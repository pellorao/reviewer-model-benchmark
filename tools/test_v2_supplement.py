"""Checks for the v2 supplement tool: per-request prices, peak hours, and a tiny saved-run directory."""

import datetime
import json
import tempfile
import unittest
from pathlib import Path

if __package__:
    from . import v2_supplement as tool
else:
    import v2_supplement as tool

RATES = {"cacheRead": 0.5, "cacheWrite1h": 10.0, "output": 25.0,
         "longPromptThreshold": 100000, "long": {"cacheRead": 1.0, "cacheWrite1h": 20.0, "output": 50.0}}
PEAK = {"weekdays": [0, 1, 2, 3, 4], "hours": [[1, 4], [6, 10]]}


def epoch(year, month, day, hour):
    return int(datetime.datetime(year, month, day, hour, tzinfo=datetime.timezone.utc).timestamp() * 1000)


class PriceTests(unittest.TestCase):
    def test_claude_request_prices_cache_writes_at_the_one_hour_rate(self):
        response = {"inputTokens": 1000, "cachedInputTokens": 400, "outputTokens": 100}
        self.assertAlmostEqual(tool.claude_request_usd(response, RATES),
                               (400 * 0.5 + 600 * 10.0 + 100 * 25.0) / 1e6)

    def test_long_prompt_tier_applies_above_the_threshold_only(self):
        small = {"inputTokens": 100000, "cachedInputTokens": 0, "outputTokens": 0}
        large = {"inputTokens": 100001, "cachedInputTokens": 0, "outputTokens": 0}
        self.assertAlmostEqual(tool.claude_request_usd(small, RATES), 100000 * 10.0 / 1e6)
        self.assertAlmostEqual(tool.claude_request_usd(large, RATES), 100001 * 20.0 / 1e6)

    def test_deepseek_peak_hours_are_weekday_utc_windows(self):
        self.assertTrue(tool.deepseek_is_peak(epoch(2026, 11, 23, 2), PEAK))    # Monday 02:00
        self.assertFalse(tool.deepseek_is_peak(epoch(2026, 11, 23, 4), PEAK))   # window end is exclusive
        self.assertTrue(tool.deepseek_is_peak(epoch(2026, 11, 23, 9), PEAK))
        self.assertFalse(tool.deepseek_is_peak(epoch(2026, 11, 22, 2), PEAK))   # Sunday

    def test_deepseek_request_uses_the_window_rates(self):
        rule = {"peakUtc": PEAK, "peak": {"input": 2.0, "cacheRead": 0.2, "output": 4.0},
                "offPeak": {"input": 1.0, "cacheRead": 0.1, "output": 2.0}}
        response = {"inputTokens": 1000, "cachedInputTokens": 500, "outputTokens": 100, "completedAt": epoch(2026, 11, 23, 2)}
        self.assertAlmostEqual(tool.deepseek_request_usd(response, rule), (500 * 0.2 + 500 * 2.0 + 100 * 4.0) / 1e6)
        response["completedAt"] = epoch(2026, 11, 23, 12)
        self.assertAlmostEqual(tool.deepseek_request_usd(response, rule), (500 * 0.1 + 500 * 1.0 + 100 * 2.0) / 1e6)

    def test_requests_that_do_not_add_up_are_refused(self):
        agent = {"result": {"snapshot": {"measurementFacts": {"responses": [
            {"inputTokens": 10, "cachedInputTokens": 0, "outputTokens": 1}]},
            "members": [{"usage": {"inputTokens": 11, "outputTokens": 1}}]}}}
        with self.assertRaises(ValueError):
            tool.api_usd(agent, "anthropic", "opus", {"anthropic": {"opus": RATES}})

    def test_plan_vendors_are_priced_from_the_export_not_here(self):
        self.assertEqual(tool.api_usd({}, "openai", "gpt-6.2-sol", {}), (None, None))


class BuildTests(unittest.TestCase):
    def write(self, directory, name, value):
        (directory / name).write_text(json.dumps(value), encoding="utf-8")

    def test_build_joins_saved_runs_to_the_export_and_counts_retries(self):
        usd = {"inputTokens": 100, "cachedInputTokens": 0, "outputTokens": 10}
        agent = {"result": {"snapshot": {"measurementFacts": {"responses": [usd]},
                                         "members": [{"usage": {"inputTokens": 100, "outputTokens": 10}}]}}}
        export = {"instances": [{"id": "run-1", "scenario": "x/code-spec",
                                 "settings": {"modelProvider": "anthropic", "model": "opus"}}]}
        pricing = {"anthropic": {"opus": RATES}}
        with tempfile.TemporaryDirectory() as root:
            directory = Path(root) / "opus-high-code-spec-r1"
            directory.mkdir()
            self.write(directory, "run.json", {"id": "run-1"})
            self.write(directory, "driver.json", {"attempt": 3, "harnessCli": "claude", "harnessVersion": "2.1"})
            self.write(directory, "score.json", {"scores": {"scenarioSha256": "abc",
                                                            "severityUnits": {"high": {"weight": 4}}}})
            self.write(directory, "agent.json", agent)
            result = tool.build(root, export, pricing, restored_voids=[{"note": "kept"}])
        entry = result["instances"]["run-1"]
        self.assertEqual((entry["lane"], entry["attempt"], entry["costBasis"]), ("opus", 3, "claude-per-request"))
        self.assertAlmostEqual(entry["apiUsd"], (100 * 10.0 + 10 * 25.0) / 1e6)
        self.assertEqual(result["arms"]["opus"]["retries"], 2)
        self.assertEqual(result["scenarios"]["x/code-spec"]["severityWeights"], {"high": 4})
        self.assertEqual(result["restoredVoids"], [{"note": "kept"}])

    def test_an_export_instance_without_a_saved_directory_fails(self):
        with tempfile.TemporaryDirectory() as root, self.assertRaises(ValueError):
            tool.build(root, {"instances": [{"id": "lost"}]}, {})


if __name__ == "__main__":
    unittest.main()
