"""Statistics and cost rules for the benchmark page: pure Python, no Plotly or HTML.

`extract(results, pricing)` turns a benchmark results snapshot into one record per configuration.
"""

import json
import math
import statistics
from pathlib import Path


RESULTS_SCHEMA_VERSION = 1
PRICING_SCHEMA_VERSION = 5
SCORING_VERSION = "r8.4"
REVIEWERS = (
    ("code-standards-reviewer", "Code Standards", 0.20),
    ("code-spec-reviewer", "Code Spec", 0.20),
    ("commit-audit-reviewer", "Commit Audit", 0.25),
    ("spec-readiness-reviewer", "Spec Readiness", 0.35),
)
TOKEN_KEYS = ("uncachedInput", "cachedInput", "output")
SPEED_KEYS = ("taskOutput", "taskInput", "engineOutput", "engineInput")
EFFORTS = {"low": 0, "medium": 1, "high": 2, "xhigh": 2.5, "max": 3}
# Model and harness display names; series follow harness order, then this model order.
# The v1 page and the v2 page share this table; each page shows only the models its data has.
MODEL_NAMES = {
    "gpt-6.2-sol": "GPT-6.2 Sol",
    "gpt-6.1-sol": "GPT-6.1 Sol",
    "gpt-6.1-terra": "GPT-6.1 Terra",
    "gpt-6-luna": "GPT-6 Luna",
    "opus": "Claude Opus 5.5",
    "sonnet": "Claude Sonnet 5.5",
    "haiku": "Claude Haiku 5.5",
    "gemini-4-hydrogen": "Gemini 4 Hydrogen",
    "gemini-4-neon": "Gemini 4 Neon",
    "deepseek-flash": "DeepSeek V4.1 Flash",
    "deepseek-v4.1-flash": "DeepSeek V4.1 Flash",
    "glm-5.3": "GLM 5.3",
    "strata-iq3_xxs": "Strata IQ3_XXS",
}
HARNESS_NAMES = {"codex": "Codex", "claude-code": "Claude Code", "antigravity": "Antigravity"}
PRICING_PATH = Path(__file__).with_name("pricing.json")


def load_pricing(path=PRICING_PATH):
    """Versioned reference prices and the local running-cost assumptions."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def finite_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _beta_fraction(a, b, x):
    # Continued fraction for the regularized incomplete beta function.
    tiny = 1e-300
    c, d = 1.0, 1.0 - (a + b) * x / (a + 1)
    d = 1 / (d if abs(d) > tiny else tiny)
    result = d
    for m in range(1, 300):
        for numerator in (m * (b - m) * x / ((a + 2 * m - 1) * (a + 2 * m)),
                          -(a + m) * (a + b + m) * x / ((a + 2 * m) * (a + 2 * m + 1))):
            d = 1 + numerator * d
            d = 1 / (d if abs(d) > tiny else tiny)
            c = 1 + numerator / c
            c = c if abs(c) > tiny else tiny
            result *= c * d
        if abs(c * d - 1) < 1e-15:
            break
    return result


def _incomplete_beta(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    front = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                     + a * math.log(x) + b * math.log(1 - x))
    if x < (a + 1) / (a + b + 2):
        return front * _beta_fraction(a, b, x) / a
    return 1 - front * _beta_fraction(b, a, 1 - x) / b


def t_cdf(value, df):
    tail = 0.5 * _incomplete_beta(df / 2, 0.5, df / (df + value * value))
    return 1 - tail if value >= 0 else tail


def t_quantile(probability, df):
    low, high = -1e3, 1e3
    for _ in range(200):
        middle = (low + high) / 2
        if t_cdf(middle, df) < probability:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def _recorded_cost(instance, config, pricing):
    # DeepSeek and Claude Code instances carry the cost the benchmark recorded.
    cost = instance.get("cost") or {}
    usd = cost.get("usd")
    return (usd, bool(cost.get("lowerBound"))) if finite_number(usd) else (None, False)


def _token_cost(section):
    """Cost rule for plan-run vendors: token counts at the reference API rates of `section` in pricing.json."""
    def rule_cost(instance, config, pricing):
        return _priced_tokens(instance, config, pricing, section)
    return rule_cost


def _priced_tokens(instance, config, pricing, section):
    tokens = instance["tokens"]
    if tokens.get("cacheWriteInput"):
        # pricing.json has no cache-write rule in use; failing beats silently under-pricing.
        raise ValueError(f"OpenAI instance with cache-write tokens is not priced: {instance['id']}")
    if not all(finite_number(tokens.get(key)) for key in TOKEN_KEYS):
        return None, False
    rule = pricing_rule(pricing, section, config)
    return (sum(tokens[key] * rule["rates"][key] for key in TOKEN_KEYS)
            / pricing["tokensPerUnit"], bool(tokens.get("lowerBound")))


def _local_cost(instance, config, pricing):
    seconds = instance["time"]["durationSeconds"]
    if not finite_number(seconds):
        return None, False
    rule = pricing_rule(pricing, "localRunningCost", config)
    hourly = (rule["wallPowerWatts"] / 1000 * rule["electricityUsdPerKwh"]
              + rule["maintenanceUsdPerHour"])
    return seconds / 3600 * hourly, False


API_COST_RULES = {"deepseek": _recorded_cost, "anthropic": _recorded_cost, "opencode": _recorded_cost,
                  "openai": _token_cost("openai"), "google": _token_cost("google"), "strata": _local_cost}


def pricing_rule(pricing, section, config):
    try:
        return pricing[section][config["model"]]
    except KeyError:
        raise ValueError(f"No {section} pricing rule for model {config['model']} "
                         f"(configuration {config['key']})") from None


def instance_api_cost(instance, config, pricing):
    """Return (API-priced USD, lower bound) for one instance, or (None, False) when unknown."""
    rule = API_COST_RULES.get(config["vendor"])
    if rule is None:
        raise ValueError(f"No cost rule for vendor: {config['vendor']}")
    return rule(instance, config, pricing)


def plan_cost_rule(pricing, config):
    """v2 plan of the config's vendor as (monthly USD, weekly quota in API-equivalent USD), else None (no planCost, or no plan)."""
    plan = pricing.get("planCost", {}).get("plans", {}).get(config["vendor"])
    if plan is None:
        return None
    weekly = plan["weeklyApiUsdByModel"][config["model"]] if "weeklyApiUsdByModel" in plan else plan["weeklyApiUsd"]
    return plan["monthlyUsd"], weekly


