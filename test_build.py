"""Checks for the benchmark page's statistics, cost rules and page assembly."""

import math
import statistics
import unittest

from build import (LOCAL_COST, OPENAI_RATES, PRICING, REVIEWERS, composite, extract,
                   instance_cost, page, summarize_cell, t_quantile)


SCENARIOS = [{"id": f"scenario-{index}", "reviewerId": key}
             for index, (key, _, _) in enumerate(REVIEWERS)]
CONFIGS = {
    "openai": {"key": "codex/gpt-6.1-sol/low", "harness": "codex", "model": "gpt-6.1-sol",
               "effort": "low", "vendor": "openai", "kind": "main"},
    "anthropic": {"key": "claude-code/opus/high", "harness": "claude-code", "model": "opus",
                  "effort": "high", "vendor": "anthropic", "kind": "main"},
    "strata": {"key": "codex/strata-iq3_xxs/low", "harness": "codex", "model": "strata-iq3_xxs",
               "effort": "low", "vendor": "strata", "kind": "main"},
}


def instance(score, seconds=100.0, tokens=(1000, 9000, 200), speeds=None, cost=None,
             config="codex/gpt-6.1-sol/low", scenario="scenario-0", status="final",
             in_main=True, supplementary=None, lower_bound=False):
    token_values = dict(zip(("uncachedInput", "cachedInput", "output"), tokens or (None,) * 3))
    if speeds is None:
        speeds = {"taskOutput": token_values["output"] / seconds if tokens else None,
                  "taskInput": token_values["uncachedInput"] / seconds if tokens else None,
                  "engineOutput": None, "engineInput": None}
    return {"id": f"{config}/{scenario}/{score}", "configKey": config, "scenario": scenario,
            "supplementaryNote": supplementary, "selection": {"inMain": in_main},
            "validity": {"valid": True}, "scoring": {"score": score, "status": status},
            "time": {"durationSeconds": seconds},
            "tokens": {**token_values, "lowerBound": lower_bound},
            "speeds": {**speeds, "lowerBounds": []}, "cost": cost}


def results(instances, configs=(CONFIGS["openai"],)):
    return {"meta": {"schemaVersion": 1}, "scenarios": SCENARIOS, "configs": list(configs),
            "instances": instances}


def full_config(config, scores=(0.6, 0.8), **fields):
    return [instance(score, config=config, scenario=scenario["id"], **fields)
            for scenario in SCENARIOS for score in scores]


class StatisticsTests(unittest.TestCase):
    def test_t_quantile_matches_reference_values(self):
        self.assertAlmostEqual(t_quantile(0.975, 4), 2.776445, places=5)
        self.assertAlmostEqual(t_quantile(0.975, 9), 2.262157, places=5)
        self.assertAlmostEqual(t_quantile(0.975, 10_000), 1.960201, places=4)

    def test_cell_keeps_negative_scores_and_counts_failures(self):
        scores = [0.9, -0.4, 0.0, 0.5, 0.7]
        cell = summarize_cell([instance(score, status="modelFailure" if score == 0 else "final")
                               for score in scores], CONFIGS["openai"])
        self.assertAlmostEqual(cell["mean"], statistics.mean(scores))
        self.assertEqual(cell["negatives"], 1)
        self.assertEqual(cell["failures"], 1)
        expected_half = t_quantile(0.975, 4) * statistics.stdev(scores) / math.sqrt(5)
        self.assertAlmostEqual(cell["half"], expected_half)

    def test_speed_is_total_tokens_over_total_seconds(self):
        cell = summarize_cell([instance(0.5, seconds=10, tokens=(50, 0, 100)),
                               instance(0.5, seconds=100, tokens=(50, 0, 300))],
                              CONFIGS["openai"])
        # Rates are 10 and 3 tok/s; their mean (6.5) would weight the short run too heavily.
        self.assertAlmostEqual(cell["speeds"]["taskOutput"], 400 / 110)
        self.assertAlmostEqual(cell["speeds"]["taskInput"], 100 / 110)
        self.assertIsNone(cell["speeds"]["engineInput"])

    def test_engine_speed_uses_each_runs_own_seconds(self):
        speeds = {"taskOutput": 1.0, "taskInput": 1.0, "engineOutput": 20.0, "engineInput": None}
        other = {**speeds, "engineOutput": 50.0}
        cell = summarize_cell([instance(0.5, tokens=(10, 0, 200), speeds=speeds),
                               instance(0.5, tokens=(10, 0, 500), speeds=other)],
                              CONFIGS["openai"])
        self.assertAlmostEqual(cell["speeds"]["engineOutput"], 700 / (10 + 10))

    def test_composite_score_interval_and_pooled_speed(self):
        record = extract(results(
            [instance(score, seconds=seconds, config=CONFIGS["openai"]["key"], scenario=scenario["id"],
                      tokens=(100, 0, output))
             for scenario, seconds, output in zip(SCENARIOS, (10, 20, 30, 40), (100, 100, 100, 700))
             for score in (0.4, 0.8)]))[0]
        self.assertAlmostEqual(record["score"], 60.0)
        variance = sum(weight ** 2 * (statistics.stdev([0.4, 0.8]) / math.sqrt(2)) ** 2
                       for _, _, weight in REVIEWERS)
        degrees = variance ** 2 / sum((weight ** 2 * 0.04) ** 2 / 1 for _, _, weight in REVIEWERS)
        self.assertAlmostEqual(record["half"], 100 * t_quantile(0.975, degrees) * math.sqrt(variance))
        self.assertAlmostEqual(record["minutes"], 25 / 60)
        self.assertAlmostEqual(record["speeds"]["taskOutput"], 1000 / 100)

    def test_missing_values_skip_only_that_instance(self):
        cell = summarize_cell([instance(0.0, tokens=None, status="modelFailure"),
                               instance(0.6, tokens=(10, 20, 30))], CONFIGS["openai"])
        self.assertEqual(cell["n"], 2)
        self.assertEqual(cell["tokenCount"], 1)
        self.assertEqual(cell["tokens"]["output"], 30)
        self.assertEqual(cell["costCount"], 1)
        self.assertEqual(cell["timeCount"], 2)

    def test_composite_resource_values_average_available_tasks(self):
        cells = {key: {"mean": 0.5, "se": None, "n": 1, "minutes": minutes, "cost": None,
                       "costLowerBound": False, "tokens": None,
                       "speedParts": dict.fromkeys(("taskOutput", "taskInput", "engineOutput",
                                                    "engineInput"))}
                 for (key, _, _), minutes in zip(REVIEWERS, (1.0, None, 3.0, 5.0))}
        result = composite(cells)
        self.assertIsNone(result["half"])
        self.assertAlmostEqual(result["minutes"], 3.0)
        self.assertEqual(result["timeCount"], 3)


