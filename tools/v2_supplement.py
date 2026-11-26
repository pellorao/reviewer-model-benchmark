#!/usr/bin/env python3
"""Build the v2 supplement file next to ARW's `export` output (statspec D1 A).

ARW's export carries no cost, harness version, severity units or scenario hash, and it knows nothing of
retried attempts. This tool reads the driver's saved instance directories (`<runs>/<instance>/`:
`run.json`, `driver.json`, `score.json`, `agent.json`, optional `bench.json`) and writes one JSON file:

- per export instance id: harness CLI and version, attempt number, per-request API-equivalent USD for the
  vendors the export's token totals cannot price (Claude cache writes and Haiku prompt tiers, DeepSeek
  peak and off-peak, GLM), score severity units and the scenario hash;
- per arm (lane): instance count, attempts, retries (sum of attempt - 1) and the harness versions seen;
- per scenario: scenario hash and severity weights (the question counts of the answer key);
- the restored void rows passed with `--restored-voids` (rows an operator cleared from a void log).

The snapshot's sha256 is recorded in sources.json; the build reads only the snapshot.
"""

import argparse
import datetime
import hashlib
import json
from pathlib import Path

PER_MILLION = 1_000_000


def claude_request_usd(response, rates):
    """USD of one Claude request. The prompt length (input incl. cache) picks Haiku's tier; every cache
    write is priced at the 1-hour rate (the saved sessions hold no 5-minute writes); the ~20 uncached
    tokens per instance are priced as cache writes too (under 0.1% of the cost)."""
    prompt = response["inputTokens"]
    if "long" in rates and prompt > rates["longPromptThreshold"]:
        rates = rates["long"]
    cached = response["cachedInputTokens"]
    write = prompt - cached
    return (cached * rates["cacheRead"] + write * rates["cacheWrite1h"]
            + response["outputTokens"] * rates["output"]) / PER_MILLION


def deepseek_is_peak(epoch_ms, peak):
    """Peak hours: Monday to Friday, 01:00-04:00 and 06:00-10:00 UTC (holidays are not modelled; none in the run window)."""
    moment = datetime.datetime.fromtimestamp(epoch_ms / 1000, datetime.timezone.utc)
    return moment.weekday() in peak["weekdays"] and any(start <= moment.hour < end for start, end in peak["hours"])


def deepseek_request_usd(response, rule):
    rates = rule["peak"] if deepseek_is_peak(response["completedAt"], rule["peakUtc"]) else rule["offPeak"]
    cached = response["cachedInputTokens"]
    return (cached * rates["cacheRead"] + (response["inputTokens"] - cached) * rates["input"]
            + response["outputTokens"] * rates["output"]) / PER_MILLION


def glm_request_usd(response, rule):
    rates = rule["rates"]
    cached = response["cachedInputTokens"]
    return (cached * rates["cacheRead"] + (response["inputTokens"] - cached) * rates["input"]
            + response["outputTokens"] * rates["output"]) / PER_MILLION


def api_usd(agent, provider, model, pricing):
    """(USD, basis) summed over the instance's saved requests, or (None, None) for a vendor priced from the export's totals."""
    if provider not in ("anthropic", "opencode-go"):
        return None, None
    snapshot = agent["result"]["snapshot"]
    responses = snapshot["measurementFacts"]["responses"]
    usage = {}
    for member in snapshot["members"]:
        for key, value in (member.get("usage") or {}).items():
            usage[key] = usage.get(key, 0) + value
    if (sum(r["inputTokens"] for r in responses) != usage.get("inputTokens")
            or sum(r["outputTokens"] for r in responses) != usage.get("outputTokens")):
        raise ValueError("saved requests do not add up to the instance's usage")
    if provider == "anthropic":
        return sum(claude_request_usd(r, pricing["anthropic"][model]) for r in responses), "claude-per-request"
    if provider == "opencode-go" and model == "deepseek-v4.1-flash":
        return sum(deepseek_request_usd(r, pricing["opencode"][model]) for r in responses), "deepseek-per-request"
    if provider == "opencode-go" and model == "glm-5.3":
        return sum(glm_request_usd(r, pricing["opencode"][model]) for r in responses), "glm-per-request"
    return None, None


