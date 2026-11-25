import json
import subprocess
import unittest
from pathlib import Path

import support
import hookcheck
import install_hooks
import leakcheck

TOKEN = "SecretIdentifier"


def outer_repo(tmp, name, nested=False):
    root = support.new_repo(tmp / name)
    (root / ".gitignore").write_text("/.bank/\n")
    (root / ".bank" / "manifest").mkdir(parents=True)
    if nested:
        support.git(root / ".bank", "init", "-q")
    (root / ".bank" / "manifest" / "m.json").write_text(
        json.dumps(leakcheck.build_manifest(tokens=[TOKEN])))
    support.git(root, "add", ".gitignore")
    support.git(root, "commit", "-q", "-m", "init")
    return root


class StagedTests(support.TempCase):
    def test_clean_file_passes_and_leak_names_file_and_line_only(self):
        root = outer_repo(self.tmp, "staged")
        (root / "ok.txt").write_text("nothing here\n")
        (root / "bad.txt").write_text(f"x\n{TOKEN}\n")
        support.git(root, "add", "ok.txt", "bad.txt")
        problems, notes = hookcheck.check_staged(root)
        self.assertEqual(problems, ["bad.txt:2: token"])
        self.assertEqual(notes, [])

    def test_forced_add_inside_the_nested_repository_stages_nothing(self):
        root = outer_repo(self.tmp, "forced", nested=True)
        (root / ".bank" / "q.txt").write_text("question")
        support.git(root, "add", "-f", ".bank/q.txt")
        self.assertEqual(support.git(root, "diff", "--cached", "--name-only"), "")
        self.assertEqual(hookcheck.check_staged(root)[0], [])

    def test_bank_file_staged_without_a_nested_repository_is_refused(self):
        root = outer_repo(self.tmp, "loose")
        (root / ".bank" / "q.txt").write_text("question")
        support.git(root, "add", "-f", ".bank/q.txt")
        self.assertEqual(hookcheck.check_staged(root)[0], [".bank/q.txt: path under .bank is staged"])

    def test_gitlink_of_nested_repository_is_refused(self):
        root = support.new_repo(self.tmp / "gitlink")
        support.git(root, "commit", "-q", "--allow-empty", "-m", "init")
        nested = support.new_repo(root / ".bank")
        support.git(nested, "commit", "-q", "--allow-empty", "-m", "n")
        support.git(root, "add", ".bank")  # no ignore line: git records a gitlink
        self.assertEqual(hookcheck.check_staged(root)[0], [".bank: path under .bank is staged"])


class PushTests(support.TempCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = outer_repo(cls.tmp, "push")
        cls.base = support.git(cls.root, "rev-parse", "HEAD")
        support.commit_file(cls.root, "a.txt", "fine\n", "fine change")
        support.commit_file(cls.root, "b.txt", f"{TOKEN}\n", "adds a leak")
        support.commit_file(cls.root, "b.txt", "removed again\n", f"mentions {TOKEN} in message")
        cls.head = support.git(cls.root, "rev-parse", "HEAD")

    def push(self, local, remote_sha):
        line = f"refs/heads/main {local} refs/heads/main {remote_sha}"
        return hookcheck.check_push(self.root, "origin", [line])[0]

    def test_range_checks_content_of_every_commit_and_the_messages(self):
        problems = self.push(self.head, self.base)
        self.assertEqual(sorted(p.split(" ", 1)[1] for p in problems), ["b.txt:1: token", "message:1: token"])

    def test_new_branch_covers_all_commits_not_on_the_remote(self):
        self.assertEqual(len(self.push(self.head, hookcheck.ZERO)), 2)

    def test_clean_range_and_delete_pass(self):
        first = support.git(self.root, "rev-list", "--reverse", "HEAD").split()[1]
        self.assertEqual(self.push(first, self.base), [])
        self.assertEqual(self.push(hookcheck.ZERO, self.head), [])

    def test_bank_path_in_a_commit_is_refused(self):
        root = support.new_repo(self.tmp / "pushbank")
        support.git(root, "commit", "-q", "--allow-empty", "-m", "init")
        base = support.git(root, "rev-parse", "HEAD")
        support.commit_file(root, ".bank/q.txt", "plain\n", "oops")
        line = f"refs/heads/main {support.git(root, 'rev-parse', 'HEAD')} refs/heads/main {base}"
        self.assertEqual([p.split(" ", 1)[1] for p in hookcheck.check_push(root, "origin", [line])[0]],
                         [".bank/q.txt: path under .bank"])


class InstallTests(support.TempCase):
    def test_wrappers_run_the_checks_through_a_real_commit(self):
        root = outer_repo(self.tmp, "real")
        (root / "bench").symlink_to(Path(install_hooks.__file__).resolve().parents[1])
        install_hooks.install(root)
        (root / "bad.txt").write_text(f"{TOKEN}\n")
        support.git(root, "add", "bad.txt")
        done = subprocess.run(["git", "commit", "-q", "-m", "try"], cwd=root, capture_output=True,
                              text=True, env=support.ENV)
        self.assertEqual(done.returncode, 1)
        self.assertIn("bad.txt:1: token", done.stderr)
        self.assertNotIn(TOKEN, done.stderr)

    def test_foreign_hook_is_kept_unless_forced(self):
        root = support.new_repo(self.tmp / "foreign")
        hook = root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 0\n")
        with self.assertRaises(SystemExit):
            install_hooks.install(root)
        self.assertEqual(hook.read_text(), "#!/bin/sh\nexit 0\n")
        install_hooks.install(root, force=True)
        self.assertIn(install_hooks.MARK, hook.read_text())


if __name__ == "__main__":
    unittest.main()
