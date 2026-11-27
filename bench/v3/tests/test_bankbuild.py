import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import bankbuild as bb


class FakeGit:
    """Canned git: maps the first argument (or two) to an output; records calls."""

    def __init__(self, outputs):
        self.outputs, self.calls = outputs, []

    def __call__(self, *args, ok=False, cwd=None):
        self.calls.append(args)
        out = self.outputs.get(args[0], "")
        return out(args) if callable(out) else out


def patched(outputs):
    fake = FakeGit(outputs)
    return fake, mock.patch.object(bb, "git", fake)


class IdTest(unittest.TestCase):
    def test_item_id_stable_and_kind_sensitive(self):
        self.assertEqual(bb.item_id("a", "k"), bb.item_id("a", "k"))
        self.assertNotEqual(bb.item_id("a", "k"), bb.item_id("b", "k"))
        self.assertRegex(bb.item_id("a", "k"), r"^w3-[0-9a-f]{12}$")

    def test_stable_is_deterministic_int(self):
        self.assertEqual(bb.stable("x"), bb.stable("x"))
        self.assertIsInstance(bb.stable("x"), int)


class BranchesTest(unittest.TestCase):
    def outputs(self, rows="c1 B\nc2 c1"):
        return {"log": "M P1 P2 1000\nbadline\nN P1 P3 5 extra",
                "merge-base": "B\n",
                "rev-list": rows,
                "diff": "20\t15\tx.py\n3\t0\ttests/test_x.py\n-\t-\timg.png\n1\t1\tnotes.md"}

    def test_linear_branch_collected(self):
        _, ctx = patched(self.outputs())
        with ctx:
            found = bb.branches()
        self.assertEqual(list(found), ["M"])
        info = found["M"]
        self.assertEqual((info["base"], info["tip"], info["commits"]), ("B", "P2", ["c1", "c2"]))
        self.assertEqual(info["lines"], 20 + 15 + 3 + 1 + 1)  # binary row skipped
        self.assertEqual(info["code_files"], ["x.py"])  # test file and .md excluded
        self.assertEqual(info["merged"], 1000)

    def test_rejects_empty_too_long_and_nonlinear(self):
        for rows in ("", "\n".join(f"c{i} p" for i in range(bb.MAX_COMMITS + 1)), "c1 a b"):
            _, ctx = patched(self.outputs(rows))
            with ctx:
                self.assertEqual(bb.branches(), {})


class UsableTest(unittest.TestCase):
    def test_bounds(self):
        ok = {"lines": bb.MIN_LINES, "code_files": ["a.py"]}
        self.assertTrue(bb.usable(ok))
        self.assertFalse(bb.usable({**ok, "lines": bb.MIN_LINES - 1}))
        self.assertFalse(bb.usable({**ok, "lines": bb.MAX_LINES + 1}))
        self.assertFalse(bb.usable({**ok, "code_files": []}))


class FixPairsTest(unittest.TestCase):
    def run_pairs(self, diff, by_commit, blame="abc (x)\n"):
        outputs = {"log": "FIX\n", "rev-parse": "PARENT\n", "diff": diff, "blame": blame}
        fake, ctx = patched(outputs)
        with ctx:
            return bb.fix_pairs(by_commit), fake

    def test_blamed_branch_paired_with_fix(self):
        diff = "--- a/x.py\n+++ b/x.py\n@@ -3,2 +3,2 @@\n--- a/tests/t.py\n@@ -1 +1 @@\n--- /dev/null\n@@ -1 +1 @@"
        pairs, fake = self.run_pairs(diff, {"abc": "M"}, blame="^abc (x)\n")
        self.assertEqual(pairs, {("M", "FIX"): ["x.py"]})
        blames = [c for c in fake.calls if c[0] == "blame"]
        self.assertEqual(len(blames), 1)  # test file and /dev/null skipped
        self.assertIn("3,4", blames[0])

    def test_pure_insertion_blames_surrounding_lines(self):
        _, fake = self.run_pairs("--- a/x.py\n@@ -5,0 +6,3 @@", {})
        self.assertIn("5,6", [c for c in fake.calls if c[0] == "blame"][0])

    def test_fix_that_is_itself_a_branch_commit_ignored(self):
        pairs, _ = self.run_pairs("--- a/x.py\n@@ -3 +3 @@", {"abc": "M", "FIX": "N"})
        self.assertEqual(pairs, {})

    def test_unknown_blamed_commit_ignored(self):
        pairs, _ = self.run_pairs("--- a/x.py\n@@ -3 +3 @@", {"other": "M"})
        self.assertEqual(pairs, {})


