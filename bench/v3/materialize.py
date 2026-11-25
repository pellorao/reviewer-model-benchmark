"""Turn a question pointer into the repository a reviewing model sees.

An item is a pointer (JSON): the source repository's baseline commit, the
question's commits in order, optional planted patches and an optional path
block for full mode.  The result is a brand-new repository: the baseline
squashed into one commit, the question commits replayed as new commits with a
fixed author and dates, and nothing after them.  A model that reads the git
history therefore cannot reach the later fix, and the new commit ids do not map
back to the source repository.

Item keys:  base (rev), commits (list of revs, oldest first),
            planted (list of {"patch": text, "message": text}),
            paths (optional list; limits the baseline and every replayed diff)
"""

import argparse
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

AUTHOR = ("bench", "bench@example.invalid")
EPOCH = 1577836800  # 2020-01-01T00:00:00Z; commit n gets EPOCH + n * 3600
GIT_ENV = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def _env(index):
    stamp = f"{EPOCH + index * 3600} +0000"
    return {**os.environ, **GIT_ENV, "GIT_AUTHOR_NAME": AUTHOR[0], "GIT_AUTHOR_EMAIL": AUTHOR[1],
            "GIT_COMMITTER_NAME": AUTHOR[0], "GIT_COMMITTER_EMAIL": AUTHOR[1],
            "GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}


def _git(repo, *args, data=None, env=None, binary=False):
    done = subprocess.run(["git", *args], cwd=repo, input=data, capture_output=True,
                          env=env or {**os.environ, **GIT_ENV})
    if done.returncode:
        raise RuntimeError(f"git {args[0]} failed: {done.stderr.decode('utf-8', 'replace')[-300:]}")
    return done.stdout if binary else done.stdout.decode("utf-8", "replace")


def archive_to(repo, rev, dest, paths=()):
    """Extract the tree of rev (limited to paths) into dest, no history."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(["git", "archive", rev, *(["--", *paths] if paths else [])], cwd=repo,
                            stdout=subprocess.PIPE, env={**os.environ, **GIT_ENV})
    with proc, tarfile.open(fileobj=proc.stdout, mode="r|") as tar:
        tar.extractall(dest, filter="data")
    if proc.returncode:
        raise RuntimeError("git archive failed")


def _commit(dest, message, index):
    _git(dest, "add", "-A")
    _git(dest, "commit", "-q", "--allow-empty", "--cleanup=verbatim", "-F", "-",
         data=message.encode("utf-8"), env=_env(index))
    return _git(dest, "rev-parse", "HEAD").strip()


def materialize(source, item, dest):
    """Build the repository at dest (must be empty or absent); return its new commit ids."""
    dest = Path(dest)
    if dest.exists() and any(dest.iterdir()):
        raise ValueError(f"{dest} is not empty")
    paths = item.get("paths") or []
    archive_to(source, item["base"], dest, paths)
    _git(dest, "init", "-q", "-b", "main")
    ids = [_commit(dest, "Baseline", 0)]
    for number, rev in enumerate(item["commits"], 1):
        parents = _git(source, "rev-list", "--parents", "-n", "1", rev).split()[1:]
        if len(parents) != 1:
            raise ValueError("only single-parent commits can be replayed")
        diff = _git(source, "diff", "--binary", "--full-index", parents[0], rev,
                    *(["--", *paths] if paths else []), binary=True)
        if diff:
            _git(dest, "apply", "--index", "--binary", "-", data=diff)
        ids.append(_commit(dest, _git(source, "log", "-1", "--format=%B", rev).rstrip("\n") + "\n",
                           len(ids)))
    for planted in item.get("planted", ()):
        _git(dest, "apply", "--index", "-", data=planted["patch"].encode("utf-8"))
        ids.append(_commit(dest, planted["message"].rstrip("\n") + "\n", len(ids)))
    return ids


def hub_lite(source, rev, paths, dest):
    """Read-only copy of the rule files as they were at rev (no history, no tasks)."""
    archive_to(source, rev, dest, paths)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", help="source repository")
    parser.add_argument("item", help="item pointer JSON file")
    parser.add_argument("dest", help="empty directory (use tmpfs) for the new repository")
    args = parser.parse_args(argv)
    ids = materialize(args.source, json.loads(Path(args.item).read_text("utf-8")), args.dest)
    print("\n".join(ids))
    return 0


if __name__ == "__main__":
    sys.exit(main())