def plan_cost(usd, config, pricing):
    """Cost of `usd` API-equivalent dollars on the plan (v2): usd / weekly quota x weekly price (monthly / days x 7)."""
    monthly, weekly = plan_cost_rule(pricing, config)
    return usd / weekly * (monthly / pricing["planCost"]["daysPerMonth"] * 7)


def plan_efficiency(pricing, vendor):
    """Efficiency ratio E of a plan vendor's quota category (Claude's cost of the same work / this plan's cost), else None."""
    rule = pricing.get("taskPoints", {}).get("efficiency", {}).get(vendor)
    return rule["e"] if rule else None


def plan_efficiency_estimate(pricing, vendor):
    """True when E of the vendor's plan category is an estimate (no direct quota measurement)."""
    rule = pricing.get("taskPoints", {}).get("efficiency", {}).get(vendor)
    return bool(rule and rule.get("estimate"))


def plan_weekly_cost(pricing):
    """USD per week of the reference plan (the Claude $100 plan): monthly price over a 30-day month, times 7 days."""
    plan = pricing["taskPoints"]["plan"]
    return plan["monthlyUsd"] / plan["daysPerMonth"] * 7


def plan_share(points, pricing):
    """Share of the reference plan's weekly quota that `points` equivalent task points use (None stays None)."""
    return None if points is None else points / pricing["taskPoints"]["plan"]["weeklyPoints"]


def instance_task_points(instance, config, pricing):
    """Equivalent task points one instance used (API-equivalent USD x E / pointUsd); None when not a plan run or unknown."""
    if "planCost" in pricing:
        return None  # v2 has no task points: cost is the run's share of the plan's own weekly quota
    e = plan_efficiency(pricing, config["vendor"])
    usd = instance_api_cost(instance, config, pricing)[0]
    return None if e is None or usd is None else usd * e / pricing["taskPoints"]["pointUsd"]


def instance_cost(instance, config, pricing):
    """Return (USD, lower bound) for one instance, or (None, False) when unknown.

    A plan vendor's run costs its equivalent task points' share of the reference plan's weekly quota
    times that plan's weekly price; every other vendor's cost is its own dollar rule.
    """
    if "planCost" in pricing and plan_cost_rule(pricing, config) is not None:
        usd, bound = instance_api_cost(instance, config, pricing)
        return (None, False) if usd is None else (plan_cost(usd, config, pricing), bound)
    points = instance_task_points(instance, config, pricing)
    if points is None:
        return instance_api_cost(instance, config, pricing)
    return plan_share(points, pricing) * plan_weekly_cost(pricing), instance_api_cost(instance, config, pricing)[1]


