"""Checks for the benchmark page's statistics, cost rules and page assembly."""

import copy
import hashlib
import json
import math
import re
import statistics
import unittest
from pathlib import Path

from stats import (REVIEWERS, TOKEN_KEYS, composite, extract, instance_api_cost, instance_cost,
                   instance_task_points, load_pricing, plan_weekly_cost, summarize_cell, t_quantile)

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
# Plan runs: cost = equivalent task points x (weekly fee / points in a plan week).
FEE_PER_POINT = plan_weekly_cost(PRICING) / PRICING["taskPoints"]["plan"]["weeklyPoints"]

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
    return {"meta": {"schemaVersion": 1, "scoring": {"version": "r8.4"}}, "scenarios": SCENARIOS, "configs": list(configs),
            "instances": instances}


def full_config(config, scores=(0.6, 0.8), **fields):
    return [instance(score, config=config, scenario=scenario["id"], **fields)
            for scenario in SCENARIOS for score in scores]


class SourcesTests(unittest.TestCase):
    def test_snapshots_match_sources_json(self):
        root = Path(__file__).parent
        sources = json.loads((root / "sources.json").read_text(encoding="utf-8"))
        self.assertEqual({item["file"] for item in sources["snapshots"]},
                         {"benchmark-results.json", "benchmark-results-phase4.json"})
        for item in sources["snapshots"]:
            digest = hashlib.sha256((root / item["file"]).read_bytes()).hexdigest()
            self.assertEqual(digest, item["sha256"], item["file"])


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
                       "costLowerBound": False, "tokens": None,
                       "taskPoints": points, "planShare": None if points is None else points / 5, "efficiency": 1.88,
                       "efficiencyEstimate": False, "apiCost": None}
                 for (key, _, _), minutes, points in zip(REVIEWERS, (1.0, None, 3.0, 5.0), (0.2, 0.4, None, 0.9))}
        result = composite(cells)
        self.assertIsNone(result["half"])
        self.assertAlmostEqual(result["minutes"], 3.0)
        self.assertEqual(result["timeCount"], 3)
        self.assertAlmostEqual(result["taskPoints"], 0.5)
        self.assertAlmostEqual(result["planShare"], 0.1)
        self.assertEqual(result["efficiency"], 1.88)
        self.assertIsNone(result["apiCost"])


