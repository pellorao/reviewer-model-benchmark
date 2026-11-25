"""Shared helpers: synthetic repositories and an isolated gpg home (no real questions)."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
       "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
       "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def git(cwd, *args, data=None):
    done = subprocess.run(["git", *args], cwd=cwd, input=data, capture_output=True, text=True, env=ENV)
    if done.returncode:
        raise RuntimeError(f"git {args}: {done.stderr}")
    return done.stdout.strip()


def new_repo(path):
    Path(path).mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    return Path(path)


def commit_file(repo, name, text, message):
    target = Path(repo, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


class TempCase(unittest.TestCase):
    """A per-class temp directory (tmpfs through TMPDIR) removed afterwards."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="v3test-")
        cls.tmp = Path(cls._tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()
