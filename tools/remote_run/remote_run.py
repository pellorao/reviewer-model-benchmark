#!/usr/bin/env python3
"""Run the Reviewer capability suite with any command-line model, pack the results, import them elsewhere.

The suite (scenarios, answer keys, scoring) is ARW's, used as a black box through its node CLI at a pinned checkout;
this script only replaces the part of ARW's `run` that needs ARW's own background-agent daemon: it builds a scenario
with `setup`, hands the prompt to a configurable command (for example `agy -p`), then repairs and scores the report
with `repair` / `score`, and saves each instance in the layout of the local benchmark driver.

  check   verify the ARW checkout, node, git, the config; `--call` also sends one tiny prompt to the command
  plan    print the cells, the expected usage and the first command line; no model call
  run     run the cells (resumable), one model call per instance
  pack    pack the saved instances into one .tar.gz bundle
  import  verify a bundle and unpack it into a local `runs` directory

Python 3.9+ standard library only. See README.md.
"""
import argparse
import contextlib
import hashlib
import io
import json
import math
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

# ---- tunables ----
TOOL_VERSION = 1
PIN_FILE = HERE / "pin.json"                        # {"arw_commit", "fixture_tree"}: the one place the pin is written
SCENARIOS = {                                       # task order of a round: CA, CS, CStd, SR
    "commit-audit": "requirements-reviewer",
    "code-spec": "requirements-reviewer",
    "code-standards": "code-standards-reviewer",
    "spec-readiness": "spec-readiness-reviewer",
}
FIXTURES = "tests/fixtures/reviewer-capability"
N_DEFAULT = 5                                       # instances per cell
RUN_LIMIT_SECONDS = 3600                            # ARW's own limit of one Reviewer run
KILL_GRACE = 10                                     # s between the terminate and the kill of a timed-out command
ARW_CALL_TIMEOUT = 600                              # s for one `setup` / `repair` / `score` call
ATTEMPTS_PER_CELL = 8                               # valid, timed-out and void attempts all count; blocked or failed ones do not
VOID_STREAK = 2                                     # same void reason in a row that stops the run (no-completion: below)
NO_COMPLETION_STREAK = 3
FAIL_STREAK = 3                                     # blocked / failed in a row
CALL_FACTOR = 2                                     # the usage guard stops at this multiple of the expected number of calls
EST_INSTANCE_SECONDS = 1800                         # expected wall time of one instance (a guess; the first instance calibrates)
MAX_OUT_TOKENS = 300_000                            # output tokens of one call, when the command prints JSON usage
STOP_EXIT = 75
PROMPT_TEMPLATE = "{instructions}\n\n---\n\n{handoff}\n"
MAX_FILE_BYTES = 50_000_000                         # per file inside a bundle
MAX_BUNDLE_BYTES = 500_000_000
CELL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._]*(-[A-Za-z0-9._]+)*-r[1-9][0-9]*$")
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
PLACEHOLDER = re.compile(r"\{([a-z_]+(?:\.[A-Za-z0-9_.-]+)?)\}")
# ---- end tunables ----

KNOWN_VARS = {"prompt", "prompt_file", "cwd", "report_path", "report_dir", "model", "model_id", "effort", "scenario"}