class CostTests(unittest.TestCase):
    def test_openai_prices_tokens_at_api_rates(self):
        usd, lower = instance_api_cost(instance(0.5, tokens=(1_000_000, 2_000_000, 100_000)),
                                       CONFIGS["openai"], PRICING)
        uncached, cached, output = OPENAI_RATES["gpt-6.1-sol"]
        self.assertAlmostEqual(usd, uncached + 2 * cached + 0.1 * output)
        self.assertFalse(lower)

    def test_anthropic_and_deepseek_use_instance_cost(self):
        item = instance(0.5, cost={"usd": 0.42, "lowerBound": True})
        self.assertEqual(instance_api_cost(item, CONFIGS["anthropic"], PRICING), (0.42, True))
        deepseek = {**CONFIGS["anthropic"], "vendor": "deepseek"}
        self.assertEqual(instance_cost(item, deepseek, PRICING), (0.42, True))
        self.assertEqual(instance_cost(instance(0.5), CONFIGS["anthropic"], PRICING), (None, False))

    def test_plan_vendors_cost_is_the_plan_week_share_of_the_weekly_fee(self):
        eff = PRICING["taskPoints"]["efficiency"]
        week_points = PRICING["taskPoints"]["plan"]["weeklyPoints"]
        weekly_fee = PRICING["taskPoints"]["plan"]["monthlyUsd"] / PRICING["taskPoints"]["plan"]["daysPerMonth"] * 7
        item = instance(0.5, cost={"usd": 0.42, "lowerBound": True})
        usd, lower = instance_cost(item, CONFIGS["anthropic"], PRICING)
        points = 0.42 * eff["anthropic"]["e"] / PRICING["taskPoints"]["pointUsd"]
        self.assertAlmostEqual(usd, points / week_points * weekly_fee)
        self.assertTrue(lower)
        self.assertAlmostEqual(instance_task_points(item, CONFIGS["anthropic"], PRICING), points)
        tokens = instance(0.5, tokens=(1_000_000, 2_000_000, 100_000))
        api_usd = instance_api_cost(tokens, CONFIGS["openai"], PRICING)[0]
        points = api_usd * eff["openai"]["e"] / 100
        self.assertAlmostEqual(instance_task_points(tokens, CONFIGS["openai"], PRICING), points)
        self.assertAlmostEqual(instance_cost(tokens, CONFIGS["openai"], PRICING)[0], points / week_points * weekly_fee)

    def test_plan_week_values_are_recorded_with_source_and_date(self):
        plan = PRICING["taskPoints"]["plan"]
        self.assertEqual(plan["weeklyPoints"], 5.36)
        self.assertEqual(plan["weeklyPoints"] * PRICING["taskPoints"]["pointUsd"], 536)
        self.assertAlmostEqual(plan_weekly_cost(PRICING), 23.3333, places=3)
        self.assertIn("2026-11-18", plan["weeklyPointsCheckedAt"])
        self.assertTrue(plan["weeklyPointsBasis"])

    def test_cost_ratios_between_plan_runs_equal_the_v25_ratios(self):
        # v2.5 cost was API-equivalent USD x E; v2.6 multiplies every plan run by the same constant.
        eff = PRICING["taskPoints"]["efficiency"]
        google = {**CONFIGS["openai"], "vendor": "google", "model": "gemini-4-hydrogen"}
        runs = [(instance(0.5, cost={"usd": 1.7055}), CONFIGS["anthropic"], "anthropic"),
                (instance(0.5, cost={"usd": 0.0831}), CONFIGS["anthropic"], "anthropic"),
                (instance(0.5, tokens=(3_000_000, 5_000_000, 400_000)), CONFIGS["openai"], "openai"),
                (instance(0.5, tokens=(1_000_000, 0, 700_000)), google, "google")]
        v25 = [instance_api_cost(item, config, PRICING)[0] * eff[vendor]["e"] for item, config, vendor in runs]
        v26 = [instance_cost(item, config, PRICING)[0] for item, config, _ in runs]
        constant = v26[0] / v25[0]
        for old, new in zip(v25, v26):
            self.assertAlmostEqual(new / old, constant)
        self.assertAlmostEqual(constant, plan_weekly_cost(PRICING) / 536)

    def test_claude_cost_matches_the_v24_share_of_the_100_dollar_plan_week(self):
        # v2.4 Claude cost: API-equivalent USD / $536 x $23.33 (feb1995); E = 1 so v2.6 must agree.
        for api in (1.7055, 1.3089, 0.274, 0.138):
            usd = instance_cost(instance(0.5, cost={"usd": api}), CONFIGS["anthropic"], PRICING)[0]
            self.assertAlmostEqual(usd, api / 536 * 100 / 30 * 7, places=9)

    def test_deepseek_and_strata_stay_in_actual_dollars(self):
        deepseek = {**CONFIGS["anthropic"], "vendor": "deepseek"}
        self.assertEqual(instance_cost(instance(0.5, cost={"usd": 0.42}), deepseek, PRICING), (0.42, False))
        self.assertEqual(instance_cost(instance(0.5, seconds=3600), CONFIGS["strata"], PRICING)[0],
                         instance_api_cost(instance(0.5, seconds=3600), CONFIGS["strata"], PRICING)[0])

    def test_claude_plan_efficiency_is_one_by_definition(self):
        self.assertEqual(PRICING["taskPoints"]["efficiency"]["anthropic"]["e"], 1.0)
        self.assertEqual(PRICING["taskPoints"]["pointUsd"], 100)

    def test_efficiency_is_the_injected_value_and_gemini_is_a_plan_vendor(self):
        other = copy.deepcopy(PRICING)
        other["taskPoints"]["efficiency"]["openai"]["e"] = 2.0
        other["taskPoints"]["efficiency"]["google"]["e"] = 1.5
        tokens = instance(0.5, tokens=(1_000_000, 0, 0))
        self.assertAlmostEqual(instance_cost(tokens, CONFIGS["openai"], other)[0], 2.0 * 2.0 / 100 * FEE_PER_POINT)
        google = {**CONFIGS["openai"], "vendor": "google", "model": "gemini-4-hydrogen"}
        self.assertAlmostEqual(instance_cost(tokens, google, other)[0], 1.5 * 1.5 / 100 * FEE_PER_POINT)
        self.assertAlmostEqual(instance_task_points(tokens, google, other), 1.5 * 1.5 / 100)

    def test_gemini_cost_is_estimated_efficiency_times_api_price(self):
        google = {**CONFIGS["openai"], "vendor": "google", "model": "gemini-4-hydrogen"}
        tokens = instance(0.5, tokens=(1_000_000, 0, 0))
        self.assertAlmostEqual(instance_api_cost(tokens, google, PRICING)[0], 1.5)
        self.assertAlmostEqual(instance_cost(tokens, google, PRICING)[0],
                               1.5 * PRICING["taskPoints"]["efficiency"]["google"]["e"] / 100 * FEE_PER_POINT)
        self.assertTrue(PRICING["taskPoints"]["efficiency"]["google"]["estimate"])

    def test_non_plan_vendors_keep_their_dollar_cost_and_have_no_points(self):
        deepseek = {**CONFIGS["anthropic"], "vendor": "deepseek"}
        item = instance(0.5, cost={"usd": 0.42})
        self.assertEqual(instance_cost(item, deepseek, PRICING), (0.42, False))
        self.assertIsNone(instance_task_points(item, deepseek, PRICING))
        self.assertIsNone(instance_task_points(instance(0.5, seconds=3600), CONFIGS["strata"], PRICING))
        self.assertIsNone(instance_task_points(instance(0.5), CONFIGS["anthropic"], PRICING))

    def test_cell_and_composite_carry_task_points_and_api_equivalent(self):
        items = full_config(CONFIGS["openai"]["key"], tokens=(1_000_000, 0, 0))
        cell = summarize_cell(items[:2], CONFIGS["openai"], PRICING)
        e = PRICING["taskPoints"]["efficiency"]["openai"]["e"]
        self.assertAlmostEqual(cell["apiCost"], 2.0)
        self.assertAlmostEqual(cell["cost"], 2.0 * e / 100 * FEE_PER_POINT)
        self.assertAlmostEqual(cell["planShare"], 2.0 * e / 100 / PRICING["taskPoints"]["plan"]["weeklyPoints"])
        self.assertAlmostEqual(cell["taskPoints"], 2.0 * e / 100)
        self.assertEqual(cell["efficiency"], e)
        record = extract(results(items), PRICING)[0]
        self.assertAlmostEqual(record["taskPoints"], 2.0 * e / 100)
        self.assertAlmostEqual(record["apiCost"], 2.0)
        self.assertEqual(record["efficiency"], e)
        local = extract(results(full_config(CONFIGS["strata"]["key"]),
                                configs=(CONFIGS["strata"],)), PRICING)[0]
        self.assertIsNone(local["taskPoints"])
        self.assertIsNone(local["apiCost"])
        self.assertIsNone(local["efficiency"])

    def test_local_cost_is_running_cost_and_positive(self):
        rule = LOCAL_COST["strata-iq3_xxs"]
        usd, _ = instance_cost(instance(0.5, seconds=3600), CONFIGS["strata"], PRICING)
        self.assertAlmostEqual(usd, rule["wallPowerWatts"] / 1000 * rule["electricityUsdPerKwh"]
                               + rule["maintenanceUsdPerHour"])
        self.assertGreater(usd, 0)
        self.assertEqual(PRICING["schemaVersion"], 5)

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

    def test_phase4_supplement_file_is_merged_and_priced_at_google_rates(self):
        google = {"key": "antigravity/gemini-4-hydrogen/high", "harness": "antigravity",
                  "model": "gemini-4-hydrogen", "effort": "high", "vendor": "google", "kind": "phase4"}
        extra = results(full_config(google["key"], tokens=(1_000_000, 2_000_000, 100_000)), configs=(google,))
        main = results(full_config(CONFIGS["openai"]["key"]))
        records = extract(main, PRICING, [extra])
        hydrogen = next(record for record in records if record["vendor"] == "google")
        self.assertEqual((hydrogen["label"], hydrogen["harness"]), ("Gemini 4 Hydrogen · high · Antigravity", "antigravity"))
        self.assertAlmostEqual(hydrogen["cost"], (1.5 + 2 * 0.075 + 0.1 * 7.5) * PRICING["taskPoints"]["efficiency"]["google"]["e"] / 100 * FEE_PER_POINT)
        with self.assertRaisesRegex(ValueError, "repeats"):
            extract(main, PRICING, [extra, extra])
        with self.assertRaisesRegex(ValueError, "same scenarios"):
            extract(main, PRICING, [{**extra, "scenarios": extra["scenarios"][:2]}])

    def test_main_instance_without_valid_score_is_rejected(self):
        bad = full_config(CONFIGS["openai"]["key"])
        bad[0]["validity"]["valid"] = False
        with self.assertRaises(ValueError):
            extract(results(bad), PRICING)

    def test_scoring_and_pricing_versions_are_checked(self):
        data = results(full_config(CONFIGS["openai"]["key"]))
        data["meta"]["scoring"] = {"version": "r9.0"}
        with self.assertRaisesRegex(ValueError, "scoring version"):
            extract(data, PRICING)
        data["meta"]["scoring"] = {"version": "r8.4"}
        with self.assertRaisesRegex(ValueError, "pricing file"):
            extract(data, {**PRICING, "schemaVersion": 99})

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
        self.assertIn("等效任务点", self.html)

    def test_method_text_follows_pricing_and_weights(self):
        pricing = copy.deepcopy(PRICING)
        pricing["openai"]["gpt-6-luna"]["rates"]["output"] = 0.75
        pricing["localRunningCost"]["strata-iq3_xxs"]["wallPowerWatts"] = 450
        pricing["checkedAt"] = "2030-01-02"
        copy_text = build.page_copy(pricing, extract(self.data, pricing))
        self.assertIn("$0.10 / $0.01 / $0.75", copy_text["en"]["method_cost"])
        self.assertIn("450 W × $0.174 per kWh", copy_text["en"]["method_cost"])
        self.assertIn("450 W × 全球家庭平均电价 $0.174/kWh", copy_text["zh"]["method_cost"])
        self.assertIn("2030-01-02", copy_text["zh"]["method_cost"])
        self.assertIn("0.20 Code Standards + 0.20 Code Spec + 0.25 Commit Audit + 0.35 Spec Readiness",
                      copy_text["en"]["method_score"])

    def test_cost_tooltips_keep_the_original_items_with_one_comparable_cost(self):
        records = {record["vendor"]: record for record in extract(self.data, PRICING)}
        hover = build.hover_summary(records["anthropic"], "cost", "score").split("\n")
        self.assertEqual(hover[:3], [records["anthropic"]["label"], build.short_value(records["anthropic"], "cost"),
                                     build.short_value(records["anthropic"], "score")])
        self.assertEqual(hover[3], "Cost\tPrice converted to plan subscription fee\t费用\t换算成套餐订阅费的价格")
        self.assertEqual(len(hover), 4)
        self.assertEqual(build.hover_summary(records["strata"], "cost", "score").count("\n"), 3)
        self.assertEqual(build.hover_summary(records["anthropic"], "minutes", "score").count("\n"), 2)
        names = "".join(re.findall(r'"name": "[^"]*"', self.html))
        for text in ("Equivalent task points", "API-equivalent cost", "Plan week share", "等效任务点", "套餐周份额"):
            self.assertNotIn(text, names)
        self.assertIn('"name": "Price converted to plan subscription fee", "color"', self.html)
        self.assertNotIn("(estimated)", self.html)

    def test_every_tooltip_label_is_short(self):
        # Tooltips list data; any explanation belongs to the reading notes and data notes.
        names = set(re.findall(r'"(?:name|meta|label)": "([^"]*)"', self.html))
        names |= set(re.findall(r'"meta": "([^"]*)', self.html))
        for name in names:
            self.assertLess(len(name), 60, name)
        for text in (" · 3 effort levels", " · 档推理强度", "Includes lower bounds", "basis named in the tooltip", "计费依据见悬停提示"):
            self.assertNotIn(text, self.html)

    def test_method_text_states_the_plan_fee_conversion(self):
        copy_text = build.page_copy(PRICING, extract(self.data, PRICING))
        for language, task_points, week in (("en", "task points", "weekly fee"), ("zh", "等效任务点", "周费用")):
            text = copy_text[language]["method_cost"]
            for needle in (task_points, week, "$23.33", "$100", "5.36", "$536", "1.88", "1.19", "1/100", "1/10", "DeepSeek", "Strata"):
                self.assertIn(needle, text)
            self.assertNotIn("$470", text)
        for key in ("cost_score_desc", "detail_cost_read", "version_summary"):
            for language in ("en", "zh"):
                self.assertIn("$100", copy_text[language][key])
        for language in ("en", "zh"):
            self.assertIn("$23.33", copy_text[language]["cost_score_desc"])
            self.assertIn("1/100", copy_text[language]["cost_score_read"])

    def test_page_version_is_2_6_3(self):
        self.assertEqual(build.PAGE_VERSION, "2.6.3")

    def test_page_text_is_escaped_and_script_json_cannot_close_the_script(self):
        self.assertIn(">Method &amp; data</a>", self.html)
        self.assertNotIn(">Method & data</a>", self.html)
        self.assertEqual(build.script_json({"a": "</script><b>"}), '{"a": "\\u003c/script>\\u003cb>"}')

    def test_run_count_text_follows_cells_in_both_languages(self):
        records = extract(self.data, PRICING)
        cells = [cell for record in records for cell in record["cells"].values()]
        for cell, n in zip(cells, (4, 8, 10)):
            cell["n"] = n
        text = build.page_copy(PRICING, records)
        self.assertIn("Each task cell counts 2 to 10 scored runs.", text["en"]["version_summary"])
        self.assertIn("每个任务格计入 2 至 10 次计分运行.", text["zh"]["version_summary"])
        for key in ("method_selection", "detail_score_read"):
            self.assertIn("9 cells with 2 runs; 1 cell with 4 runs; 1 cell with 8 runs; "
                          "1 cell with 10 runs", text["en"][key])
            self.assertIn("9 格各 2 次; 1 格各 4 次; 1 格各 8 次; 1 格各 10 次", text["zh"][key])
        for cell in cells:
            cell["n"] = 7
        text = build.page_copy(PRICING, records)
        self.assertIn("Each task cell counts 7 scored runs.", text["en"]["version_summary"])
        self.assertIn("每个任务格计入 7 次计分运行.", text["zh"]["version_summary"])
        self.assertIn("12 cells with 7 runs", text["en"]["method_selection"])

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
