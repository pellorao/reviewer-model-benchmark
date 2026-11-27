"""Build helpers for the question bank: branch pool, split, SZZ pairs, model calls.

Generic code only (no question content).  Intermediate data goes to
.bank/notes/work/ and the finished items to .bank/items/, .bank/keys/.
Models are called only through claude-guard (Claude subscription).
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BANK = ROOT / ".bank"
WORK = BANK / "notes" / "work"
SRC = Path(os.environ.get("BANK_SOURCE", Path.home() / "projects" / "kaze-workshop"))
CODE = re.compile(r"\.(py|sh|js|mjs|go|html|ps1|json)$")
MIN_LINES, MAX_LINES, MAX_COMMITS = 30, 800, 10
CLEAN_AGE_DAYS = 7
RESERVE_PERCENT = 40
GUARD = Path.home() / ".claude" / "bin" / "claude-guard"


def git(*args, ok=False, cwd=SRC):
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if done.returncode and not ok:
        raise RuntimeError(f"git {args[0]} failed")
    return done.stdout


def stable(text):
    return int(hashlib.sha256(text.encode()).hexdigest(), 16)


def item_id(kind, key):
    return "w3-" + hashlib.sha256(f"{kind}:{key}".encode()).hexdigest()[:12]


def branches():
    """Merged linear branches of 1..MAX_COMMITS commits: {merge: info}."""
    found = {}
    for line in git("log", "--merges", "--format=%H %P %ct").splitlines():
        parts = line.split()
        if len(parts) != 4:
            continue
        merge, p1, p2, stamp = parts
        base = git("merge-base", p1, p2).strip()
        rows = git("rev-list", "--reverse", "--parents", f"{base}..{p2}").splitlines()
        if not rows or len(rows) > MAX_COMMITS or any(len(r.split()) != 2 for r in rows):
            continue
        stat = git("diff", "--numstat", base, p2).splitlines()
        files = [s.split("\t") for s in stat]
        lines = sum(int(a) + int(b) for a, b, _ in files if a.isdigit() and b.isdigit())
        code = [f[2] for f in files if CODE.search(f[2]) and "test" not in f[2].lower()]
        found[merge] = {"base": base, "tip": p2, "commits": [r.split()[0] for r in rows],
                        "lines": lines, "code_files": code, "merged": int(stamp)}
    return found


def usable(info):
    return MIN_LINES <= info["lines"] <= MAX_LINES and bool(info["code_files"])


def fix_pairs(by_commit):
    """(introducing branch merge, fix commit) pairs found by blaming the lines a fix removed."""
    fixes = git("log", "--no-merges", "-i", "-E", "--grep=fix|修|regress|bug|wrong|broken",
                "--format=%H").split()
    pairs = {}
    for fix in fixes:
        parent = git("rev-parse", fix + "^").strip()
        current = None
        for row in git("diff", "-U0", parent, fix).splitlines():
            if row.startswith("--- "):
                current = row[6:] if row.startswith("--- a/") else None
            match = re.match(r"@@ -(\d+)(?:,(\d+))? ", row)
            if not (match and current and CODE.search(current) and "test" not in current.lower()):
                continue
            start, count = int(match.group(1)), int(match.group(2) or 1)
            if count == 0:  # pure insertion: the code it patches is the lines around it
                start, count = max(start, 1), 2
            blame = git("blame", "-l", "-w", "-L", f"{start},{start + count - 1}", parent, "--",
                        current, ok=True)
            for entry in blame.splitlines():
                owner = by_commit.get(entry.split()[0].lstrip("^"))
                if owner and fix not in by_commit:
                    pairs.setdefault((owner, fix), set()).add(current)
    return {k: sorted(v) for k, v in pairs.items()}


def llm(prompt, max_usd=0.8, effort="high"):
    """One claude -p call through claude-guard; returns the result text."""
    env = {**os.environ, "TMPDIR": os.environ.get("TMPDIR", "/tmp/reviewer-bench/v3-bank")}
    done = subprocess.run(
        [str(GUARD), "--label", "reviewer-bench/v3-bank", "--max-usd", str(max_usd),
         "--max-starts", "1000", "--per-min", "600", "--", "-p", "--model", "sonnet",
         "--effort", effort, "--output-format", "stream-json", "--verbose",
         "--permission-mode", "dontAsk"],
        input=prompt, capture_output=True, text=True, cwd="/tmp/reviewer-bench/v3-bank", env=env)
    if done.returncode:
        raise RuntimeError(f"claude-guard rc={done.returncode}")
    result = None
    for row in done.stdout.splitlines():
        try:
            data = json.loads(row)
        except ValueError:
            continue
        if data.get("type") == "result":
            result = data
    if not result or result.get("is_error"):
        raise RuntimeError("model call failed")
    return result["result"]


def json_from(text):
    """First top-level JSON object in a model answer."""
    start = text.find("{")
    depth = 0
    for i in range(start, len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return json.loads(text[start:i + 1])
    raise ValueError("no JSON object")


def split_pool(pool):
    """Stratified 60/40 split by hash rank inside each stratum; branches never straddle."""
    side = {}
    for stratum in sorted({i["stratum"] for i in pool.values()}):
        merges = sorted((m for m, i in pool.items() if i["stratum"] == stratum), key=stable)
        cut = round(len(merges) * RESERVE_PERCENT / 100)
        for number, merge in enumerate(merges):
            side[merge] = "reserve" if number < cut else "dev"
    return side


SEVERITY_RULES = """Severity (landing mode, correctness axis only): `high` and `medium` each need a concrete input or event sequence that triggers the failure in normal use (one user, the normal order of install and deploy). A failure that needs concurrent installs, a deploy window, a hostile local process or an abnormally long input is `low`. `high` is a failure of one of these kinds: the change cannot run, install or start; it crashes or hangs the machine or a service, or exhausts memory, disk, processes or time (including work added to a path that runs on every call, hook or timer tick); it loses or corrupts data; it leaks a credential or private data; it costs a large amount of money or quota. Any other defect that meets the scenario rule is `medium`. A severe failure that needs an unlikely input is graded by impact times likelihood, and when the product is very low it is `low`."""


def read_at(rev, path):
    return git("show", f"{rev}:{path}", ok=True)


def diff_text(base, tip):
    return git("diff", "--no-color", "-U6", base, tip)
