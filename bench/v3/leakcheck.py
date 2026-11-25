"""Leak check: does a text carry material from the private question bank?

This file holds only the detection logic and is public.  What to look for lives
in the bank's hash manifest (.bank/manifest/*.json), which never leaves the
bank repository: it stores only SHA-256 hashes, so a leaked manifest does not
reveal the questions either.  Findings report the kind and the line number,
never the matched text, so logs and hook output cannot leak what they find.

Manifest format (all lists hold lowercase hex SHA-256 digests):
  {"version": 1,
   "commit7":  [sha256(first 7 hex chars of a workshop commit)],
   "tokens":   [sha256(lowercased identifier or id)],
   "shingles": [sha256(8 consecutive lowercased words joined by a space)]}
Besides the manifest, two shapes always count as a leak: an opaque question id
(w3-<12 hex>) and a canary string (RBCANARY-<hex>).
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SHINGLE = 8
HEX_RUN = re.compile(r"(?<![0-9A-Za-z])[0-9a-f]{7,64}(?![0-9A-Za-z])")
TOKEN = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_\-]{5,}")
WORD = re.compile(r"\w+")
ALWAYS = (("item-id", re.compile(r"\bw3-[0-9a-f]{12}\b")),
          ("canary", re.compile(r"RBCANARY-[0-9a-f]{8,}")))
MAX_BYTES = 5_000_000


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def empty_manifest():
    return {"commit7": set(), "tokens": set(), "shingles": set()}


def build_manifest(commits=(), tokens=(), texts=()):
    """Hash manifest for workshop commit ids, identifiers and passages of text."""
    shingles = set()
    for text in texts:
        words = [w.lower() for w in WORD.findall(text)]
        shingles.update(digest(" ".join(words[i:i + SHINGLE]))
                        for i in range(len(words) - SHINGLE + 1))
    return {"version": 1,
            "commit7": sorted({digest(c.lower()[:7]) for c in commits}),
            "tokens": sorted({digest(t.lower()) for t in tokens}),
            "shingles": sorted(shingles)}


def merge_manifest(into, data):
    for key in ("commit7", "tokens", "shingles"):
        into[key].update(data.get(key, ()))
    return into


def load_manifest(directory, decrypt=None):
    """Merge every manifest/*.json; a missing directory gives the pattern-only check.

    Files ending in .json.gpg are the test set's part; decrypt(bytes) opens them.
    Returns (manifest, notes) where notes lists parts that could not be read.
    """
    manifest, notes = empty_manifest(), []
    directory = Path(directory)
    for path in sorted(directory.glob("*.json")) if directory.is_dir() else ():
        merge_manifest(manifest, json.loads(path.read_text("utf-8")))
    for path in sorted(directory.glob("*.json.gpg")) if directory.is_dir() else ():
        try:
            merge_manifest(manifest, json.loads(decrypt(path.read_bytes())))
        except Exception as error:  # the key may be absent on this machine
            notes.append(f"{path.name} not checked ({type(error).__name__})")
    return manifest, notes


def scan_text(text, manifest):
    """Return sorted (kind, line) pairs for every hit; never the text itself."""
    hits = set()
    for number, line in enumerate(text.splitlines(), 1):
        for kind, pattern in ALWAYS:
            if pattern.search(line):
                hits.add((kind, number))
        for run in HEX_RUN.findall(line):
            if digest(run[:7]) in manifest["commit7"]:
                hits.add(("commit", number))
        for token in TOKEN.findall(line):
            if digest(token.lower()) in manifest["tokens"]:
                hits.add(("token", number))
    if manifest["shingles"]:
        words = [(w.lower(), n) for n, line in enumerate(text.splitlines(), 1)
                 for w in WORD.findall(line)]
        for i in range(len(words) - SHINGLE + 1):
            if digest(" ".join(w for w, _ in words[i:i + SHINGLE])) in manifest["shingles"]:
                hits.add(("passage", words[i][1]))
    return sorted(hits)


def scan_bytes(data, manifest):
    """Binary blobs and oversized files are skipped; the caller can see the empty result."""
    if len(data) > MAX_BYTES or b"\0" in data[:8192]:
        return []
    return scan_text(data.decode("utf-8", "replace"), manifest)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scan files for question-bank material.")
    parser.add_argument("paths", nargs="+", help="files to scan")
    parser.add_argument("--bank", default=str(Path(__file__).resolve().parents[2] / ".bank"))
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import bank
    manifest, notes = load_manifest(Path(args.bank) / "manifest", bank.decrypt_with_default_key)
    for note in notes:
        print(f"leakcheck: {note}", file=sys.stderr)
    found = 0
    for name in args.paths:
        for kind, line in scan_bytes(Path(name).read_bytes(), manifest):
            print(f"{name}:{line}: {kind}")
            found += 1
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
