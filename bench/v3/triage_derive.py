"""Derive triage questions from landing-review runs on the development pool.

A triage question is one `high` opinion that a landing review raised on a
land-first question, with its diff.  Its gold label comes from the answer key,
not from a model:

  matches a key defect (same file, line windows within WINDOW lines) whose
  key severity is `high`                       -> fix-now
  matches a key defect of lower severity       -> follow-up
  matches a known false positive of the key,
  or matches nothing and the blind judge rules
  it not valid (or no judge ruling exists yet) -> ignore
  matches nothing and the judge rules it a valid new defect:
  gold is the judge's severity (high -> fix-now, else follow-up)

Questions are drawn once per (question id, opinion fingerprint) and only from
runs made while the development pool was being used, so the triage pool never
depends on the test set.  Inputs are plain dicts; no model is called here.
"""

WINDOW = 5
LABELS = ("fix-now", "follow-up", "ignore")


def overlaps(finding, spot):
    return (finding["file"] == spot["file"]
            and finding["start"] <= spot["end"] + WINDOW and finding["end"] >= spot["start"] - WINDOW)


def gold(finding, key, ruling=None):
    """Gold label of one opinion; `ruling` is the judge's {"valid": bool, "severity": str} or None."""
    for defect in key.get("defects", ()):
        if any(overlaps(finding, spot) for spot in defect["locations"]):
            return "fix-now" if defect["severity"] == "high" else "follow-up"
    for false in key.get("known_false", ()):
        if any(overlaps(finding, spot) for spot in false["locations"]):
            return "ignore"
    if ruling and ruling.get("valid"):
        return "fix-now" if ruling.get("severity") == "high" else "follow-up"
    return "ignore"


def derive(runs, keys, rulings=None):
    """Return triage questions [{question, fingerprint, finding, gold}] from landing runs.

    runs: [{"question": id, "findings": [{"fingerprint", "severity", "file", "start", "end"}]}]
    keys: {question id: key}; rulings: {(question id, fingerprint): ruling}
    """
    seen, out = set(), []
    for run in runs:
        for finding in run["findings"]:
            if finding["severity"] != "high":
                continue
            ident = (run["question"], finding["fingerprint"])
            if ident in seen or run["question"] not in keys:
                continue
            seen.add(ident)
            label = gold(finding, keys[run["question"]], (rulings or {}).get(ident))
            out.append({"question": run["question"], "fingerprint": finding["fingerprint"],
                        "finding": finding, "gold": label})
    return out
