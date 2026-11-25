"""The private question bank (.bank/): layout, test-set sealing and checks.

.bank/ is a nested git repository inside the public working copy.  The outer
.gitignore ignores it, it has no remote and its pre-push hook always refuses.
Only the test set is encrypted (gpg, symmetric); the key is one random file
outside every repository (default ~/.config/reviewer-bench/test-key).

Commands:  init | key | seal SRC_DIR | open DEST_DIR | check
"""

import argparse
import io
import os
import secrets
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BANK = ROOT / ".bank"
SUBDIRS = ("items", "keys", "split", "manifest", "notes", "results", "test")
SEALED = "test/test.tar.gpg"
PUSH_HOOK = """#!/bin/sh
echo "The question bank has no remote and is never pushed." >&2
exit 1
"""
BANK_IGNORE = "/test/plain/\n"


def key_path():
    return Path(os.environ.get("REVBENCH_KEY_FILE")
                or Path.home() / ".config" / "reviewer-bench" / "test-key")


def make_key(path):
    """Write a fresh random key (mode 0600); never overwrite an existing one."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(secrets.token_hex(32))
    return path


def _gpg(args, data, key):
    # 256 random bits need no key stretching, so the minimum s2k count is enough.
    command = ["gpg", "--batch", "--yes", "--no-tty", "--pinentry-mode", "loopback",
               "--passphrase-file", str(key), "--s2k-count", "65536", *args, "-o", "-"]
    done = subprocess.run(command, input=data, capture_output=True)
    if done.returncode:
        raise RuntimeError(f"gpg failed ({done.returncode}): {done.stderr.decode()[-200:]}")
    return done.stdout


def encrypt(data, key):
    return _gpg(["--symmetric", "--cipher-algo", "AES256"], data, key)


def decrypt(data, key):
    return _gpg(["--decrypt"], data, key)


def decrypt_with_default_key(data):
    return decrypt(data, key_path())


def pack_dir(src):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as tar:
        for path in sorted(Path(src).rglob("*")):
            tar.add(path, arcname=str(path.relative_to(src)), recursive=False)
    return buffer.getvalue()


def unpack_dir(data, dest):
    """Extract into dest; refuse (touching nothing) when a file would be overwritten."""
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        members = tar.getmembers()
        clashes = [m for m in members
                   if not m.isdir() and os.path.lexists(Path(dest, m.name))]
        if clashes:
            # Only the count is reported: member names are bank content.
            raise FileExistsError(f"{len(clashes)} file(s) in {dest} would be overwritten; "
                                  "open into an empty or new directory")
        tar.extractall(dest, members=members, filter="data")


def seal(src, out, key):
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(encrypt(pack_dir(src), key))


def open_sealed(sealed, dest, key):
    Path(dest).mkdir(parents=True, exist_ok=True)
    unpack_dir(decrypt(Path(sealed).read_bytes(), key), dest)


def git(*args, cwd):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def init_bank(bank=BANK):
    """Create the nested repository with its folders and the refusing pre-push hook."""
    bank = Path(bank)
    if not (bank / ".git").exists():
        bank.mkdir(parents=True, exist_ok=True)
        git("init", "-q", "-b", "main", cwd=bank)
    for name in SUBDIRS:
        (bank / name).mkdir(exist_ok=True)
        keep = bank / name / ".gitkeep"
        keep.touch()
    (bank / ".gitignore").write_text(BANK_IGNORE)
    hook = bank / ".git" / "hooks" / "pre-push"
    hook.write_text(PUSH_HOOK)
    hook.chmod(0o755)
    git("add", "-A", cwd=bank)
    if git("status", "--porcelain", cwd=bank).strip():
        git("-c", "user.name=bench", "-c", "user.email=bench@localhost",
            "commit", "-q", "-m", "Bank skeleton", cwd=bank)
    return bank


def check(root=ROOT, key=None):
    """Return a list of (ok, what) lines about the bank's safety setup."""
    root, bank = Path(root), Path(root) / ".bank"
    key = Path(key) if key else key_path()

    def run(*args, cwd=root):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)

    tracked = [p for p in run("ls-files", "-z").stdout.split("\0")
               if p == ".bank" or p.startswith(".bank/")]
    hooks = run("rev-parse", "--git-path", "hooks").stdout.strip()
    hooks = Path(root, hooks) if not os.path.isabs(hooks) else Path(hooks)
    bank_hook = bank / ".git" / "hooks" / "pre-push"
    refused = bank_hook.exists() and subprocess.run([str(bank_hook)], capture_output=True).returncode != 0
    return [
        (run("check-ignore", "-q", ".bank").returncode == 0, ".bank is ignored by the outer repository"),
        (not tracked, "no .bank path is tracked by the outer repository"),
        ((bank / ".git").is_dir(), ".bank is its own git repository"),
        (bank.is_dir() and not run("remote", cwd=bank).stdout.strip(), ".bank has no remote"),
        (refused, ".bank pre-push hook refuses"),
        ((hooks / "pre-commit").exists() and (hooks / "pre-push").exists(),
         "outer pre-commit and pre-push hooks are installed"),
        (key.exists() and (key.stat().st_mode & 0o077) == 0, "test-set key exists with mode 0600"),
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init", help="create .bank/ and the test-set key if missing")
    sub.add_parser("key", help="print the key file path (not its content)")
    sub.add_parser("check", help="report the safety setup")
    sub.add_parser("seal", help="encrypt a directory into .bank/test/").add_argument("src")
    sub.add_parser("open", help="decrypt the test set into a directory").add_argument("dest")
    args = parser.parse_args(argv)
    if args.cmd == "init":
        init_bank()
        if not key_path().exists():
            make_key(key_path())
            print(f"new key written to {key_path()}; save a copy outside this machine")
        return 0
    if args.cmd == "key":
        print(key_path())
        return 0
    if args.cmd == "seal":
        seal(args.src, BANK / SEALED, key_path())
        return 0
    if args.cmd == "open":
        open_sealed(BANK / SEALED, args.dest, key_path())
        return 0
    lines = check()
    for ok, what in lines:
        print(("ok   " if ok else "FAIL ") + what)
    return 0 if all(ok for ok, _ in lines) else 1


if __name__ == "__main__":
    sys.exit(main())