class JsonFromTest(unittest.TestCase):
    def test_extracts_first_object_with_nesting(self):
        self.assertEqual(bb.json_from('text {"a": {"b": 1}} tail {"c": 2}'), {"a": {"b": 1}})

    def test_no_object_raises(self):
        with self.assertRaises(ValueError):
            bb.json_from("nothing here")

    def test_unbalanced_raises(self):
        with self.assertRaises(ValueError):
            bb.json_from('{"a": 1')


class SplitPoolTest(unittest.TestCase):
    pool = {f"m{i}": {"stratum": "s1" if i < 10 else "s2"} for i in range(15)}

    def test_stratified_share(self):
        side = bb.split_pool(self.pool)
        self.assertEqual(set(side), set(self.pool))
        self.assertEqual(sum(v == "reserve" for k, v in side.items() if self.pool[k]["stratum"] == "s1"), 4)
        self.assertEqual(sum(v == "reserve" for k, v in side.items() if self.pool[k]["stratum"] == "s2"), 2)

    def test_deterministic_and_order_independent(self):
        reordered = dict(reversed(list(self.pool.items())))
        self.assertEqual(bb.split_pool(self.pool), bb.split_pool(reordered))

    def test_empty(self):
        self.assertEqual(bb.split_pool({}), {})


class LlmTest(unittest.TestCase):
    def call(self, stdout, rc=0):
        done = subprocess.CompletedProcess([], rc, stdout=stdout, stderr="")
        with mock.patch.object(bb.subprocess, "run", return_value=done) as run:
            try:
                return bb.llm("prompt"), run
            except RuntimeError as err:
                return err, run

    def test_returns_result_row(self):
        rows = "\n".join(["not json", json.dumps({"type": "system"}),
                          json.dumps({"type": "result", "is_error": False, "result": "ok"})])
        text, run = self.call(rows)
        self.assertEqual(text, "ok")
        self.assertEqual(run.call_args.kwargs["input"], "prompt")
        self.assertEqual(run.call_args.args[0][0], str(bb.GUARD))

    def test_failures_raise(self):
        err, _ = self.call("", rc=3)
        self.assertIn("rc=3", str(err))
        err, _ = self.call(json.dumps({"type": "result", "is_error": True, "result": "x"}))
        self.assertIn("failed", str(err))
        err, _ = self.call(json.dumps({"type": "system"}))
        self.assertIn("failed", str(err))


class LlmGuardTest(unittest.TestCase):
    def test_start_cap_bounds_window_spend_and_dirs_are_made(self):
        ok = json.dumps({"type": "result", "is_error": False, "result": "ok"})
        done = subprocess.CompletedProcess([], 0, stdout=ok, stderr="")
        with mock.patch.object(bb.subprocess, "run", return_value=done) as run, \
                mock.patch.object(bb.os, "makedirs") as mk:
            bb.llm("p")
        cmd = run.call_args.args[0]
        starts = int(cmd[cmd.index("--max-starts") + 1])
        self.assertLessEqual(starts * float(cmd[cmd.index("--max-usd") + 1]), 360)
        self.assertEqual(run.call_args.kwargs["cwd"], bb.LLM_DIR)
        self.assertIn(mock.call(bb.LLM_DIR, exist_ok=True), mk.call_args_list)


class JsonFromStringTest(unittest.TestCase):
    def test_braces_inside_strings(self):
        self.assertEqual(bb.json_from('x {"a": "}y", "b": 1} t'), {"a": "}y", "b": 1})
        self.assertEqual(bb.json_from('{"a": "\\"}", "b": 2}'), {"a": '"}', "b": 2})

    def test_skips_broken_prefix(self):
        self.assertEqual(bb.json_from('{oops {"a": 1}'), {"a": 1})


class GitWrapperTest(unittest.TestCase):
    def test_failure_raises_unless_ok(self):
        bad = subprocess.CompletedProcess([], 1, stdout="partial", stderr="")
        with mock.patch.object(bb.subprocess, "run", return_value=bad):
            with self.assertRaises(RuntimeError):
                bb.git("log")
            self.assertEqual(bb.git("log", ok=True), "partial")

    def test_read_at_and_diff_text_args(self):
        fake, ctx = patched({"show": "body", "diff": "d"})
        with ctx:
            self.assertEqual(bb.read_at("rev", "p.py"), "body")
            self.assertEqual(bb.diff_text("a", "b"), "d")
        self.assertEqual(fake.calls[0], ("show", "rev:p.py"))
        self.assertEqual(fake.calls[1], ("diff", "--no-color", "-U6", "a", "b"))


if __name__ == "__main__":
    unittest.main()