def mean_of(values):
    return sum(values) / len(values) if values else None


def summarize_cell(instances, config, pricing):
    scores = [instance["scoring"]["score"] for instance in instances]
    n = len(scores)
    mean = sum(scores) / n
    sd = statistics.stdev(scores) if n > 1 else None
    se = sd / math.sqrt(n) if sd is not None else None
    half = t_quantile(0.975, n - 1) * se if se is not None else None
    durations = [instance["time"]["durationSeconds"] for instance in instances
                 if finite_number(instance["time"]["durationSeconds"])]
    token_sets = [instance["tokens"] for instance in instances
                  if all(finite_number(instance["tokens"].get(key)) for key in TOKEN_KEYS)]
    costs = [instance_cost(instance, config, pricing) for instance in instances]
    costs = [cost for cost in costs if cost[0] is not None]
    points = [instance_task_points(instance, config, pricing) for instance in instances]
    points = [value for value in points if value is not None]
    api_costs = ([instance_api_cost(instance, config, pricing)[0] for instance in instances]
                 if points or ("planCost" in pricing and plan_cost_rule(pricing, config)) else [])
    api_costs = [usd for usd in api_costs if usd is not None]
    speeds, speed_counts, speed_bounds = {}, {}, {}
    for key in SPEED_KEYS:
        token_key = "output" if key.endswith("Output") else "uncachedInput"
        # A speed is total tokens over total seconds, never a mean of per-run rates. Each
        # run's seconds follow from its own rate, which keeps the benchmark's time basis.
        used = [instance for instance in instances
                if finite_number(instance["speeds"].get(key)) and instance["speeds"][key] > 0
                and finite_number(instance["tokens"].get(token_key))]
        tokens = [instance["tokens"][token_key] for instance in used]
        seconds = [instance["tokens"][token_key] / instance["speeds"][key] for instance in used]
        speeds[key] = sum(tokens) / sum(seconds) if used and sum(seconds) > 0 else None
        speed_counts[key] = len(used)
        speed_bounds[key] = any(key in instance["speeds"].get("lowerBounds", []) for instance in used)
    return {
        "n": n, "mean": mean, "sd": sd, "se": se, "half": half,
        "min": min(scores), "median": statistics.median(scores),
        "negatives": sum(score < 0 for score in scores),
        "failures": sum(instance["scoring"]["status"] == "modelFailure" for instance in instances),
        "minutes": mean_of(durations) / 60 if durations else None, "timeCount": len(durations),
        "tokens": ({key: mean_of([tokens[key] for tokens in token_sets]) for key in TOKEN_KEYS}
                   if token_sets else None),
        "tokenCount": len(token_sets),
        "tokenLowerBound": any(tokens.get("lowerBound") for tokens in token_sets),
        "cost": mean_of([cost[0] for cost in costs]), "costCount": len(costs),
        "costLowerBound": any(cost[1] for cost in costs),
        "taskPoints": mean_of(points), "planShare": plan_share(mean_of(points), pricing),
        "apiCost": mean_of(api_costs),
        "efficiency": plan_efficiency(pricing, config["vendor"]),
        "efficiencyEstimate": plan_efficiency_estimate(pricing, config["vendor"]),
        "speeds": speeds, "speedCounts": speed_counts,
        "speedLowerBounds": speed_bounds,
    }


