import json
import unittest
from pathlib import Path

import support
import materialize


class MaterializeTests(support.TempCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.src = support.new_repo(cls.tmp / "src")
        cls.c0 = support.commit_file(cls.src, "app/a.py", "x = 1\n", "base")
        cls.c1 = support.commit_file(cls.src, "app/a.py", "x = 2\n", "step one\n\nbody line")
        Path(cls.src, "docs").mkdir()
        Path(cls.src, "docs/n.md").write_text("n\n")
        Path(cls.src, "app/blob.bin").write_bytes(bytes(range(256)))
        support.git(cls.src, "add", "-A")
        support.git(cls.src, "commit", "-q", "-m", "step two")
        cls.c2 = support.git(cls.src, "rev-parse", "HEAD")
        cls.c3 = support.commit_file(cls.src, "app/a.py", "x = 3  # the later fix\n", "later fix")
        cls.item = {"base": cls.c0, "commits": [cls.c1, cls.c2]}
        cls.dest = cls.tmp / "out"
        cls.ids = materialize.materialize(cls.src, cls.item, cls.dest)

    def test_tree_equals_the_question_head_and_history_stops_there(self):
        self.assertEqual(Path(self.dest, "app/a.py").read_text(), "x = 2\n")
        self.assertEqual(Path(self.dest, "app/blob.bin").read_bytes(), bytes(range(256)))
        log = support.git(self.dest, "log", "--format=%s")
        self.assertEqual(log.splitlines(), ["step two", "step one", "Baseline"])
        self.assertEqual(support.git(self.dest, "log", "-1", "--skip=1", "--format=%B").strip(), "step one\n\nbody line")

    def test_nothing_of_the_source_history_is_reachable(self):
        objects = support.git(self.dest, "cat-file", "--batch-all-objects", "--batch-check")
        for sha in (self.c0, self.c1, self.c2, self.c3):
            self.assertNotIn(sha, objects)
            self.assertNotIn(sha, self.ids)
        self.assertNotIn("later fix", support.git(self.dest, "log", "--all", "--format=%B"))

    def test_ids_are_reproducible_and_author_fixed(self):
        again = materialize.materialize(self.src, self.item, self.tmp / "out2")
        self.assertEqual(again, self.ids)
        self.assertEqual(support.git(self.dest, "log", "-1", "--format=%an <%ae> %at"),
                         f"bench <bench@example.invalid> {materialize.EPOCH + 2 * 3600}")

    def test_paths_limit_baseline_and_diffs_and_planted_patch_is_a_commit(self):
        planted = ("diff --git a/app/a.py b/app/a.py\n--- a/app/a.py\n+++ b/app/a.py\n"
                   "@@ -1 +1 @@\n-x = 2\n+x = 0\n")
        item = {**self.item, "paths": ["app/a.py"], "planted": [{"patch": planted, "message": "tidy"}]}
        ids = materialize.materialize(self.src, item, self.tmp / "out3")
        self.assertEqual(len(ids), 4)
        self.assertFalse(Path(self.tmp, "out3", "docs").exists())
        self.assertEqual(Path(self.tmp, "out3", "app/a.py").read_text(), "x = 0\n")
        self.assertEqual(support.git(self.tmp / "out3", "log", "-1", "--format=%s"), "tidy")

    def test_merge_commit_and_non_empty_destination_are_rejected(self):
        with self.assertRaises(ValueError):
            materialize.materialize(self.src, self.item, self.dest)
        support.git(self.src, "checkout", "-q", "-b", "side", self.c1)
        side = support.commit_file(self.src, "side.txt", "s\n", "side")
        support.git(self.src, "checkout", "-q", "main")
        support.git(self.src, "merge", "-q", "--no-ff", "-m", "merge", side)
        merge = support.git(self.src, "rev-parse", "HEAD")
        with self.assertRaises(ValueError):
            materialize.materialize(self.src, {"base": self.c0, "commits": [merge]}, self.tmp / "out4")

    def test_hub_lite_copies_only_the_named_files(self):
        materialize.hub_lite(self.src, self.c1, ["app/a.py"], self.tmp / "lite")
        self.assertEqual([p.name for p in Path(self.tmp, "lite").rglob("*") if p.is_file()], ["a.py"])
        self.assertEqual(Path(self.tmp, "lite", "app/a.py").read_text(), "x = 2\n")


if __name__ == "__main__":
    unittest.main()