class Stop(Exception):
    """The run must stop (usage guard, repeated failure, STOP file); the message says why."""


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def write_json(path, value):
    Path(path).write_text(json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def load_pin():
    pin = read_json(PIN_FILE)
    if not isinstance(pin, dict) or not pin.get("arw_commit") or not pin.get("fixture_tree"):
        raise SystemExit(f"{PIN_FILE} is missing or has no arw_commit / fixture_tree.")
    return pin


# ---------------------------------------------------------------- ARW checkout and CLI

def git_out(arw, *args):
    done = subprocess.run(["git", "-C", str(arw), *args], capture_output=True, text=True, timeout=60)
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed in {arw}: {done.stderr.strip()[:200]}")
    return done.stdout.strip()


def check_arw(arw, pin):
    """The checkout must be the pinned commit with the pinned fixture tree and no tracked change; returns the provenance record."""
    commit = git_out(arw, "rev-parse", "HEAD")
    dirty = git_out(arw, "status", "--porcelain", "--untracked-files=no")
    tree = git_out(arw, "rev-parse", f"HEAD:{FIXTURES}")
    if commit != pin["arw_commit"]:
        raise SystemExit(f"ARW is at {commit}, the pin is {pin['arw_commit']}: git -C {arw} checkout {pin['arw_commit']}")
    if dirty:
        raise SystemExit(f"ARW checkout has tracked changes:\n{dirty[:300]}")
    if tree != pin["fixture_tree"]:
        raise SystemExit(f"Fixture tree {tree} differs from the pin {pin['fixture_tree']}.")
    package = read_json(Path(arw) / "package.json", {})
    return {"commit": commit, "treeDirty": False, "fixtureTree": tree, "arwVersion": package.get("version", "")}


def arw_call(arw, args, work, timeout=ARW_CALL_TIMEOUT):
    """`node scripts/reviewer-capability.mjs ARGS` -> its JSON result. stdout goes to a file: the pinned CLI exits
    without waiting for a pipe to drain, so a result over the pipe buffer (a `score` result is about 100 KB) would be cut off."""
    out_path = Path(work) / f"arw-{secrets.token_hex(4)}.json"
    try:
        with open(out_path, "wb") as out:
            try:
                done = subprocess.run(["node", str(Path(arw) / "scripts" / "reviewer-capability.mjs"), *map(str, args)], cwd=str(arw),
                                      stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.PIPE, timeout=timeout)
            except subprocess.TimeoutExpired:
                return {"status": "failed", "stage": "arw-timeout"}
        try:
            data = json.loads(out_path.read_text(encoding="utf-8").strip().splitlines()[-1])
            if not isinstance(data, dict):
                raise ValueError
        except (OSError, ValueError, IndexError):
            data = {"status": "failed", "stage": "arw-parse"}
    finally:
        with contextlib.suppress(OSError):
            out_path.unlink()
    data["_rc"] = done.returncode
    data["_stderr"] = done.stderr.decode("utf-8", "replace")[-300:]
    return data


# ---------------------------------------------------------------- config and the model command

def load_config(path):
    config = read_json(path)
    if not isinstance(config, dict):
        raise SystemExit(f"{path} is not a JSON object.")
    command = config.get("command")
    if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
        raise SystemExit('config "command" must be a non-empty list of strings (an argument vector, no shell).')
    files = config.setdefault("files", {})
    if not isinstance(files, dict) or not all(SAFE_NAME.match(name) for name in files):
        raise SystemExit('config "files" must map plain file names to a string or JSON template.')
    known = KNOWN_VARS | {f"file.{name}" for name in files}
    texts = list(command) + [json.dumps(v) if not isinstance(v, str) else v for v in files.values()]
    for text in texts:
        for var in PLACEHOLDER.findall(text):
            if var not in known:
                raise SystemExit(f"Unknown placeholder {{{var}}} in the config; known: {', '.join(sorted(known))}.")
    config.setdefault("provider", "agy")
    config.setdefault("env", {})
    config.setdefault("version_command", None)
    return config


def render(value, variables):
    """Substitute {name} placeholders in a string, or in every string of a JSON value."""
    if isinstance(value, str):
        return PLACEHOLDER.sub(lambda m: str(variables[m.group(1)]), value)
    if isinstance(value, list):
        return [render(x, variables) for x in value]
    if isinstance(value, dict):
        return {k: render(v, variables) for k, v in value.items()}
    return value


def kill_tree(proc):
    """Terminate a command and what it started; kill it when it does not stop within KILL_GRACE."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
            return
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(KILL_GRACE)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def call_model(argv, cwd, env, stdin_text, timeout):
    """Run the model command. Returns {rc, out, err, seconds, timed_out}; on timeout the process tree is stopped first."""
    kwargs = {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)} if os.name == "nt" else {"start_new_session": True}
    started = time.monotonic()
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE if stdin_text is not None else subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", **kwargs)
    timed_out = False
    try:
        out, err = proc.communicate(stdin_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=KILL_GRACE)
        except subprocess.TimeoutExpired:
            out, err = "", ""
    except BaseException:
        kill_tree(proc)
        raise
    return {"rc": proc.returncode, "out": out or "", "err": err or "", "seconds": time.monotonic() - started, "timed_out": timed_out}


def parse_usage(text):
    """Token counts from a JSON result with a `usage` object (what `agy -p --output-format json` prints); None fields when absent."""
    try:
        usage = json.loads(text).get("usage")
    except (ValueError, AttributeError):
        usage = None
    usage = usage if isinstance(usage, dict) else {}
    number = lambda key: int(usage[key]) if isinstance(usage.get(key), (int, float)) and math.isfinite(usage[key]) else None
    inp, cached = number("input_tokens"), number("cache_read_tokens")
    return {"uncachedInput": None if inp is None or cached is None else max(0, inp - cached), "cachedInput": cached, "output": number("output_tokens")}


def scan_leaks(arw, texts):
    """Answer-key locations seen in what the command printed or the report says. A weak stand-in for ARW's `inspect`, which needs
    the session records of Codex or Claude Code; the real barrier is the read permission given to the command (README)."""
    root = str(Path(arw).resolve())
    markers = {root + "/", root.replace("\\", "/") + "/", root + os.sep, FIXTURES}
    return sorted(m for m in markers if m and any(m in text for text in texts))


# ---------------------------------------------------------------- cells, usage guard, attempt log

def task_list(model, efforts, scenarios, n):
    """Cells of the run in order: one round holds every effort x scenario once; odd rounds forward, even rounds reversed."""
    cells = [(effort, scenario) for effort in efforts for scenario in scenarios]
    tasks = []
    for rnd in range(1, n + 1):
        for effort, scenario in (cells if rnd % 2 else cells[::-1]):
            tasks.append({"cell": f"{model}-{effort}-{scenario}-r{rnd}", "effort": effort, "scenario": scenario, "round": rnd})
    return tasks


class Guard:
    """Usage watch: states the expected usage up front, compares the actual after every call, stops past CALL_FACTOR times it."""

    def __init__(self, out, expected_calls):
        self.out, self.expected, self.calls, self.seconds = Path(out), expected_calls, 0, 0.0
        self.marker = self.out / "STOPPED.json"

    def expectation(self):
        return {"calls": self.expected, "seconds": self.expected * EST_INSTANCE_SECONDS,
                "call_limit": math.ceil(CALL_FACTOR * self.expected), "second_limit": CALL_FACTOR * self.expected * EST_INSTANCE_SECONDS}

    def refuse_if_stopped(self, ack):
        stopped = read_json(self.marker)
        if stopped is None:
            return
        if not ack:
            raise Stop(f"A previous run stopped itself ({stopped.get('reason')}); check the cause, then run again with --ack '<what you checked>'.")
        with open(self.out / "acks.log", "a", encoding="utf-8") as log:
            log.write(f"{now_iso()} {ack} (stop was: {stopped.get('reason')})\n")
        self.marker.unlink()

    def record(self, seconds, out_tokens):
        """Count one finished call; raises Stop (and leaves the marker) when the actual runs past the expectation."""
        self.calls += 1
        self.seconds += seconds
        limits = self.expectation()
        reason = None
        if self.calls > limits["call_limit"]:
            reason = f"{self.calls} calls, expected {limits['calls']} (limit {limits['call_limit']})"
        elif self.seconds > limits["second_limit"]:
            reason = f"{int(self.seconds)} s of model time, expected {limits['seconds']} s (limit {limits['second_limit']})"
        elif out_tokens is not None and out_tokens > MAX_OUT_TOKENS:
            reason = f"one call produced {out_tokens} output tokens (cap {MAX_OUT_TOKENS})"
        if reason:
            write_json(self.marker, {"reason": reason, "calls": self.calls, "seconds": int(self.seconds), "expected": limits, "at": now_iso()})
            raise Stop(f"usage guard: {reason}")


class Attempts:
    """Append-only log of attempts (`attempts.jsonl`): the resume state and the source of the streak rules."""

    def __init__(self, out):
        self.path = Path(out) / "attempts.jsonl"
        self.rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines() if self.path.exists() else []:
            with contextlib.suppress(ValueError):
                self.rows.append(json.loads(line))

    def add(self, row):
        row = dict(row, at=now_iso())
        self.rows.append(row)
        with open(self.path, "a", encoding="utf-8") as log:
            log.write(json.dumps(row, ensure_ascii=False) + "\n")

    def counted(self, cell):
        return sum(1 for r in self.rows if r["cell"] == cell and r["outcome"] in ("valid", "timeout", "void"))

    def streak(self, outcomes, reason=None):
        """Length of the newest run of rows whose outcome is in `outcomes` (and whose reason is `reason`, when given)."""
        count = 0
        for row in reversed(self.rows):
            if row["outcome"] not in outcomes or (reason is not None and row.get("reason") != reason):
                break
            count += 1
        return count


# ---------------------------------------------------------------- one instance

def find_report(setup_input, instance):
    """The delivered report: the path `setup` named, else (timeouts) the newest non-empty report or draft file under the instance's .tmp."""
    path = Path(setup_input["reportPath"])
    if path.is_file() and path.stat().st_size > 0:
        return path
    found = [p for p in Path(instance).glob(".tmp/**/*") if p.is_file() and p.stat().st_size > 0
             and re.search(r"report|draft", str(p.relative_to(instance))) and p.name not in ("request.json", "input.json")]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


class Runner:
    """One cell attempt = one model call. `arw` and `model` are injectable (tests pass fakes)."""

    def __init__(self, args, config, provenance, out, work, arw=None, model=None):
        self.args, self.config, self.provenance, self.out, self.work = args, config, provenance, Path(out), Path(work)
        self.arw_dir = Path(args.arw).resolve()
        self.arw = arw or (lambda a: arw_call(self.arw_dir, a, self.work))
        self.model = model or call_model
        self.harness_version = ""
        self.pending_stop = None
        self.limit = getattr(args, "limit_seconds", RUN_LIMIT_SECONDS)

    def scenario_dir(self, scenario):
        return self.arw_dir / FIXTURES / SCENARIOS[scenario] / scenario

    def settings(self, effort):
        return {"model": self.args.model_id or self.args.model, "modelProvider": self.config["provider"], "reasoningEffort": effort, "serviceTier": "default"}

    def attempt(self, task, attempt_no, guard):
        """Returns (outcome, reason, saved_dir_or_None): outcome valid, timeout, void, failed."""
        scenario, effort, cell = task["scenario"], task["effort"], task["cell"]
        iid = "i-" + secrets.token_hex(6)                   # opaque: the instance path reaches the model and its report
        run_dir = self.work / ("r-" + secrets.token_hex(4))
        inst, side = run_dir / iid, run_dir / "side"
        side.mkdir(parents=True)
        try:
            setup = self.arw(["setup", self.scenario_dir(scenario), inst])
            if setup.get("status") != "succeeded":
                return "failed", f"setup:{setup.get('status')}:{setup.get('stage', '')}", None
            spec = setup["input"]
            prompt = PROMPT_TEMPLATE.format(instructions=spec["instructions"], handoff=spec["handoff"])
            prompt_file = side / "prompt.md"
            prompt_file.write_text(prompt, encoding="utf-8")
            variables = {"prompt": prompt, "prompt_file": prompt_file, "cwd": spec["cwd"], "report_path": spec["reportPath"],
                         "report_dir": Path(spec["reportPath"]).parent, "model": self.args.model, "model_id": self.args.model_id or self.args.model,
                         "effort": effort, "scenario": scenario}
            for name, template in self.config["files"].items():
                text = render(template, variables) if isinstance(template, str) else json.dumps(render(template, variables))
                (side / name).write_text(text, encoding="utf-8")
                variables[f"file.{name}"] = side / name
            argv = [render(part, variables) for part in self.config["command"]]
            uses_prompt = any("{prompt}" in part or "{prompt_file}" in part for part in self.config["command"])
            env = dict(os.environ, **{k: render(v, variables) for k, v in self.config["env"].items()},
                       RB_REPORT_PATH=str(spec["reportPath"]), RB_CWD=str(spec["cwd"]), RB_PROMPT_FILE=str(prompt_file),
                       RB_MODEL=self.args.model, RB_EFFORT=effort, RB_SCENARIO=scenario)
            started = now_iso()
            call = self.model(argv, spec["cwd"], env, None if uses_prompt else prompt, self.limit)
            finished = now_iso()
            usage = parse_usage(call["out"])
            guard_stop = None
            try:
                guard.record(call["seconds"], usage["output"])
            except Stop as stop:
                guard_stop = stop                            # finish this instance first, then stop
            report = find_report(spec, inst)
            leaks = scan_leaks(self.arw_dir, [call["out"], call["err"], report.read_text("utf-8", "replace") if report else ""])
            notes = ""
            if call["timed_out"]:
                notes = f"timeout: no result within {self.limit} s (command stopped)"
            elif report is None or not (Path(spec["reportPath"]).is_file() and Path(spec["reportPath"]).stat().st_size > 0):
                notes = f"no-completion: command exit {call['rc']}, no report at the expected path"
            elif leaks:
                notes = f"inspect-flags: {len(leaks)} (answer-key location seen: {leaks[0]})"
            record = {"id": iid, "scenario": f"{SCENARIOS[scenario]}/{scenario}", "arw": {k: self.provenance[k] for k in ("commit", "treeDirty", "fixtureTree")},
                      "runtime": {"arwVersion": self.provenance["arwVersion"], "matchesCheckout": True, "portable": True},
                      "settings": self.settings(effort), "startedAt": started, "completedAt": finished,
                      "time": {"durationSeconds": call["seconds"], "durationEstimated": True, "wallClockSeconds": call["seconds"], "timeLimitSeconds": self.limit},
                      "tokens": usage, "validity": {"valid": notes == "", "status": "valid" if notes == "" else "void", "notes": notes},
                      "report": None, "repair": None}
            extra = {"exitCode": call["rc"], "harness": self.config["provider"], "harnessVersion": self.harness_version, "instanceId": iid,
                     "inspection": "portable-scan", "tool": TOOL_VERSION}
            if notes == "" or notes.startswith("timeout"):
                outcome, reason, saved = self.score_and_save(task, attempt_no, spec, inst, side, report, record, extra, timed_out=notes != "")
            elif notes.startswith("no-completion"):
                outcome, reason, saved = "void", "no-completion", None
            else:
                outcome, reason, saved = "void", "inspect-flags", None
            if outcome in ("void", "failed"):
                self.keep_for_diagnosis(cell, attempt_no, iid, report, call, reason)
            self.pending_stop = guard_stop                  # run_lane logs this attempt first, then stops
            return outcome, reason, saved
        finally:
            shutil.rmtree(run_dir, ignore_errors=True)

    def score_and_save(self, task, attempt_no, spec, inst, side, report, record, extra, timed_out):
        """Repair and score the report the way ARW's `run` does (repair, score, fall back to the unrepaired report on a model failure)."""
        scenario_dir = self.scenario_dir(task["scenario"])
        agent_path = side / "agent.json"
        write_json(agent_path, {"status": "succeeded", "result": {"runId": record["id"], "notifications": [], "completion": {"reportPath": "report"},
                                                                  "portable": True, "exitCode": extra["exitCode"]}})
        scored, use, repair_record = None, None, None
        if report is not None:
            ext = report.suffix
            repaired = self.arw(["repair", scenario_dir, report, side / f"report.repaired{ext}"])
            if repaired.get("status") != "succeeded":
                return "failed", f"repair:{repaired.get('status')}:{repaired.get('stage', '')}", None
            changed = bool(repaired.get("changes"))
            use, repair_record = (repaired["normalized"], repaired["record"]) if changed else (str(report), None)
            args = ["score", scenario_dir, use, "--agent", agent_path, "--instance", record["id"]]
            scored = self.arw(args + (["--repair", repair_record] if repair_record else ["--no-repair"]))
            if repair_record and scored.get("status") == "blocked":
                fallback = self.arw(["score", scenario_dir, str(report), "--agent", agent_path, "--instance", record["id"], "--no-repair"])
                if fallback.get("status") == "succeeded" and fallback.get("scores", {}).get("modelFailure") is not None:
                    scored, use, repair_record = fallback, str(report), None
            if scored.get("status") != "succeeded":
                if timed_out:                                # nothing usable came out of a timed-out run: it scores 0 as it stands
                    scored, use, repair_record = None, None, None
                else:
                    return "failed", f"score:{scored.get('status')}:{scored.get('stage') or '; '.join(scored.get('diagnostics') or [])[:120]}", None
        dest = self.out / "runs" / task["cell"]
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True)
        if use:
            shutil.copy(use, dest / f"report{Path(use).suffix}")
            record["report"] = f"report{Path(use).suffix}"
        if repair_record:
            shutil.copy(repair_record, dest / "repair.json")
            record["repair"] = "repair.json"
        if scored:
            write_json(dest / "score.json", dict({"diagnostics": []}, **{k: v for k, v in scored.items() if not k.startswith("_")}))
            write_json(dest / "candidates.json", scored.get("candidates", []))
        else:
            write_json(dest / "score.json", {"status": "timeout", "scores": {"final": 0}, "note": "nothing delivered"})
        shutil.copy(agent_path, dest / "agent.json")
        write_json(dest / "run.json", record)
        final = (scored or {}).get("scores", {}).get("final", 0)
        outcome = "timeout" if timed_out else "valid"
        driver = dict(extra, outcome=outcome, attempt=attempt_no, id=task["cell"], saved=now_iso())
        if timed_out:
            driver.update(delivered=scored is not None, final=final, reason=record["validity"]["notes"])
        write_json(dest / "driver.json", driver)               # last: a directory without it is not a finished instance
        return outcome, "", dest

    def keep_for_diagnosis(self, cell, attempt_no, iid, report, call, reason):
        """Void and failed attempts keep the report, the command's output tail and the reason (small), for a look afterwards."""
        folder = self.out / "voids" / f"{cell}-a{attempt_no}"
        folder.mkdir(parents=True, exist_ok=True)
        if report is not None:
            shutil.copy(report, folder / f"report{Path(report).suffix}")
        (folder / "command-output.txt").write_text(f"exit {call['rc']}\n--- stdout (tail)\n{call['out'][-4000:]}\n--- stderr (tail)\n{call['err'][-4000:]}\n", encoding="utf-8")
        write_json(folder / "why.json", {"reason": reason, "instanceId": iid})