def composite(cells):
    score = 100 * sum(cells[key]["mean"] * weight for key, _, weight in REVIEWERS)
    parts = [(weight ** 2 * cells[key]["se"] ** 2, cells[key]["n"])
             for key, _, weight in REVIEWERS if cells[key]["se"] is not None]
    half = None
    if len(parts) == len(REVIEWERS):
        variance = sum(part for part, _ in parts)
        if variance == 0:
            half = 0.0
        else:
            # Welch-Satterthwaite degrees of freedom for a weighted sum of independent means.
            df = variance ** 2 / sum(part ** 2 / (n - 1) for part, n in parts)
            half = 100 * t_quantile(0.975, df) * math.sqrt(variance)

    def average(field):
        values = [cells[key][field] for key, _, _ in REVIEWERS if cells[key][field] is not None]
        return mean_of(values), len(values)

    minutes, time_count = average("minutes")
    cost, cost_count = average("cost")
    task_points, _ = average("taskPoints")
    plan_share_value, _ = average("planShare")
    api_cost, _ = average("apiCost")
    token_cells = [cells[key]["tokens"] for key, _, _ in REVIEWERS if cells[key]["tokens"]]
    return {
        "score": score, "half": half, "minutes": minutes, "timeCount": time_count,
        "cost": cost, "costCount": cost_count,
        "costLowerBound": any(cells[key]["costLowerBound"] for key, _, _ in REVIEWERS),
        "taskPoints": task_points, "planShare": plan_share_value, "apiCost": api_cost,
        "efficiency": next((cells[key]["efficiency"] for key, _, _ in REVIEWERS if cells[key]["efficiency"] is not None), None),
        "efficiencyEstimate": any(cells[key]["efficiencyEstimate"] for key, _, _ in REVIEWERS),
        "tokens": ({key: mean_of([tokens[key] for tokens in token_cells]) for key in TOKEN_KEYS}
                   if token_cells else None),
    }


def merge_supplements(results, supplements):
    """The main results file plus supplement-only files (benchmark phase 4): same schema, scoring and scenarios;
    their configurations and instances are added, a configuration or instance in two files is an error."""
    merged = dict(results, configs=list(results["configs"]), instances=list(results["instances"]))
    for extra in supplements:
        if (extra.get("meta", {}).get("schemaVersion") != RESULTS_SCHEMA_VERSION
                or extra["meta"].get("scoring", {}).get("version") != SCORING_VERSION):
            raise ValueError("A supplement file must have the same schema and scoring version as the main file.")
        if [s["id"] for s in extra["scenarios"]] != [s["id"] for s in results["scenarios"]]:
            raise ValueError("A supplement file must have the same scenarios as the main file.")
        keys = {config["key"] for config in merged["configs"]}
        ids = {instance["id"] for instance in merged["instances"]}
        if keys & {config["key"] for config in extra["configs"]} or ids & {i["id"] for i in extra["instances"]}:
            raise ValueError("A supplement file repeats a configuration or instance of the main file.")
        merged["configs"] += extra["configs"]
        merged["instances"] += extra["instances"]
    return merged


def extract(results, pricing, supplements=()):
    """Group the benchmark's main-statistic instances into configuration records."""
    if supplements:
        results = merge_supplements(results, supplements)
    if not isinstance(results, dict) or results.get("meta", {}).get("schemaVersion") != RESULTS_SCHEMA_VERSION:
        raise ValueError(f"Expected a schema-version-{RESULTS_SCHEMA_VERSION} benchmark results file.")
    if results["meta"].get("scoring", {}).get("version") != SCORING_VERSION:
        raise ValueError(f"Expected scoring version {SCORING_VERSION} in the benchmark results.")
    if pricing.get("schemaVersion") != PRICING_SCHEMA_VERSION:
        raise ValueError(f"Expected a schema-version-{PRICING_SCHEMA_VERSION} pricing file.")
    scenario_reviewers = {scenario["id"]: scenario["reviewerId"] for scenario in results["scenarios"]}
    if sorted(scenario_reviewers.values()) != sorted(key for key, _, _ in REVIEWERS):
        raise ValueError("The results must contain exactly the four weighted reviewers.")
    # Supplement configurations (phase 3: GPT-6 Luna xhigh / max; phase 4: Gemini 4 Hydrogen) are plotted like main ones.
    configs = {config["key"]: config for config in results["configs"] if config["kind"] in ("main", "phase3", "phase4")}
    for config in configs.values():
        if (config["model"] not in MODEL_NAMES or config["harness"] not in HARNESS_NAMES
                or config["effort"] not in EFFORTS):
            raise ValueError(f"Unknown configuration: {config['key']}")
    if not configs:
        raise ValueError("The results contain no main or phase-3 configuration.")
    instances = {(key, reviewer): [] for key in configs for reviewer, _, _ in REVIEWERS}
    for instance in results["instances"]:
        # Supplementary configurations (DeepSeek "high requested as medium") are not plotted.
        if not instance["selection"]["inMain"] or instance["supplementaryNote"] is not None:
            continue
        if not instance["validity"]["valid"] or not finite_number(instance["scoring"].get("score")):
            raise ValueError(f"Main-statistic instance without a valid score: {instance['id']}")
        cell_key = (instance["configKey"], scenario_reviewers[instance["scenario"]])
        if cell_key not in instances:
            raise ValueError(f"Main-statistic instance of an unexpected configuration: {instance['id']}")
        instances[cell_key].append(instance)
    records = []
    # Model groups first (GPT, Claude, DeepSeek, local; stronger first), then Codex before Claude Code.
    series_order = [(harness, model) for model in MODEL_NAMES for harness in HARNESS_NAMES]
    for key, config in configs.items():
        cells = {}
        for reviewer, name, _ in REVIEWERS:
            cell_instances = instances[(key, reviewer)]
            if not cell_instances:
                raise ValueError(f"No main-statistic instances: {key} / {name}")
            cells[reviewer] = summarize_cell(cell_instances, config, pricing)
        harness, model, effort = config["harness"], config["model"], config["effort"]
        records.append({
            "key": key, "harness": harness, "model": model, "effort": effort,
            "vendor": config["vendor"], "series": series_order.index((harness, model)),
            "label": f"{MODEL_NAMES[model]} · {effort} · {HARNESS_NAMES[harness]}",
            "cells": cells, **composite(cells)})
    # Configuration order: model (groups and strength follow MODEL_NAMES), effort high to low, then harness.
    model_order = list(MODEL_NAMES)
    harness_order = list(HARNESS_NAMES)
    records.sort(key=lambda record: (model_order.index(record["model"]), -EFFORTS[record["effort"]],
                                     harness_order.index(record["harness"])))
    return records


