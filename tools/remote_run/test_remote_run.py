"""Offline tests of remote_run: ARW and the model command are fakes, except the two real-process cases and the gated end-to-end one."""
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import time
import unittest
from unittest.mock import patch

from tools.remote_run import remote_run as rr

PIN = {"arw_commit": "a" * 40, "fixture_tree": "b" * 40}
PROVENANCE = {"commit": PIN["arw_commit"], "treeDirty": False, "fixtureTree": PIN["fixture_tree"], "arwVersion": "9.9"}


class Args:
    def __init__(self, **kw):
        self.arw, self.model, self.model_id, self.efforts = "/arw", "hyd", None, ["high"]
        self.scenarios, self.n, self.limit_seconds = ["code-spec"], 1, 5
        self.__dict__.update(kw)


class FakeArw:
    """setup builds a bare instance directory; repair and score answer from `self.score`."""

    def __init__(self):
        self.calls = []
        self.score = {"status": "succeeded", "candidates": [{"candidateId": "c1"}], "scores": {"final": 0.5}}
        self.repair = {"status": "succeeded", "changes": {}}

    def __call__(self, args):
        self.calls.append(args[0])
        if args[0] == "setup":
            inst = Path(args[2])
            report = inst / ".tmp" / "review" / "reports" / "report.txt"
            report.parent.mkdir(parents=True)
            return {"status": "succeeded", "input": {"instructions": "I", "handoff": "H", "cwd": str(inst), "reportPath": str(report)}}
        if args[0] == "repair":
            return dict(self.repair)
        return dict(self.score)


def model_writing(text="review", out="", rc=0, leak=""):
    def call(argv, cwd, env, stdin, timeout):
        Path(env["RB_REPORT_PATH"]).write_text(text + leak, encoding="utf-8")
        return {"rc": rc, "out": out, "err": "", "seconds": 1.5, "timed_out": False}
    return call


def model_silent(timed_out=False):
    return lambda *a: {"rc": 0 if not timed_out else -15, "out": "", "err": "", "seconds": 1.0, "timed_out": timed_out}


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.out, self.work = self.root / "out", self.root / "work"
        self.out.mkdir()
        self.work.mkdir()
        self.config = {"command": ["cmd", "{prompt_file}", "{model}-{effort}"], "files": {}, "provider": "agy", "env": {}}

    def runner(self, arw, model, **kw):
        args = Args(**kw)
        return rr.Runner(args, self.config, PROVENANCE, self.out, self.work, arw=arw, model=model)

    def task(self):
        return rr.task_list("hyd", ["high"], ["code-spec"], 1)[0]