# ---------------------------------------------------------------- run loop

def log(out, text):
    line = f"{now_iso()} {text}"
    print(line, flush=True)
    with open(Path(out) / "events.log", "a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def pending_tasks(args, out, attempts):
    scenarios = args.scenarios or list(SCENARIOS)
    tasks = task_list(args.model, args.efforts, scenarios, args.n)
    return [t for t in tasks if not (Path(out) / "runs" / t["cell"] / "driver.json").exists() and attempts.counted(t["cell"]) < ATTEMPTS_PER_CELL]


def run_lane(runner, args, out, guard, attempts, tasks):
    """Run every pending cell, one attempt at a time, until all are done or a stop rule fires. Returns the exit code."""
    queue = list(tasks)
    while queue:
        if (Path(out) / "STOP").exists():
            log(out, "STOP file found; stopping before the next instance")
            return 0
        task = queue.pop(0)
        attempt_no = attempts.counted(task["cell"]) + 1
        log(out, f"start {task['cell']} attempt {attempt_no} ({len(queue)} cells after it)")
        runner.pending_stop = None
        outcome, reason, saved = runner.attempt(task, attempt_no, guard)
        attempts.add({"cell": task["cell"], "attempt": attempt_no, "outcome": outcome, "reason": reason})
        log(out, f"{task['cell']} attempt {attempt_no}: {outcome}{' ' + reason if reason else ''}")
        if runner.pending_stop:
            log(out, f"STOPPED: {runner.pending_stop}")
            return STOP_EXIT
        if outcome == "void" or outcome == "failed":
            if outcome == "void" and attempts.counted(task["cell"]) < ATTEMPTS_PER_CELL:
                queue.append(task)                              # a void instance goes to the end of the run
            limit = (NO_COMPLETION_STREAK if reason == "no-completion" else VOID_STREAK) if outcome == "void" else FAIL_STREAK
            same = attempts.streak(("void",), reason) if outcome == "void" else attempts.streak(("failed",))
            if same >= limit:
                log(out, f"STOPPED: {same} {outcome} attempts in a row ({reason}); check the cause, then run again")
                return 3
    return 0


# ---------------------------------------------------------------- pack and import

def pack_bundle(out, bundle_path):
    out = Path(out)
    runs = sorted(p for p in (out / "runs").glob("*") if (p / "driver.json").exists())
    if not runs:
        raise SystemExit(f"No finished instances under {out / 'runs'}.")
    files, cells = {}, []
    home = str(Path.home())
    private = 0
    for directory in runs:
        entry = {"dir": directory.name, "files": {}}
        for path in sorted(directory.iterdir()):
            if not path.is_file() or not SAFE_NAME.match(path.name):
                raise SystemExit(f"Unexpected entry in {directory}: {path.name}")
            data = path.read_bytes()
            private += home.encode() in data
            entry["files"][path.name] = {"sha256": sha256_bytes(data), "bytes": len(data)}
            files[f"runs/{directory.name}/{path.name}"] = data
        cells.append(entry)
    first = read_json(runs[0] / "run.json", {})
    driver = read_json(runs[0] / "driver.json", {})
    attempts = (out / "attempts.jsonl")
    if attempts.exists():
        files["attempts.jsonl"] = attempts.read_bytes()
    manifest = {"schema": 1, "tool": TOOL_VERSION, "created": now_iso(), "arw": first.get("arw"), "arwVersion": first.get("runtime", {}).get("arwVersion"),
                "harness": {"provider": first.get("settings", {}).get("modelProvider"), "version": driver.get("harnessVersion", "")}, "cells": cells}
    files["manifest.json"] = (json.dumps(manifest, indent=1, ensure_ascii=False) + "\n").encode("utf-8")
    bundle_path = Path(bundle_path)
    with tarfile.open(bundle_path, "w:gz") as tar:
        for name in ["manifest.json"] + sorted(n for n in files if n != "manifest.json"):
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(files[name]), 0, 0o644
            tar.addfile(info, io.BytesIO(files[name]))
    if private:
        print(f"warning: {private} file(s) contain the home directory path {home}; reports may quote paths of this machine", file=sys.stderr)
    return {"cells": len(cells), "path": str(bundle_path), "bytes": bundle_path.stat().st_size}


def read_bundle(bundle_path):
    """name -> bytes of a bundle, only known member names and regular files, with size caps; never extracts to disk."""
    files, total = {}, 0
    with tarfile.open(bundle_path, "r:*") as tar:
        for member in tar:
            parts = member.name.split("/")
            ok = member.isfile() and (member.name in ("manifest.json", "attempts.jsonl")
                                      or (len(parts) == 3 and parts[0] == "runs" and CELL_RE.match(parts[1]) and SAFE_NAME.match(parts[2])))
            if not ok:
                raise SystemExit(f"Bundle member not allowed: {member.name!r}")
            if member.size > MAX_FILE_BYTES or (total := total + member.size) > MAX_BUNDLE_BYTES:
                raise SystemExit("Bundle is larger than the allowed size.")
            files[member.name] = tar.extractfile(member).read()
    return files


def import_bundle(bundle_path, runs_dir, pin, replace=False, dry_run=False):
    files = read_bundle(bundle_path)
    if "manifest.json" not in files:
        raise SystemExit("Bundle has no manifest.json.")
    manifest = json.loads(files["manifest.json"])
    if manifest.get("schema") != 1:
        raise SystemExit(f"Unknown bundle schema {manifest.get('schema')!r}.")
    arw = manifest.get("arw") or {}
    if arw.get("commit") != pin["arw_commit"] or arw.get("fixtureTree") != pin["fixture_tree"]:
        raise SystemExit(f"Bundle was run on ARW {arw.get('commit')} / fixtures {arw.get('fixtureTree')}, not the pin {pin['arw_commit']} / {pin['fixture_tree']}.")
    runs_dir = Path(runs_dir)
    taken = {}
    for existing in runs_dir.glob("*/run.json") if runs_dir.is_dir() else []:
        if existing.parent.name.startswith(".import-"):
            continue
        taken[(read_json(existing, {}) or {}).get("id")] = existing.parent.name
    expected = set()
    for cell in manifest["cells"]:
        name = cell["dir"]
        if not CELL_RE.match(name):
            raise SystemExit(f"Bad cell directory name {name!r}.")
        if (runs_dir / name).exists() and not replace:
            raise SystemExit(f"{runs_dir / name} exists; use --replace to overwrite it.")
        for fname, meta in cell["files"].items():
            data = files.get(f"runs/{name}/{fname}")
            if data is None or sha256_bytes(data) != meta["sha256"]:
                raise SystemExit(f"{name}/{fname} is missing or does not match the manifest.")
            expected.add(f"runs/{name}/{fname}")
        run = json.loads(files[f"runs/{name}/run.json"])
        if run["arw"]["commit"] != pin["arw_commit"] or run["arw"]["fixtureTree"] != pin["fixture_tree"] or run["arw"]["treeDirty"]:
            raise SystemExit(f"{name}: run.json provenance differs from the pin.")
        if "driver.json" not in cell["files"]:
            raise SystemExit(f"{name}: no driver.json (unfinished instance).")
        if taken.get(run["id"]) not in (None, name):
            raise SystemExit(f"{name}: instance id {run['id']} already exists in {taken[run['id']]}.")
    extra = set(n for n in files if n.startswith("runs/")) - expected
    if extra:
        raise SystemExit(f"Bundle has files the manifest does not list: {sorted(extra)[:3]}")
    if dry_run:
        return {"cells": len(manifest["cells"]), "imported": 0}
    runs_dir.mkdir(parents=True, exist_ok=True)
    for cell in manifest["cells"]:
        name = cell["dir"]
        staging = runs_dir / f".import-{name}"
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir()
        for fname in cell["files"]:
            data = files[f"runs/{name}/{fname}"]
            if fname == "run.json":                          # report / repair point at the saved copies, as in the local layout
                run = json.loads(data)
                for key in ("report", "repair"):
                    if run.get(key):
                        run[key] = str((runs_dir / name / run[key]).resolve())
                data = (json.dumps(run, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
            (staging / fname).write_bytes(data)
        shutil.rmtree(runs_dir / name, ignore_errors=True)
        staging.rename(runs_dir / name)
    return {"cells": len(manifest["cells"]), "imported": len(manifest["cells"])}


# ---------------------------------------------------------------- commands

def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(s):
        s.add_argument("--arw", required=True, help="ARW checkout at the pinned commit")
        s.add_argument("--config", required=True, help="JSON config with the model command (see config.example.json)")
        s.add_argument("--model", required=True, help="model label used in names, e.g. hydrogen")
        s.add_argument("--model-id", help="value for settings.model (default: the label)")
        s.add_argument("--efforts", required=True, type=lambda t: [x for x in t.split(",") if x], help="comma-separated effort levels")
        s.add_argument("--scenarios", type=lambda t: [x for x in t.split(",") if x], help=f"comma-separated, default all: {','.join(SCENARIOS)}")
        s.add_argument("--n", type=int, default=N_DEFAULT, help=f"instances per cell (default {N_DEFAULT})")
        s.add_argument("--out", required=True, help="results directory (resumable)")
        s.add_argument("--work", help="scratch directory for instances (default <out>/work); use a short neutral path, it appears in the prompt")

    for name in ("check", "plan", "run"):
        common(sub.add_parser(name))
    sub.choices["check"].add_argument("--call", action="store_true", help="also send one tiny prompt to the command")
    for name in ("plan", "run"):
        sub.choices[name].add_argument("--limit-seconds", type=int, default=RUN_LIMIT_SECONDS, help="wall-clock limit of one instance (the suite's is 3600)")
    sub.choices["run"].add_argument("--ack", help="clear a usage-guard stop marker after checking its cause")
    pk = sub.add_parser("pack")
    pk.add_argument("--out", required=True)
    pk.add_argument("--bundle", help="bundle file (default <out>/bundle-<time>.tar.gz)")
    im = sub.add_parser("import")
    im.add_argument("bundle")
    im.add_argument("--runs-dir", required=True, help="local runs directory, e.g. .../v2/data/runs")
    im.add_argument("--replace", action="store_true")
    im.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)
    if args.cmd in ("check", "plan", "run"):
        unknown = [s for s in (args.scenarios or []) if s not in SCENARIOS]
        if unknown or not SAFE_NAME.match(args.model) or not all(SAFE_NAME.match(e) for e in args.efforts):
            p.error(f"bad scenario, model or effort name: {unknown or args.model}")
    return args


def setup_run(args):
    pin = load_pin()
    provenance = check_arw(Path(args.arw), pin)
    config = load_config(args.config)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    work = Path(args.work).resolve() if args.work else out / "work"
    work.mkdir(parents=True, exist_ok=True)
    return provenance, config, out, work


def show_plan(args, tasks, guard):
    limits = guard.expectation()
    print(f"cells pending: {len(tasks)} ({args.model}; efforts {','.join(args.efforts)}; scenarios {','.join(args.scenarios or SCENARIOS)}; n={args.n})")
    print(f"expected usage: {limits['calls']} model calls (one per instance, each up to {RUN_LIMIT_SECONDS // 60} min), about {limits['seconds'] / 3600:.1f} h of model time at "
          f"{EST_INSTANCE_SECONDS // 60} min per instance; tokens and quota are not known in advance (the first instance calibrates them)")
    print(f"the run stops itself above {limits['call_limit']} calls, {limits['second_limit'] / 3600:.1f} h of model time, or {MAX_OUT_TOKENS} output tokens in one call; "
          f"it stops after {VOID_STREAK} void attempts in a row ({NO_COMPLETION_STREAK} for no-completion) or {FAIL_STREAK} failed ones")


def on_term(*_):
    raise KeyboardInterrupt


def cmd_plan_or_run(args, execute):
    provenance, config, out, work = setup_run(args)
    attempts = Attempts(out)
    tasks = pending_tasks(args, out, attempts)
    guard = Guard(out, len(tasks))
    show_plan(args, tasks, guard)
    runner = Runner(args, config, provenance, out, work)
    if config.get("version_command"):
        done = subprocess.run(config["version_command"], capture_output=True, text=True, timeout=60)
        runner.harness_version = (done.stdout or done.stderr).strip().splitlines()[0] if (done.stdout or done.stderr).strip() else ""
        print(f"harness version: {runner.harness_version or 'unknown'}")
    if not execute:
        if tasks:
            variables = {k: f"<{k}>" for k in KNOWN_VARS} | {"model": args.model, "model_id": args.model_id or args.model, "effort": tasks[0]["effort"], "scenario": tasks[0]["scenario"]}
            variables.update({f"file.{name}": f"<side>/{name}" for name in config["files"]})
            print("first command: " + " ".join(render(part, variables) for part in config["command"]))
        return 0
    guard.refuse_if_stopped(args.ack)
    if not tasks:
        print("nothing pending")
        return 0
    signal.signal(signal.SIGTERM, on_term)
    try:
        code = run_lane(runner, args, out, guard, attempts, tasks)
    except KeyboardInterrupt:
        log(out, "interrupted; run again to resume")
        code = 130
    finally:
        if not args.work:
            shutil.rmtree(work, ignore_errors=True)
    return code


def cmd_check(args):
    provenance, config, out, work = setup_run(args)
    for tool in (["node", "--version"], ["git", "--version"]):
        done = subprocess.run(tool, capture_output=True, text=True, timeout=30)
        print(f"{tool[0]}: {done.stdout.strip()}")
    print(f"ARW {provenance['arwVersion']} at {provenance['commit'][:10]}, fixtures {provenance['fixtureTree'][:10]}: matches the pin")
    probe = Runner(args, config, provenance, out, work)
    for scenario in (args.scenarios or SCENARIOS):
        target = work / f"check-{scenario}" / "inst"
        result = probe.arw(["setup", probe.scenario_dir(scenario), target])
        print(f"setup {scenario}: {result.get('status')}")
        shutil.rmtree(target.parent, ignore_errors=True)
        if result.get("status") != "succeeded":
            return 1
    if args.call:
        sandbox = work / "check-call"
        sandbox.mkdir(exist_ok=True)
        prompt = "Reply with the single word OK. Do not use any tool."
        variables = {k: f"<{k}>" for k in KNOWN_VARS} | {"prompt": prompt, "cwd": str(sandbox), "model": args.model, "model_id": args.model_id or args.model,
                                                       "effort": args.efforts[0], "report_dir": str(sandbox), "report_path": str(sandbox / "r.txt")}
        side = work / "check-side"
        side.mkdir(exist_ok=True)
        (side / "prompt.md").write_text(prompt, encoding="utf-8")
        variables["prompt_file"] = side / "prompt.md"
        for name, template in config["files"].items():
            (side / name).write_text(render(template, variables) if isinstance(template, str) else json.dumps(render(template, variables)), encoding="utf-8")
            variables[f"file.{name}"] = side / name
        uses_prompt = any("{prompt}" in part or "{prompt_file}" in part for part in config["command"])
        call = call_model([render(p, variables) for p in config["command"]], str(sandbox), dict(os.environ), None if uses_prompt else prompt, 300)
        print(f"call: exit {call['rc']}, {call['seconds']:.1f} s, timed out {call['timed_out']}\n--- stdout\n{call['out'][-600:]}\n--- stderr\n{call['err'][-300:]}")
        shutil.rmtree(sandbox, ignore_errors=True)
        shutil.rmtree(side, ignore_errors=True)
        if call["timed_out"] or call["rc"] != 0:
            return 1
    if not args.work:
        shutil.rmtree(work, ignore_errors=True)
    return 0


def main(argv=None):
    args = parse_args(argv)
    if args.cmd == "check":
        return cmd_check(args)
    if args.cmd == "plan":
        return cmd_plan_or_run(args, execute=False)
    if args.cmd == "run":
        return cmd_plan_or_run(args, execute=True)
    if args.cmd == "pack":
        out = Path(args.out)
        bundle = args.bundle or out / f"bundle-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
        print(json.dumps(pack_bundle(out, bundle)))
        return 0
    print(json.dumps(import_bundle(args.bundle, args.runs_dir, load_pin(), args.replace, args.dry_run)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
