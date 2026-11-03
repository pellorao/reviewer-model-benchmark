"""Checks for the benchmark page's statistics, cost rules and page assembly."""

import copy
import math
import statistics
import unittest

from stats import (REVIEWERS, TOKEN_KEYS, composite, extract, instance_cost, load_pricing,
                   summarize_cell, t_quantile)

try:  # The statistics tests need no plotly; only the page tests do.
    import build
except ModuleNotFoundError as error:
    if error.name != "plotly" and not (error.name or "").startswith("plotly."):
        raise
    build = None

PRICING = load_pricing()
OPENAI_RATES = {model: tuple(rule["rates"][key] for key in TOKEN_KEYS)
                for model, rule in PRICING["openai"].items()}
LOCAL_COST = PRICING["localRunningCost"]

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
                               for score in scores], CONFIGS["openai"], PRICING)
        self.assertAlmostEqual(cell["mean"], statistics.mean(scores))
        self.assertEqual(cell["negatives"], 1)
        self.assertEqual(cell["failures"], 1)
        expected_half = t_quantile(0.975, 4) * statistics.stdev(scores) / math.sqrt(5)
        self.assertAlmostEqual(cell["half"], expected_half)

    def test_speed_is_total_tokens_over_total_seconds(self):
        cell = summarize_cell([instance(0.5, seconds=10, tokens=(50, 0, 100)),
                               instance(0.5, seconds=100, tokens=(50, 0, 300))],
                              CONFIGS["openai"], PRICING)
        # Rates are 10 and 3 tok/s; their mean (6.5) would weight the short run too heavily.
        self.assertAlmostEqual(cell["speeds"]["taskOutput"], 400 / 110)
        self.assertAlmostEqual(cell["speeds"]["taskInput"], 100 / 110)
        self.assertIsNone(cell["speeds"]["engineInput"])

    def test_engine_speed_uses_each_runs_own_seconds(self):
        speeds = {"taskOutput": 1.0, "taskInput": 1.0, "engineOutput": 20.0, "engineInput": None}
        other = {**speeds, "engineOutput": 50.0}
        cell = summarize_cell([instance(0.5, tokens=(10, 0, 200), speeds=speeds),
                               instance(0.5, tokens=(10, 0, 500), speeds=other)],
                              CONFIGS["openai"], PRICING)
        self.assertAlmostEqual(cell["speeds"]["engineOutput"], 700 / (10 + 10))

    def test_composite_score_interval(self):
        record = extract(results(
            [instance(score, seconds=seconds, config=CONFIGS["openai"]["key"], scenario=scenario["id"],
                      tokens=(100, 0, output))
             for scenario, seconds, output in zip(SCENARIOS, (10, 20, 30, 40), (100, 100, 100, 700))
             for score in (0.4, 0.8)]), PRICING)[0]
        self.assertAlmostEqual(record["score"], 60.0)
        variance = sum(weight ** 2 * (statistics.stdev([0.4, 0.8]) / math.sqrt(2)) ** 2
                       for _, _, weight in REVIEWERS)
        degrees = variance ** 2 / sum((weight ** 2 * 0.04) ** 2 / 1 for _, _, weight in REVIEWERS)
        self.assertAlmostEqual(record["half"], 100 * t_quantile(0.975, degrees) * math.sqrt(variance))
        self.assertAlmostEqual(record["minutes"], 25 / 60)

    def test_missing_values_skip_only_that_instance(self):
        cell = summarize_cell([instance(0.0, tokens=None, status="modelFailure"),
                               instance(0.6, tokens=(10, 20, 30))], CONFIGS["openai"], PRICING)
        self.assertEqual(cell["n"], 2)
        self.assertEqual(cell["tokenCount"], 1)
        self.assertEqual(cell["tokens"]["output"], 30)
        self.assertEqual(cell["costCount"], 1)
        self.assertEqual(cell["timeCount"], 2)

    def test_composite_resource_values_average_available_tasks(self):
        cells = {key: {"mean": 0.5, "se": None, "n": 1, "minutes": minutes, "cost": None,
                       "costLowerBound": False, "tokens": None}
                 for (key, _, _), minutes in zip(REVIEWERS, (1.0, None, 3.0, 5.0))}
        result = composite(cells)
        self.assertIsNone(result["half"])
        self.assertAlmostEqual(result["minutes"], 3.0)
        self.assertEqual(result["timeCount"], 3)