class CostTests(unittest.TestCase):
    def test_openai_prices_tokens_at_api_rates(self):
        usd, lower = instance_cost(instance(0.5, tokens=(1_000_000, 2_000_000, 100_000)),
                                   CONFIGS["openai"])
        uncached, cached, output = OPENAI_RATES["gpt-6.1-sol"]
        self.assertAlmostEqual(usd, uncached + 2 * cached + 0.1 * output)
        self.assertFalse(lower)

    def test_anthropic_and_deepseek_use_instance_cost(self):
        usd, lower = instance_cost(instance(0.5, cost={"usd": 0.42, "lowerBound": True}),
                                   CONFIGS["anthropic"])
        self.assertEqual((usd, lower), (0.42, True))
        self.assertEqual(instance_cost(instance(0.5), CONFIGS["anthropic"]), (None, False))

    def test_local_cost_is_running_cost_and_positive(self):
        rule = LOCAL_COST["strata-iq3_xxs"]
        usd, _ = instance_cost(instance(0.5, seconds=3600), CONFIGS["strata"])
        self.assertAlmostEqual(usd, rule["wallPowerWatts"] / 1000 * rule["electricityUsdPerKwh"]
                               + rule["maintenanceUsdPerHour"])
        self.assertGreater(usd, 0)
        self.assertEqual(PRICING["schemaVersion"], 2)


class ExtractTests(unittest.TestCase):
    def test_only_main_selection_without_supplementary_note_counts(self):
        key = CONFIGS["openai"]["key"]
        extra = [instance(-1.0, config=key, in_main=False),
                 instance(-1.0, config=key, supplementary="high requested as medium")]
        record = extract(results(full_config(key) + extra))[0]
        self.assertEqual([cell["n"] for cell in record["cells"].values()], [2, 2, 2, 2])
        self.assertAlmostEqual(record["score"], 70.0)

    def test_main_instance_without_valid_score_is_rejected(self):
        bad = full_config(CONFIGS["openai"]["key"])
        bad[0]["validity"]["valid"] = False
        with self.assertRaises(ValueError):
            extract(results(bad))

    def test_missing_task_is_rejected(self):
        partial = [item for item in full_config(CONFIGS["openai"]["key"])
                   if item["scenario"] != "scenario-3"]
        with self.assertRaises(ValueError):
            extract(results(partial))

    def test_page_contains_every_chart(self):
        data = results(full_config(CONFIGS["openai"]["key"])
                       + full_config(CONFIGS["anthropic"]["key"], cost={"usd": 0.3})
                       + full_config(CONFIGS["strata"]["key"]),
                       configs=CONFIGS.values())
        html = page(data)
        for chart_id in ("benchmark-bars-effort", "benchmark-scatter-1", "benchmark-scatter-2",
                         "benchmark-scatter-3", "benchmark-bars-grouped", "benchmark-bars-minutes",
                         "benchmark-bars-tokens", "benchmark-bars-cost", "benchmark-bars-speed"):
            self.assertIn(f'id="{chart_id}"', html)
        self.assertIn("套餐运行，参考 API 价", html)


if __name__ == "__main__":
    unittest.main()