# ---- Benchmark v2 (ARW export plus the driver's supplement file; statspec 2026-11-19 D1 to D8) ----

V2_PRICING_SCHEMA_VERSION = 7
V2_SCORING_VERSION = "r8.5"
V2_SPEED_KEYS = ("taskOutput", "taskInput")  # D8: v2 has no engine speeds
V2_CELL_RUNS = 5
V2_FIXTURE_TREE = "4326aca3cbd04ae126f6f4a3e26867f2b740e81a"
# Export provider -> (cost vendor, harness shown on the page).
V2_PROVIDERS = {"openai": ("openai", "codex"), "anthropic": ("anthropic", "claude-code"),
                "agy": ("google", "antigravity"), "qwen_strata": ("strata", "codex"),
                "opencode-go": ("opencode", "codex")}
# Export model id -> key in MODEL_NAMES and pricing.json.
V2_MODELS = {"hydrogen": "gemini-4-hydrogen", "neon": "gemini-4-neon",
             "qwen3.8-flash-next-iq3_xxs": "strata-iq3_xxs"}


def _v2_instance(raw, extra, config_key):
    """One export instance in the shape summarize_cell reads (task speeds only; the cost comes from the supplement)."""
    seconds, tokens = raw["time"]["durationSeconds"], raw["tokens"]
    speeds = {key: (tokens[token] / seconds if finite_number(seconds) and seconds > 0 else None)
              for key, token in (("taskOutput", "output"), ("taskInput", "uncachedInput"))}
    usd = extra.get("apiUsd")
    return {"id": raw["id"], "configKey": config_key, "scenario": raw["scenario"], "scoring": raw["scoring"],
            "time": raw["time"], "tokens": dict(tokens), "speeds": {**speeds, "lowerBounds": []},
            "cost": {"usd": usd} if usd is not None else None}


def _check_v2_instance(raw, extra, scenario_sha):
    problems = []
    if not raw["validity"]["valid"] or not finite_number(raw["scoring"].get("score")):
        problems.append("not valid or not scored")
    if raw["scoring"].get("status") not in ("final", "modelFailure"):
        problems.append(f"scoring status {raw['scoring'].get('status')}")
    if raw["arw"]["treeDirty"] or raw["arw"]["fixtureTree"] != V2_FIXTURE_TREE or not raw["runtime"]["matchesCheckout"]:
        problems.append("ARW checkout is dirty, off the fixture tree, or differs from the runtime")
    if extra["scenarioSha256"] != scenario_sha:
        problems.append("scenario hash differs from the scenario's recorded one")
    if problems:
        raise ValueError(f"v2 instance {raw['id']}: " + "; ".join(problems))