class CostTests(unittest.TestCase):
    def test_openai_prices_tokens_at_api_rates(self):
        usd, lower = instance_cost(instance(0.5, tokens=(1_000_000, 2_000_000, 100_000)),
                                   CONFIGS["openai"], PRICING)
        uncached, cached, output = OPENAI_RATES["gpt-6.1-sol"]
        self.assertAlmostEqual(usd, uncached + 2 * cached + 0.1 * output)
        self.assertFalse(lower)

    def test_anthropic_and_deepseek_use_instance_cost(self):
        usd, lower = instance_cost(instance(0.5, cost={"usd": 0.42, "lowerBound": True}),
                                   CONFIGS["anthropic"], PRICING)
        self.assertEqual((usd, lower), (0.42, True))
        self.assertEqual(instance_cost(instance(0.5), CONFIGS["anthropic"], PRICING), (None, False))

    def test_local_cost_is_running_cost_and_positive(self):
        rule = LOCAL_COST["strata-iq3_xxs"]
        usd, _ = instance_cost(instance(0.5, seconds=3600), CONFIGS["strata"], PRICING)
        self.assertAlmostEqual(usd, rule["wallPowerWatts"] / 1000 * rule["electricityUsdPerKwh"]
                               + rule["maintenanceUsdPerHour"])
        self.assertGreater(usd, 0)
        self.assertEqual(PRICING["schemaVersion"], 2)

    def test_pricing_is_injected(self):
        cheaper = copy.deepcopy(PRICING)
        cheaper["openai"]["gpt-6.1-sol"]["rates"]["output"] = 0.0
        tokens = (0, 0, 1_000_000)
        self.assertGreater(instance_cost(instance(0.5, tokens=tokens), CONFIGS["openai"], PRICING)[0], 0)
        self.assertEqual(instance_cost(instance(0.5, tokens=tokens), CONFIGS["openai"], cheaper)[0], 0)

    def test_openai_cache_write_tokens_are_rejected_not_ignored(self):
        item = instance(0.5)
        item["tokens"]["cacheWriteInput"] = 5000
        with self.assertRaisesRegex(ValueError, "cache-write"):
            instance_cost(item, CONFIGS["openai"], PRICING)
        item["tokens"]["cacheWriteInput"] = None
        instance_cost(item, CONFIGS["openai"], PRICING)

    def test_unknown_model_or_vendor_is_a_clear_error(self):
        unknown = {**CONFIGS["openai"], "model": "gpt-9"}
        with self.assertRaisesRegex(ValueError, "gpt-9"):
            instance_cost(instance(0.5), unknown, PRICING)
        with self.assertRaisesRegex(ValueError, "vendor"):
            instance_cost(instance(0.5), {**CONFIGS["openai"], "vendor": "other"}, PRICING)

class ExtractTests(unittest.TestCase):
    def test_only_main_selection_without_supplementary_note_counts(self):
        key = CONFIGS["openai"]["key"]
        extra = [instance(-1.0, config=key, in_main=False),
                 instance(-1.0, config=key, supplementary="high requested as medium")]
        record = extract(results(full_config(key) + extra), PRICING)[0]
        self.assertEqual([cell["n"] for cell in record["cells"].values()], [2, 2, 2, 2])
        self.assertAlmostEqual(record["score"], 70.0)

    def test_phase3_xhigh_configuration_is_plotted(self):
        config = {**CONFIGS["openai"], "key": "codex/gpt-6-luna/xhigh", "model": "gpt-6-luna",
                  "effort": "xhigh", "kind": "phase3"}
        records = extract(results(full_config(CONFIGS["openai"]["key"]) + full_config(config["key"]),
                                  configs=(CONFIGS["openai"], config)), PRICING)
        self.assertEqual(sorted(record["effort"] for record in records), ["low", "xhigh"])

    def test_main_instance_without_valid_score_is_rejected(self):
        bad = full_config(CONFIGS["openai"]["key"])
        bad[0]["validity"]["valid"] = False
        with self.assertRaises(ValueError):
            extract(results(bad), PRICING)

    def test_missing_task_is_rejected(self):
        partial = [item for item in full_config(CONFIGS["openai"]["key"])
                   if item["scenario"] != "scenario-3"]
        with self.assertRaises(ValueError):
            extract(results(partial), PRICING)

    def test_empty_configuration_set_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no main"):
            extract(results([], configs=()), PRICING)

    def test_main_instance_of_unlisted_configuration_is_rejected(self):
        stray = full_config(CONFIGS["openai"]["key"]) + [instance(0.5, config="codex/other/low")]
        with self.assertRaisesRegex(ValueError, "unexpected configuration"):
            extract(results(stray), PRICING)


