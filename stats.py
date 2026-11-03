"""Statistics and cost rules for the benchmark page: pure Python, no Plotly or HTML.

`extract(results, pricing)` turns a benchmark results snapshot into one record per configuration.
"""

import json
import math
import statistics
from pathlib import Path


RESULTS_SCHEMA_VERSION = 1
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
MODEL_NAMES = {
    "gpt-6.1-sol": "GPT-6.1 Sol",
    "gpt-6-luna": "GPT-6 Luna",
    "opus": "Claude Opus 5.5",
    "sonnet": "Claude Sonnet 5.5",
    "haiku": "Claude Haiku 5.5",
    "deepseek-flash": "DeepSeek V4.1 Flash",
    "strata-iq3_xxs": "Strata IQ3_XXS",
}
HARNESS_NAMES = {"codex": "Codex", "claude-code": "Claude Code"}
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


def _openai_cost(instance, config, pricing):
    tokens = instance["tokens"]
    if tokens.get("cacheWriteInput"):
        # pricing.json has no cache-write rule in use; failing beats silently under-pricing.
        raise ValueError(f"OpenAI instance with cache-write tokens is not priced: {instance['id']}")
    if not all(finite_number(tokens.get(key)) for key in TOKEN_KEYS):
        return None, False
    rule = pricing_rule(pricing, "openai", config)
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


COST_RULES = {"deepseek": _recorded_cost, "anthropic": _recorded_cost,
              "openai": _openai_cost, "strata": _local_cost}


def pricing_rule(pricing, section, config):
    try:
        return pricing[section][config["model"]]
    except KeyError:
        raise ValueError(f"No {section} pricing rule for model {config['model']} "
                         f"(configuration {config['key']})") from None


def instance_cost(instance, config, pricing):
    """Return (USD, lower bound) for one instance, or (None, False) when unknown."""
    rule = COST_RULES.get(config["vendor"])
    if rule is None:
        raise ValueError(f"No cost rule for vendor: {config['vendor']}")
    return rule(instance, config, pricing)


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
    speeds, speed_parts, speed_counts, speed_bounds = {}, {}, {}, {}
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
        speed_parts[key] = (mean_of(tokens), mean_of(seconds)) if speeds[key] is not None else None
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
        "speeds": speeds, "speedParts": speed_parts, "speedCounts": speed_counts,
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
    token_cells = [cells[key]["tokens"] for key, _, _ in REVIEWERS if cells[key]["tokens"]]
    speeds = {}
    for speed in SPEED_KEYS:
        # Tokens and seconds of one average run per task, summed over the four tasks.
        task_parts = [cells[key]["speedParts"][speed] for key, _, _ in REVIEWERS
                      if cells[key]["speedParts"][speed] is not None]
        speeds[speed] = (sum(part[0] for part in task_parts) / sum(part[1] for part in task_parts)
                         if task_parts else None)
    return {
        "score": score, "half": half, "minutes": minutes, "timeCount": time_count,
        "cost": cost, "costCount": cost_count,
        "costLowerBound": any(cells[key]["costLowerBound"] for key, _, _ in REVIEWERS),
        "tokens": ({key: mean_of([tokens[key] for tokens in token_cells]) for key in TOKEN_KEYS}
                   if token_cells else None),
        "speeds": speeds,
    }


def extract(results, pricing):
    """Group the benchmark's main-statistic instances into configuration records."""
    if not isinstance(results, dict) or results.get("meta", {}).get("schemaVersion") != RESULTS_SCHEMA_VERSION:
        raise ValueError(f"Expected a schema-version-{RESULTS_SCHEMA_VERSION} benchmark results file.")
    scenario_reviewers = {scenario["id"]: scenario["reviewerId"] for scenario in results["scenarios"]}
    if sorted(scenario_reviewers.values()) != sorted(key for key, _, _ in REVIEWERS):
        raise ValueError("The results must contain exactly the four weighted reviewers.")
    # Phase-3 supplement configurations (GPT-6 Luna xhigh / max) are plotted like main ones.
    configs = {config["key"]: config for config in results["configs"] if config["kind"] in ("main", "phase3")}
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