def claude_code_version(agent):
    """Claude Code version written into the instance's saved session (the driver records none for Claude lanes), else None."""
    for member in agent["result"]["snapshot"]["members"]:
        path = member.get("sessionPath")
        if path and Path(path).is_file():
            with open(path, encoding="utf-8") as handle:
                for line in handle:
                    try:
                        version = json.loads(line).get("version")
                    except ValueError:
                        continue
                    if version:
                        return version
    return None


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def build(runs_dir, export, pricing, restored_voids=()):
    by_run_id = {instance["id"]: instance for instance in export["instances"]}
    instances, arms, scenarios = {}, {}, {}
    for directory in sorted(Path(runs_dir).iterdir()):
        if not (directory / "driver.json").is_file():
            continue
        run = read_json(directory / "run.json")
        exported = by_run_id.get(run["id"])
        if exported is None:
            raise ValueError(f"{directory.name}: run id {run['id']} is not in the export")
        driver = read_json(directory / "driver.json")
        score = read_json(directory / "score.json")["scores"]
        bench = read_json(directory / "bench.json", {})
        settings = exported["settings"]
        agent = read_json(directory / "agent.json")
        usd, basis = api_usd(agent, settings["modelProvider"], settings["model"], pricing)
        entry = {"lane": directory.name.split("-", 1)[0], "attempt": driver.get("attempt"),
                 "harness": ({"cli": driver["harnessCli"], "version": driver["harnessVersion"]}
                             if driver.get("harnessCli") else
                             {"cli": driver["harness"], "version": driver["harnessVersion"]} if driver.get("harness") else None),
                 "timeout": bool(bench.get("timeout")), "scenarioSha256": score.get("scenarioSha256"),
                 "severityUnits": score.get("severityUnits")}
        if entry["harness"] is None and settings["modelProvider"] == "anthropic":
            version = claude_code_version(agent)
            entry["harness"] = {"cli": "claude", "version": version} if version else None
        if usd is not None:
            entry["apiUsd"], entry["costBasis"] = usd, basis
        instances[exported["id"]] = entry
        arm = arms.setdefault(entry["lane"], {"instances": 0, "attempts": None, "retries": None, "harnesses": []})
        arm["instances"] += 1
        if entry["attempt"] is not None:
            arm["attempts"] = (arm["attempts"] or 0) + entry["attempt"]
            arm["retries"] = (arm["retries"] or 0) + entry["attempt"] - 1
        if entry["harness"] and entry["harness"] not in arm["harnesses"]:
            arm["harnesses"].append(entry["harness"])
        scenario = scenarios.setdefault(exported["scenario"], {"scenarioSha256": set(), "severityWeights": {}})
        scenario["scenarioSha256"].add(entry["scenarioSha256"])
        for level, unit in (entry["severityUnits"] or {}).items():
            scenario["severityWeights"].setdefault(level, set()).add(unit["weight"])
    for name, scenario in scenarios.items():
        if len(scenario["scenarioSha256"]) != 1 or any(len(w) != 1 for w in scenario["severityWeights"].values()):
            raise ValueError(f"{name}: scenario hash or severity weights differ between instances")
        scenario["scenarioSha256"] = next(iter(scenario["scenarioSha256"]))
        scenario["severityWeights"] = {level: next(iter(w)) for level, w in scenario["severityWeights"].items()}
    missing = {i["id"] for i in export["instances"]} - set(instances)
    if missing:
        raise ValueError(f"{len(missing)} export instances have no saved directory")
    return {"schemaVersion": 1, "suite": "v2", "instances": instances,
            "arms": dict(sorted(arms.items())), "scenarios": scenarios, "restoredVoids": list(restored_voids)}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--runs", type=Path, required=True)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--pricing", type=Path, default=Path(__file__).resolve().parents[1] / "pricing-v2.json")
    parser.add_argument("--restored-voids", type=Path, help="JSON list of void rows to record in the supplement")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    export_bytes = args.export.read_bytes()
    result = build(args.runs, json.loads(export_bytes), json.loads(args.pricing.read_text(encoding="utf-8")),
                   json.loads(args.restored_voids.read_text(encoding="utf-8")) if args.restored_voids else ())
    result["exportSha256"] = hashlib.sha256(export_bytes).hexdigest()
    args.out.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{args.out}: {len(result['instances'])} instances, arms {', '.join(result['arms'])}")


if __name__ == "__main__":
    main()
