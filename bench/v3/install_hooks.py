"""Install the outer repository's hooks (one-line wrappers into bench/v3/hooks/).

Run once per clone:  python3 -I bench/v3/install_hooks.py
Hooks under .git/hooks are not tracked, so a fresh clone needs this command.
An existing hook that is not ours is left alone unless --force is given.
"""

import argparse
import subprocess
import sys
from pathlib import Path

NAMES = ("pre-commit", "pre-push")
MARK = "# reviewer-bench v3 hook"
WRAPPER = """#!/bin/sh
{mark}
root=$(git rev-parse --show-toplevel) || exit 1
exec python3 -I "$root/bench/v3/hooks/{name}.py" "$@"
"""


def install(root, force=False):
    hooks = subprocess.run(["git", "rev-parse", "--git-path", "hooks"], cwd=root,
                           capture_output=True, text=True, check=True).stdout.strip()
    hooks = Path(root, hooks)
    hooks.mkdir(parents=True, exist_ok=True)
    done = []
    for name in NAMES:
        target = hooks / name
        if target.exists() and MARK not in target.read_text() and not force:
            raise SystemExit(f"{target} exists and is not ours; use --force to replace it")
        target.write_text(WRAPPER.format(mark=MARK, name=name))
        target.chmod(0o755)
        done.append(str(target))
    return done


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args(argv)
    for path in install(args.root, args.force):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
