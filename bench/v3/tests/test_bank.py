import os
import stat
import subprocess
import unittest
from pathlib import Path

import support
import bank
import install_hooks


class KeyAndSealTests(support.TempCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        home = cls.tmp / "gnupg"
        home.mkdir(mode=0o700)
        cls._old = os.environ.get("GNUPGHOME")
        os.environ["GNUPGHOME"] = str(home)
        cls.key = bank.make_key(cls.tmp / "cfg" / "key")
        cls.other = bank.make_key(cls.tmp / "cfg" / "other")

    @classmethod
    def tearDownClass(cls):
        if cls._old is None:
            del os.environ["GNUPGHOME"]
        else:
            os.environ["GNUPGHOME"] = cls._old
        super().tearDownClass()

    def test_key_is_private_random_and_never_overwritten(self):
        self.assertEqual(stat.S_IMODE(self.key.stat().st_mode), 0o600)
        self.assertEqual(len(self.key.read_text()), 64)
        self.assertNotEqual(self.key.read_text(), self.other.read_text())
        with self.assertRaises(FileExistsError):
            bank.make_key(self.key)

    def test_round_trip_hides_plaintext_and_wrong_key_fails(self):
        sealed = bank.encrypt(b"answer: line 42", self.key)
        self.assertNotIn(b"answer", sealed)
        self.assertEqual(bank.decrypt(sealed, self.key), b"answer: line 42")
        with self.assertRaises(RuntimeError):
            bank.decrypt(sealed, self.other)

    def test_sealed_directory_round_trip(self):
        src = self.tmp / "plain"
        (src / "sub").mkdir(parents=True)
        (src / "sub" / "q1.json").write_text('{"id": 1}')
        (src / "q2.txt").write_text("two")
        out = self.tmp / "bank-test" / "test.tar.gpg"
        bank.seal(src, out, self.key)
        bank.open_sealed(out, self.tmp / "opened", self.key)
        self.assertEqual((self.tmp / "opened" / "sub" / "q1.json").read_text(), '{"id": 1}')
        self.assertEqual((self.tmp / "opened" / "q2.txt").read_text(), "two")


class InitAndCheckTests(support.TempCase):
    def test_init_builds_skeleton_without_remote_and_refuses_push(self):
        root = support.new_repo(self.tmp / "outer")
        (root / ".gitignore").write_text("/.bank/\n")
        install_hooks.install(root)
        key = bank.make_key(self.tmp / "k" / "key")
        bank.init_bank(root / ".bank")
        bank.init_bank(root / ".bank")  # idempotent
        for name in bank.SUBDIRS:
            self.assertTrue((root / ".bank" / name).is_dir())
        self.assertEqual(support.git(root / ".bank", "remote"), "")
        self.assertEqual(support.git(root / ".bank", "rev-list", "--count", "HEAD"), "1")
        self.assertNotEqual(subprocess.run([root / ".bank/.git/hooks/pre-push"]).returncode, 0)
        self.assertEqual(support.git(root, "ls-files"), "")
        results = bank.check(root, key)
        self.assertEqual([what for ok, what in results if not ok], [])

    def test_check_fails_when_unprotected(self):
        root = support.new_repo(self.tmp / "bare")
        support.git(root, "commit", "-q", "--allow-empty", "-m", "x")
        failed = {what for ok, what in bank.check(root, self.tmp / "missing") if not ok}
        self.assertIn(".bank is ignored by the outer repository", failed)
        self.assertIn("outer pre-commit and pre-push hooks are installed", failed)
        self.assertIn("test-set key exists with mode 0600", failed)


if __name__ == "__main__":
    unittest.main()
