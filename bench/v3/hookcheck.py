"""Git-side checks for the outer repository's hooks (pre-commit, pre-push).

Both refuse any path under .bank (a gitlink included, so not even the nested
repository's commit id reaches the public history) and run leakcheck over the
content.  pre-push covers the whole pushed range, commit messages included.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bank  # noqa: E402
import leakcheck  # noqa: E402

ZERO = "0" * 40


def git(root, *args, data=False):
    done = subprocess.run(["git", *args], cwd=root, capture_output=True, check=True)
    return done.stdout if data else done.stdout.decode("utf-8", "replace")


def blob_text(root, spec):
    """Blob bytes, or b"" when it is over the scan limit (checked before reading it)."""
    if int(git(root, "cat-file", "-s", spec)) > leakcheck.MAX_BYTES:
        return b""
    return git(root, "cat-file", "blob", spec, data=True)


def is_bank_path(path):
    return path == ".bank" or path.startswith(".bank/") or "/.bank/" in path


def manifest_for(root):
    return leakcheck.load_manifest(Path(root) / ".bank" / "manifest", bank.decrypt_with_default_key)


def check_staged(root):
    """Problems in the index: list of strings (empty means clean)."""
    manifest, notes = manifest_for(root)
    problems = []
    names = git(root, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR").split("\0")
    for name in filter(None, names):
        if is_bank_path(name):
            problems.append(f"{name}: path under .bank is staged")
            continue
        for kind, line in leakcheck.scan_bytes(blob_text(root, f":{name}"), manifest):
            problems.append(f"{name}:{line}: {kind}")
    return problems, notes


def commits_to_push(root, remote, local, remote_sha):
    if local == ZERO:
        return []
    if remote_sha == ZERO:
        spec = [local, "--not", f"--remotes={remote}"]
    else:
        spec = [f"{remote_sha}..{local}"]
    return git(root, "rev-list", *spec).split()


def check_commit(root, sha, manifest):
    problems = []
    short = sha[:10]
    for kind, line in leakcheck.scan_text(git(root, "log", "-1", "--format=%B", sha), manifest):
        problems.append(f"{short} message:{line}: {kind}")
    raw = git(root, "diff-tree", "-r", "-m", "--root", "--no-renames", "--no-commit-id", "-z", "--raw", sha)
    fields = raw.split("\0")
    seen = set()
    for meta, name in zip(fields[0::2], fields[1::2]):
        if not meta:
            continue
        mode, blob, status = meta.split()[1], meta.split()[3], meta.split()[4][0]
        if is_bank_path(name):
            problems.append(f"{short} {name}: path under .bank")
        elif status != "D" and mode != "160000" and blob not in seen:
            seen.add(blob)
            for kind, line in leakcheck.scan_bytes(blob_text(root, blob), manifest):
                problems.append(f"{short} {name}:{line}: {kind}")
    return problems


def check_push(root, remote, stdin_lines):
    manifest, notes = manifest_for(root)
    problems = []
    for line in stdin_lines:
        parts = line.split()
        if len(parts) != 4:
            continue
        _, local, _, remote_sha = parts
        for sha in commits_to_push(root, remote, local, remote_sha):
            problems += check_commit(root, sha, manifest)
    return problems, notes


def run_hook(problems, notes, what):
    for note in notes:
        print(f"leakcheck: {note}", file=sys.stderr)
    for problem in problems:
        print(f"leakcheck: {problem}", file=sys.stderr)
    if problems:
        print(f"leakcheck: {what} refused; no hook may be skipped, fix the content.", file=sys.stderr)
        return 1
    return 0