def extract_v2(export, supplement, pricing, export_sha256=None):
    """Group a v2 export into configuration records like `extract`; returns (records, meta).

    Timed-out instances are counted when the export scored them (the export holds only scored ones; the
    supplement says which timed out). Every cell must hold exactly five runs; anything else fails the build.
    """
    if export.get("status") != "succeeded" or export.get("schemaVersion") != 1:
        raise ValueError("Expected a succeeded schema-version-1 ARW export.")
    if pricing.get("schemaVersion") != V2_PRICING_SCHEMA_VERSION:
        raise ValueError(f"Expected a schema-version-{V2_PRICING_SCHEMA_VERSION} pricing file.")
    if supplement.get("schemaVersion") != 1 or supplement.get("suite") != "v2":
        raise ValueError("Expected a schema-version-1 v2 supplement file.")
    if export_sha256 is not None and export_sha256 != supplement.get("exportSha256"):
        raise ValueError("The supplement was made from a different export file.")
    extras = supplement["instances"]
    scenario_reviewers = {}
    for scenario in {instance["scenario"] for instance in export["instances"]}:
        scenario_reviewers[scenario] = scenario.split("/")[1] + "-reviewer"
    if sorted(scenario_reviewers.values()) != sorted(key for key, _, _ in REVIEWERS):
        raise ValueError("The export must contain exactly the four weighted reviewers.")
    configs, cells, pins, timeouts = {}, {}, {}, {}
    for raw in export["instances"]:
        extra = extras.get(raw["id"])
        if extra is None:
            raise ValueError(f"v2 instance {raw['id']} has no supplement entry")
        _check_v2_instance(raw, extra, supplement["scenarios"][raw["scenario"]]["scenarioSha256"])
        settings = raw["settings"]
        if settings["modelProvider"] not in V2_PROVIDERS:
            raise ValueError(f"Unknown v2 provider: {settings['modelProvider']}")
        vendor, harness = V2_PROVIDERS[settings["modelProvider"]]
        model = V2_MODELS.get(settings["model"], settings["model"])
        effort = settings["reasoningEffort"]
        if model not in MODEL_NAMES or effort not in EFFORTS:
            raise ValueError(f"Unknown v2 configuration: {settings['model']} / {effort}")
        key = f"{harness}/{model}/{effort}"
        config = configs.setdefault(key, {"key": key, "harness": harness, "model": model, "effort": effort,
                                          "vendor": vendor, "kind": "main", "lane": extra["lane"]})
        reviewer = scenario_reviewers[raw["scenario"]]
        cells.setdefault((key, reviewer), []).append(_v2_instance(raw, extra, key))
        pins.setdefault(extra["lane"], set()).add(raw["arw"]["commit"])
        if extra["timeout"]:
            timeouts[(key, reviewer)] = timeouts.get((key, reviewer), 0) + 1
    records = []
    series_order = [(harness, model) for model in MODEL_NAMES for harness in HARNESS_NAMES]
    for key, config in configs.items():
        record_cells = {}
        for reviewer, name, _ in REVIEWERS:
            cell_instances = cells.get((key, reviewer), [])
            if len(cell_instances) != V2_CELL_RUNS:
                raise ValueError(f"{key} / {name}: {len(cell_instances)} runs, expected {V2_CELL_RUNS}")
            record_cells[reviewer] = summarize_cell(cell_instances, config, pricing)
            record_cells[reviewer]["timeouts"] = timeouts.get((key, reviewer), 0)
        harness, model, effort = config["harness"], config["model"], config["effort"]
        records.append({"key": key, "harness": harness, "model": model, "effort": effort,
                        "vendor": config["vendor"], "lane": config["lane"],
                        "series": series_order.index((harness, model)),
                        "label": f"{MODEL_NAMES[model]} · {effort} · {HARNESS_NAMES[harness]}",
                        "cells": record_cells, **composite(record_cells)})
    records.sort(key=lambda r: (list(MODEL_NAMES).index(r["model"]), -EFFORTS[r["effort"]],
                                list(HARNESS_NAMES).index(r["harness"])))
    arms = {}
    for lane, info in supplement["arms"].items():
        lane_records = [r for r in records if r["lane"] == lane]
        arms[lane] = {**info, "models": sorted({r["model"] for r in lane_records}),
                      "pins": sorted(pins.get(lane, ())),
                      "modelFailures": sum(cell["failures"] for r in lane_records for cell in r["cells"].values())}
    meta = {"arms": arms, "scenarios": supplement["scenarios"], "restoredVoids": supplement.get("restoredVoids", []),
            "timeouts": sum(timeouts.values()),
            "failures": sum(cell["failures"] for r in records for cell in r["cells"].values())}
    return records, meta