class SmallPieces(unittest.TestCase):
    def test_task_list_alternates_rounds(self):
        cells = [t["cell"] for t in rr.task_list("m", ["low", "high"], ["code-spec", "commit-audit"], 2)]
        self.assertEqual(cells, ["m-low-code-spec-r1", "m-low-commit-audit-r1", "m-high-code-spec-r1", "m-high-commit-audit-r1",
                                 "m-high-commit-audit-r2", "m-high-code-spec-r2", "m-low-commit-audit-r2", "m-low-code-spec-r2"])

    def test_config_validation(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "c.json"
            path.write_text(json.dumps({"command": ["x", "{nope}"]}))
            with self.assertRaisesRegex(SystemExit, "Unknown placeholder"):
                rr.load_config(path)
            path.write_text(json.dumps({"command": ["x", "{file.s.json}"], "files": {"s.json": {"a": "{cwd}"}}}))
            self.assertEqual(rr.load_config(path)["provider"], "agy")
            path.write_text(json.dumps({"command": "x"}))
            with self.assertRaisesRegex(SystemExit, "non-empty list"):
                rr.load_config(path)

    def test_render_nested_values(self):
        self.assertEqual(rr.render({"a": ["{x}/y", 3]}, {"x": "p"}), {"a": ["p/y", 3]})

    def test_parse_usage(self):
        usage = rr.parse_usage('{"usage": {"input_tokens": 100, "cache_read_tokens": 30, "output_tokens": 7}}')
        self.assertEqual(usage, {"uncachedInput": 70, "cachedInput": 30, "output": 7})
        self.assertEqual(rr.parse_usage("plain text"), {"uncachedInput": None, "cachedInput": None, "output": None})

    def test_scan_leaks_finds_fixture_path_and_checkout_path(self):
        self.assertEqual(rr.scan_leaks("/x/arw", ["nothing"]), [])
        self.assertIn(rr.FIXTURES, rr.scan_leaks("/x/arw", [f"cat {rr.FIXTURES}/a/expected.json"]))

    def test_parse_usage_ignores_non_dict_and_nan(self):
        for text in ('{"usage": [1]}', '{"usage": "x"}', '[]', '{"usage": {"output_tokens": NaN}}'):
            self.assertEqual(rr.parse_usage(text)["output"], None)

    def test_scan_leaks_ignores_a_sibling_directory_with_the_same_prefix(self):
        self.assertEqual(rr.scan_leaks("/x/arw", ["/x/arw-work/i-1/prompt.md"]), [])
        self.assertTrue(rr.scan_leaks("/x/arw", ["/x/arw/fixtures"]))

    def test_cell_names_allow_underscore_from_model_and_effort(self):
        self.assertTrue(rr.CELL_RE.match("gemini_pro-extra_high-s1-r2"))

    def test_check_arw_pin_dirty_and_tree(self):
        answers = {"rev-parse HEAD": PIN["arw_commit"], f"rev-parse HEAD:{rr.FIXTURES}": PIN["fixture_tree"], "status --porcelain --untracked-files=no": ""}
        fake = lambda arw, *a: answers[" ".join(a)]
        with patch.object(rr, "git_out", fake):
            self.assertEqual(rr.check_arw("/arw", PIN)["commit"], PIN["arw_commit"])
            for key, value, message in (("rev-parse HEAD", "c" * 40, "the pin is"), ("status --porcelain --untracked-files=no", " M x", "tracked changes"),
                                        (f"rev-parse HEAD:{rr.FIXTURES}", "d" * 40, "Fixture tree")):
                with patch.dict(answers, {key: value}), self.assertRaisesRegex(SystemExit, message):
                    rr.check_arw("/arw", PIN)


class GuardAndLog(Base):
    def test_guard_stops_past_twice_expected_and_ack_clears(self):
        guard = rr.Guard(self.out, 1)
        guard.record(1, 10)
        guard.record(1, 10)
        with self.assertRaisesRegex(rr.Stop, "3 calls, expected 1"):
            guard.record(1, 10)
        again = rr.Guard(self.out, 1)
        with self.assertRaisesRegex(rr.Stop, "--ack"):
            again.refuse_if_stopped(None)
        again.refuse_if_stopped("checked the log: a void streak")
        self.assertFalse(again.marker.exists())
        self.assertIn("a void streak", (self.out / "acks.log").read_text())

    def test_guard_output_token_cap(self):
        with self.assertRaisesRegex(rr.Stop, "output tokens"):
            rr.Guard(self.out, 5).record(1, rr.MAX_OUT_TOKENS + 1)

    def test_attempt_log_counts_and_streaks(self):
        log = rr.Attempts(self.out)
        for outcome, reason in (("void", "no-completion"), ("failed", "x"), ("void", "inspect-flags"), ("void", "inspect-flags")):
            log.add({"cell": "c", "outcome": outcome, "reason": reason})
        self.assertEqual(log.counted("c"), 3)
        self.assertEqual(log.streak(("void",), "inspect-flags"), 2)
        self.assertEqual(rr.Attempts(self.out).streak(("void",), "inspect-flags"), 2)      # read back from disk


class OneInstance(Base):
    def test_valid_instance_saved_with_opaque_id(self):
        arw = FakeArw()
        runner = self.runner(arw, model_writing(out='{"usage": {"output_tokens": 9}}'))
        outcome, reason, saved = runner.attempt(self.task(), 1, rr.Guard(self.out, 1))
        self.assertEqual((outcome, reason), ("valid", ""))
        run = json.loads((saved / "run.json").read_text())
        self.assertRegex(run["id"], r"^i-[0-9a-f]{12}$")
        self.assertEqual((run["settings"]["model"], run["settings"]["reasoningEffort"], run["report"], run["tokens"]["output"]), ("hyd", "high", "report.txt", 9))
        self.assertEqual(json.loads((saved / "driver.json").read_text())["id"], "hyd-high-code-spec-r1")
        self.assertEqual(json.loads((saved / "score.json").read_text())["scores"]["final"], 0.5)
        self.assertEqual(arw.calls, ["setup", "repair", "score"])
        self.assertEqual(list(self.work.iterdir()), [])                                    # scratch removed

    def test_no_report_is_void_and_kept_for_diagnosis(self):
        outcome, reason, saved = self.runner(FakeArw(), model_silent()).attempt(self.task(), 1, rr.Guard(self.out, 1))
        self.assertEqual((outcome, reason, saved), ("void", "no-completion", None))
        self.assertTrue((self.out / "voids" / "hyd-high-code-spec-r1-a1" / "why.json").exists())
        self.assertFalse((self.out / "runs").exists())

    def test_answer_key_location_voids_the_instance(self):
        runner = self.runner(FakeArw(), model_writing(leak=f" read {rr.FIXTURES}/x"))
        self.assertEqual(runner.attempt(self.task(), 1, rr.Guard(self.out, 1))[:2], ("void", "inspect-flags"))

    def test_timeout_without_report_scores_zero_and_is_saved(self):
        outcome, _, saved = self.runner(FakeArw(), model_silent(timed_out=True)).attempt(self.task(), 1, rr.Guard(self.out, 1))
        self.assertEqual(outcome, "timeout")
        self.assertEqual(json.loads((saved / "score.json").read_text())["scores"]["final"], 0)
        driver = json.loads((saved / "driver.json").read_text())
        self.assertEqual((driver["delivered"], driver["final"]), (False, 0))
        self.assertFalse((saved / "candidates.json").exists())

    def test_repaired_report_is_scored_and_a_blocked_repaired_score_falls_back(self):
        arw = FakeArw()
        scores = [{"status": "blocked"}, {"status": "succeeded", "candidates": [], "scores": {"final": 0, "modelFailure": "x"}}]
        orig = arw.__call__

        def call(args):
            if args[0] == "repair":
                norm = Path(args[3]).with_name("norm.txt")
                norm.write_text("normalized")
                rec = Path(args[3]).with_name("rec.json")
                rec.write_text("{}")
                return {"status": "succeeded", "changes": {"a": 1}, "normalized": str(norm), "record": str(rec)}
            if args[0] == "score":
                arw.calls.append("score")
                return scores.pop(0)
            return orig(args)
        saved = self.runner(call, model_writing()).attempt(self.task(), 1, rr.Guard(self.out, 1))[2]
        self.assertEqual(scores, [])
        self.assertFalse((saved / "repair.json").exists())                                # fell back to the unrepaired report
        self.assertEqual((saved / "report.txt").read_text(), "review")

    def test_score_blocked_is_failed_not_counted(self):
        arw = FakeArw()
        arw.score = {"status": "blocked", "diagnostics": ["report is empty"]}
        outcome, reason, saved = self.runner(arw, model_writing()).attempt(self.task(), 1, rr.Guard(self.out, 1))
        self.assertEqual(outcome, "failed")
        self.assertIn("score:blocked", reason)

    def test_guard_stop_after_the_instance_is_saved(self):
        guard = rr.Guard(self.out, 1)
        guard.calls = 2
        runner = self.runner(FakeArw(), model_writing())
        self.assertEqual(runner.attempt(self.task(), 1, guard)[0], "valid")
        self.assertIsNotNone(runner.pending_stop)
        self.assertTrue(guard.marker.exists())

    def test_prompt_goes_to_stdin_without_a_prompt_placeholder(self):
        self.config["command"] = ["cmd", "{model}"]
        seen = {}

        def model(argv, cwd, env, stdin, timeout):
            seen.update(argv=argv, stdin=stdin, timeout=timeout)
            return model_writing()(argv, cwd, env, stdin, timeout)
        self.runner(FakeArw(), model).attempt(self.task(), 1, rr.Guard(self.out, 1))
        self.assertEqual((seen["argv"], seen["stdin"], seen["timeout"]), (["cmd", "hyd"], "I\n\n---\n\nH\n", 5))


class Loop(Base):
    def lane(self, model, args=None):
        args = args or Args()
        runner = self.runner(FakeArw(), model)
        attempts = rr.Attempts(self.out)
        tasks = rr.pending_tasks(args, self.out, attempts)
        guard = rr.Guard(self.out, len(tasks))
        return rr.run_lane(runner, args, self.out, guard, attempts, tasks), attempts

    def test_run_resumes_and_skips_finished_cells(self):
        with patch("builtins.print"):
            code, attempts = self.lane(model_writing(), Args(n=2))
            self.assertEqual((code, attempts.counted("hyd-high-code-spec-r2")), (0, 1))
            calls = []
            code, _ = self.lane(lambda *a: calls.append(1))
        self.assertEqual((code, calls), (0, []))

    def test_no_completion_stops_after_three_in_a_row(self):
        with patch("builtins.print"):
            code, attempts = self.lane(model_silent(), Args(n=3))
        self.assertEqual((code, len(attempts.rows)), (3, 3))

    def test_stop_file_ends_the_run_before_the_next_instance(self):
        (self.out / "STOP").write_text("")
        with patch("builtins.print"):
            code, attempts = self.lane(model_writing())
        self.assertEqual((code, attempts.rows), (0, []))

    def test_guard_stop_gives_exit_75(self):
        with patch("builtins.print"):
            runner = self.runner(FakeArw(), model_writing())
            attempts = rr.Attempts(self.out)
            guard = rr.Guard(self.out, 1)
            guard.calls = 2
            code = rr.run_lane(runner, Args(), self.out, guard, attempts, rr.pending_tasks(Args(), self.out, attempts))
        self.assertEqual(code, rr.STOP_EXIT)
        self.assertEqual(attempts.rows[0]["outcome"], "valid")


class Bundles(Base):
    def make_run(self, cell="hyd-high-code-spec-r1", iid="i-aaaaaaaaaaaa", commit=PIN["arw_commit"]):
        directory = self.out / "runs" / cell
        directory.mkdir(parents=True)
        run = {"id": iid, "arw": {"commit": commit, "treeDirty": False, "fixtureTree": PIN["fixture_tree"]}, "runtime": {"arwVersion": "9.9"},
               "settings": {"modelProvider": "agy"}, "report": "report.txt", "repair": None}
        (directory / "run.json").write_text(json.dumps(run))
        (directory / "report.txt").write_text("r")
        (directory / "driver.json").write_text(json.dumps({"harnessVersion": "1.2"}))
        return directory

    def bundle(self):
        path = self.root / "b.tar.gz"
        rr.pack_bundle(self.out, path)
        return path

    def test_round_trip_rewrites_report_to_the_local_copy(self):
        self.make_run()
        runs = self.root / "runs"
        result = rr.import_bundle(self.bundle(), runs, PIN)
        self.assertEqual(result["imported"], 1)
        run = json.loads((runs / "hyd-high-code-spec-r1" / "run.json").read_text())
        self.assertEqual(run["report"], str((runs / "hyd-high-code-spec-r1" / "report.txt").resolve()))
        with self.assertRaisesRegex(SystemExit, "--replace"):
            rr.import_bundle(self.bundle(), runs, PIN)
        rr.import_bundle(self.bundle(), runs, PIN, replace=True)

    def test_import_refuses_other_pin_duplicate_id_and_unfinished(self):
        self.make_run()
        bundle = self.bundle()
        with self.assertRaisesRegex(SystemExit, "not the pin"):
            rr.import_bundle(bundle, self.root / "r1", dict(PIN, arw_commit="c" * 40))
        existing = self.root / "r2" / "other-cell-r1"
        existing.mkdir(parents=True)
        (existing / "run.json").write_text(json.dumps({"id": "i-aaaaaaaaaaaa"}))
        with self.assertRaisesRegex(SystemExit, "already exists"):
            rr.import_bundle(bundle, self.root / "r2", PIN)

    def test_import_detects_tampering_and_bad_members(self):
        self.make_run()
        bundle = self.bundle()
        files = rr.read_bundle(bundle)

        def rebuild(change):
            path = self.root / "t.tar.gz"
            with tarfile.open(path, "w:gz") as tar:
                for name, data in change(dict(files)).items():
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    tar.addfile(info, io.BytesIO(data))
            return path
        with self.assertRaisesRegex(SystemExit, "does not match"):
            rr.import_bundle(rebuild(lambda f: dict(f, **{"runs/hyd-high-code-spec-r1/report.txt": b"changed"})), self.root / "x", PIN)
        with self.assertRaisesRegex(SystemExit, "not allowed"):
            rr.import_bundle(rebuild(lambda f: dict(f, **{"../evil": b"x"})), self.root / "x", PIN)
        with self.assertRaisesRegex(SystemExit, "not list"):
            rr.import_bundle(rebuild(lambda f: dict(f, **{"runs/hyd-high-code-spec-r1/extra.txt": b"x"})), self.root / "x", PIN)
        self.assertFalse((self.root / "x").exists())

    def test_pack_ignores_unfinished_instances(self):
        self.make_run()
        (self.out / "runs" / "hyd-high-code-spec-r2").mkdir()
        self.assertEqual(rr.pack_bundle(self.out, self.root / "b.tar.gz")["cells"], 1)


class RealProcess(unittest.TestCase):
    # These two start a real child process (about 50 ms each): the process-group stop is what a fake cannot show.
    def test_call_model_captures_output_and_stdin(self):
        call = rr.call_model([sys.executable, "-c", "import sys;print(sys.stdin.read().upper())"], ".", dict(os.environ), "abc", 10)
        self.assertEqual((call["rc"], call["out"].strip(), call["timed_out"]), (0, "ABC", False))

    def test_call_model_timeout_stops_the_command(self):
        started = time.monotonic()
        call = rr.call_model([sys.executable, "-c", "import time;time.sleep(30)"], ".", dict(os.environ), None, 0.05)
        self.assertTrue(call["timed_out"])
        self.assertLess(time.monotonic() - started, 5)


@unittest.skipUnless(os.environ.get("RB_ARW_DIR"), "set RB_ARW_DIR to an ARW checkout at the pin to run the end-to-end case")
class EndToEnd(unittest.TestCase):
    def test_real_arw_with_a_command_that_writes_a_report(self):
        # Runs node, git and the scenario setup for real (about 0.5 s, over the 100 ms of a unit case): the only case that shows the CLI's JSON shapes still fit.
        with tempfile.TemporaryDirectory() as d:
            config = Path(d) / "c.json"
            config.write_text(json.dumps({"command": [sys.executable, str(Path(rr.HERE) / "fake_model.py"), str(Path(d) / "report.txt")]}))
            (Path(d) / "report.txt").write_text("No findings.")
            out = Path(d) / "out"
            argv = ["run", "--arw", os.environ["RB_ARW_DIR"], "--config", str(config), "--model", "fake", "--efforts", "high",
                    "--scenarios", "code-spec", "--n", "1", "--out", str(out)]
            with patch("builtins.print"):
                self.assertEqual(rr.main(argv), 0)
            self.assertTrue((out / "runs" / "fake-high-code-spec-r1" / "driver.json").exists())


if __name__ == "__main__":
    unittest.main()