@unittest.skipIf(build is None, "plotly is not installed")
class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = results(full_config(CONFIGS["openai"]["key"])
                           + full_config(CONFIGS["anthropic"]["key"], cost={"usd": 0.3})
                           + full_config(CONFIGS["strata"]["key"]),
                           configs=CONFIGS.values())
        cls.html = build.page(cls.data, PRICING)

    def test_page_contains_every_chart(self):
        for chart_id in ("benchmark-bars-effort", "benchmark-scatter-1", "benchmark-scatter-2",
                         "benchmark-scatter-3", "benchmark-bars-grouped", "benchmark-bars-minutes",
                         "benchmark-bars-tokens", "benchmark-bars-cost", "benchmark-bars-speed"):
            self.assertIn(f'id="{chart_id}"', self.html)
        self.assertIn("套餐运行, 参考 API 价", self.html)

    def test_method_text_follows_pricing_and_weights(self):
        pricing = copy.deepcopy(PRICING)
        pricing["openai"]["gpt-6-luna"]["rates"]["output"] = 0.75
        pricing["localRunningCost"]["strata-iq3_xxs"]["wallPowerWatts"] = 450
        pricing["checkedAt"] = "2030-01-02"
        copy_text = build.page_copy(pricing)
        self.assertIn("$0.10 / $0.01 / $0.75", copy_text["en"]["method_cost"])
        self.assertIn("450 W × $0.174 per kWh", copy_text["en"]["method_cost"])
        self.assertIn("450 W × 全球家庭平均电价 $0.174/kWh", copy_text["zh"]["method_cost"])
        self.assertIn("2030-01-02", copy_text["zh"]["method_cost"])
        self.assertIn("0.20 Code Standards + 0.20 Code Spec + 0.25 Commit Audit + 0.35 Spec Readiness",
                      copy_text["en"]["method_score"])

    def test_page_text_is_escaped_and_script_json_cannot_close_the_script(self):
        self.assertIn(">Method &amp; data</a>", self.html)
        self.assertNotIn(">Method & data</a>", self.html)
        self.assertEqual(build.script_json({"a": "</script><b>"}), '{"a": "\\u003c/script>\\u003cb>"}')

    def test_speed_note_lists_partial_cells_but_not_unknown_api_engine_input(self):
        records = build.extract(self.data, PRICING)
        for record in records:
            for cell in record["cells"].values():
                cell["speedCounts"].update(taskOutput=cell["n"], taskInput=cell["n"],
                                           engineOutput=cell["n"], engineInput=0)
        self.assertEqual(build.partial_note([r for r in records if r["vendor"] != "strata"],
                                            "speed", "en"), "")
        records = [r for r in records if r["vendor"] != "strata"]
        records[0]["cells"][REVIEWERS[0][0]]["speedCounts"]["taskOutput"] = 1
        note = build.partial_note(records, "speed", "en")
        self.assertIn(f"Code Standards · {records[0]['label']} · Task output speed (1/2)", note)
        self.assertNotIn("Engine input", note)

    def test_scale_and_segment_controls_keep_their_markup(self):
        self.assertEqual(
            build.cost_scale_control("plot", "x"),
            '<div class="cost-scale-control" role="group" data-plot="plot" data-axis="x" '
            'aria-label="Cost axis scale"><span data-i18n="cost_scale">Cost scale</span>'
            '<button type="button" data-scale="linear" data-i18n="scale_linear" '
            'aria-pressed="false">Linear</button>'
            '<button type="button" data-scale="log" data-i18n="scale_log" '
            'aria-pressed="true">Log</button></div>')
        self.assertIn('aria-pressed="true">A</button><button type="button" data-speed="1"',
                      build.segment_control("c", [(0, "a", "A"), (1, "b", "B")], "speed", "l", "L"))


if __name__ == "__main__":
    unittest.main()
