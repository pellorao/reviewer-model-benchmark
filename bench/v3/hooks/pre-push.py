"""Outer pre-push: refuse .bank paths and question-bank material in the pushed range."""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import hookcheck  # noqa: E402

root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                      text=True, check=True).stdout.strip()
sys.exit(hookcheck.run_hook(*hookcheck.check_push(root, sys.argv[1], sys.stdin.read().splitlines()), "push"))
