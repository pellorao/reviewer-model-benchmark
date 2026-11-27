import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import triage_derive as td

KEY = {"defects": [{"severity": "high", "locations": [{"file": "a.py", "start": 10, "end": 12}]},
                   {"severity": "medium", "locations": [{"file": "b.py", "start": 40, "end": 40}]}],
       "known_false": [{"locations": [{"file": "c.py", "start": 5, "end": 6}]}]}


def finding(file, start, end=None, fp="f", severity="high"):
    return {"fingerprint": fp, "severity": severity, "file": file, "start": start, "end": end or start}


class GoldTest(unittest.TestCase):
    def test_matches_by_severity(self):
        self.assertEqual(td.gold(finding("a.py", 16), KEY), "fix-now")
        self.assertEqual(td.gold(finding("b.py", 35), KEY), "follow-up")

    def test_window_and_file(self):
        self.assertEqual(td.gold(finding("a.py", 18), KEY), "ignore")
        self.assertEqual(td.gold(finding("z.py", 11), KEY), "ignore")

    def test_known_false_and_ruling(self):
        self.assertEqual(td.gold(finding("c.py", 5), KEY), "ignore")
        self.assertEqual(td.gold(finding("d.py", 1), KEY, {"valid": True, "severity": "high"}), "fix-now")
        self.assertEqual(td.gold(finding("d.py", 1), KEY, {"valid": True, "severity": "medium"}), "follow-up")
        self.assertEqual(td.gold(finding("d.py", 1), KEY, {"valid": False}), "ignore")


class DeriveTest(unittest.TestCase):
    def test_only_high_once_per_fingerprint(self):
        runs = [{"question": "q", "findings": [finding("a.py", 10, fp="x"), finding("a.py", 10, fp="y", severity="medium")]},
                {"question": "q", "findings": [finding("a.py", 11, fp="x")]},
                {"question": "other", "findings": [finding("a.py", 10, fp="x")]}]
        got = td.derive(runs, {"q": KEY})
        self.assertEqual([(g["question"], g["fingerprint"], g["gold"]) for g in got], [("q", "x", "fix-now")])


if __name__ == "__main__":
    unittest.main()
