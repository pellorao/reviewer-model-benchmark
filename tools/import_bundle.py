#!/usr/bin/env python3
"""Verify a pinned ARW result bundle and record it as an immutable snapshot."""

import argparse
from datetime import datetime, timedelta
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import tarfile
import zlib

ROOT = Path(__file__).resolve().parents[1]
ARW_ORIGIN = {
    "commit": "83bdb6b4f5ec39e7b32b30862a9ece24aa9b7fc6",
    "fixtureTree": "4326aca3cbd04ae126f6f4a3e26867f2b740e81a",
    "treeDirty": False,
}
# Bundles packed by the retired tools/remote_run pin this earlier ARW commit; the fixture tree is the same.
# That packer also stored its unlisted attempt log, attempts.jsonl, in the archive.
LEGACY_ARW_ORIGIN = {**ARW_ORIGIN, "commit": "6ca23a9d5b9d1116a9690bbbc39b42a408b8df07"}
AGY_ARW_ORIGIN = {**ARW_ORIGIN, "commit": "3901f02e1fe234b76bba722fd9fe5f4ccaedc264"}
ARW_ORIGINS = (ARW_ORIGIN, LEGACY_ARW_ORIGIN, AGY_ARW_ORIGIN)
SCENARIOS = ("commit-audit", "code-spec", "code-standards", "spec-readiness")
LABEL = r"[A-Za-z0-9][A-Za-z0-9._]*(?:-[A-Za-z0-9._]+)*"
CELL_NAME = re.compile(rf"(?P<labels>{LABEL})-(?:{'|'.join(SCENARIOS)})-r[1-9][0-9]*")
REQUIRED = {"run.json", "driver.json", "agent.json", "score.json"}
REPORTS = {"report.txt", "report.md", "report.jsonl"}
ALLOWED = REQUIRED | REPORTS | {"candidates.json", "repair.json", "agy.jsonl"}
MAX_FILE_BYTES = 50_000_000
MAX_BUNDLE_BYTES = 500_000_000
MAX_TAR_METADATA_BYTES = 64 * 1024


class BundleMember(tarfile.TarInfo):
    def _proc_member(self, archive):
        # GNU and PAX long-path headers are handled before iteration yields a member.
        if self.type in (tarfile.GNUTYPE_LONGNAME, tarfile.XHDTYPE, tarfile.XGLTYPE, tarfile.SOLARIS_XHDTYPE):
            if not 0 <= self.size <= MAX_TAR_METADATA_BYTES:
                raise ValueError("Tar metadata exceeds the size limit")
        elif self.type not in (tarfile.REGTYPE, tarfile.AREGTYPE):
            raise ValueError(f"Bundle member must be a regular file: {self.name!r}")
        return super()._proc_member(archive)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key {key!r}")
        result[key] = value
    return result


def read_object(data, name):
    try:
        value = json.loads(data, object_pairs_hook=unique_object)
        if not isinstance(value, dict):
            raise ValueError("Expected a JSON object")
    except (ValueError, RecursionError) as error:
        raise ValueError(f"Invalid {name}: {error}") from error
    return value


def read_members(archive, stream):
    members = {}
    for member in archive:
        if member.sparse is not None or member.linkname:
            raise ValueError(f"Bundle member must be a regular file: {member.name!r}")
        if member.name in members:
            raise ValueError(f"Duplicate archive path: {member.name!r}")
        if not 0 <= member.size <= MAX_FILE_BYTES or archive.offset > MAX_BUNDLE_BYTES:
            raise ValueError("Bundle exceeds the size limits")
        members[member.name] = member

    # tarfile stops at the first end block. Check the terminator and gzip footer too.
    stream.seek(archive.offset)
    tail_size = 0
    for chunk in iter(lambda: stream.read(64 * 1024), b""):
        tail_size += len(chunk)
        if chunk.strip(b"\0") or archive.offset + tail_size > MAX_BUNDLE_BYTES:
            raise ValueError("Unexpected data after the last tar member")
    if tail_size < 2 * tarfile.BLOCKSIZE or tail_size % tarfile.BLOCKSIZE:
        raise ValueError("Missing tar end blocks")
    return members


def manifest_files(manifest):
    if any(type(manifest.get(key)) is not int or manifest[key] != 1 for key in ("schema", "tool")):
        raise ValueError("Unsupported bundle schema or tool version")
    created = manifest.get("created")
    if (not isinstance(created, str) or "T" not in created
            or datetime.fromisoformat(created).utcoffset() != timedelta(0)):
        raise ValueError("Manifest created must be a UTC ISO 8601 timestamp")
    origin = manifest.get("arw")
    if origin not in ARW_ORIGINS or origin["treeDirty"] is not False:
        raise ValueError("Bundle must use a pinned clean ARW commit and fixture tree")
    harness = manifest.get("harness")
    if (not isinstance(harness, dict) or not isinstance(harness.get("provider"), str)
            or not isinstance(harness.get("version"), str)
            or not isinstance(manifest.get("arwVersion"), str) or not manifest["arwVersion"]):
        raise ValueError("Manifest must record the ARW version and harness identity")
    cells = manifest.get("cells")
    if not isinstance(cells, list) or not cells:
        raise ValueError("Manifest must list at least one instance")

    directories = {}
    for cell in cells:
        name = cell.get("dir") if isinstance(cell, dict) else None
        match = CELL_NAME.fullmatch(name) if isinstance(name, str) else None
        if not match or not re.search(r"-[A-Za-z0-9]", match["labels"]) or name in directories:
            raise ValueError(f"Invalid or duplicate instance directory: {name!r}")
        files = cell.get("files")
        if (not isinstance(files, dict) or not REQUIRED <= files.keys() <= ALLOWED
                or len(REPORTS & files.keys()) > 1):
            raise ValueError(f"{name}: invalid instance file set")
        for filename, record in files.items():
            if (not isinstance(record, dict) or type(record.get("bytes")) is not int
                    or record["bytes"] < 0 or not isinstance(record.get("sha256"), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])):
                raise ValueError(f"{name}/{filename}: invalid manifest byte count or SHA-256")
        directories[name] = files
    return directories


def verify_run(name, files, run, manifest, instance_ids):
    instance_id = run.get("id")
    if (not isinstance(instance_id, str) or not re.fullmatch(r"i-[0-9a-f]{12}", instance_id)
            or instance_id in instance_ids):
        raise ValueError(f"{name}: invalid or duplicate instance ID")
    instance_ids.add(instance_id)
    runtime, settings = run.get("runtime"), run.get("settings")
    origin = run.get("arw")
    if (origin != manifest["arw"] or origin["treeDirty"] is not False
            or not isinstance(runtime, dict) or runtime.get("arwVersion") != manifest["arwVersion"]
            or not isinstance(settings, dict) or settings.get("modelProvider") != manifest["harness"]["provider"]):
        raise ValueError(f"{name}: instance provenance differs from the manifest")
    report = next(iter(REPORTS & files.keys()), None)
    repair = "repair.json" if "repair.json" in files else None
    if "report" not in run or "repair" not in run or run["report"] != report or run["repair"] != repair:
        raise ValueError(f"{name}: report or repair path does not match the bundled file")


def verify_driver(name, files, driver, manifest):
    if driver.get("harnessVersion") != manifest["harness"]["version"]:
        raise ValueError(f"{name}: driver provenance differs from the manifest")
    inspection = driver.get("inspection")
    if inspection not in ("portable-scan", "agy-record") or driver.get("outcome") not in ("valid", "timeout"):
        raise ValueError(f"{name}: driver must record a completed instance with portable-scan or agy-record inspection")
    if inspection == "agy-record":
        if manifest["arw"] != AGY_ARW_ORIGIN:
            raise ValueError(f"{name}: agy-record inspection requires the pinned agy ARW origin")
        if "agy.jsonl" not in files:
            raise ValueError(f"{name}: agy-record inspection requires agy.jsonl in the manifest")
        if not isinstance(driver.get("inspect"), dict):
            raise ValueError(f"{name}: agy-record inspection requires an inspect object")
    elif "agy.jsonl" in files:
        raise ValueError(f"{name}: agy.jsonl requires agy-record inspection")


def verify_bundle(bundle):
    with bundle.open("rb") as source, gzip.GzipFile(fileobj=source) as stream, \
            tarfile.open(fileobj=stream, mode="r:", tarinfo=BundleMember) as archive:
        members = read_members(archive, stream)
        if "manifest.json" not in members:
            raise ValueError("Missing manifest.json")
        with archive.extractfile(members["manifest.json"]) as content:
            manifest = read_object(content.read(), "manifest.json")
        cells = manifest_files(manifest)
        expected = {f"runs/{name}/{file}" for name, files in cells.items() for file in files}
        unlisted = {"manifest.json"}
        if manifest["arw"] == LEGACY_ARW_ORIGIN:
            unlisted |= members.keys() & {"attempts.jsonl"}
        if members.keys() != expected | unlisted:
            raise ValueError("Archive members differ from the manifest")

        instance_ids = set()
        for path, member in members.items():
            if path in unlisted:
                continue
            _, name, filename = path.split("/")
            record = cells[name][filename]
            if member.size != record["bytes"]:
                raise ValueError(f"{path}: byte count differs from the manifest")
            with archive.extractfile(member) as content:
                if filename in ("run.json", "driver.json"):
                    data = content.read()
                    digest = hashlib.sha256(data)
                else:
                    digest = hashlib.file_digest(content, "sha256")
            if digest.hexdigest() != record["sha256"]:
                raise ValueError(f"{path}: SHA-256 differs from the manifest")
            if filename == "run.json":
                verify_run(name, cells[name], read_object(data, path), manifest, instance_ids)
            elif filename == "driver.json":
                verify_driver(name, cells[name], read_object(data, path), manifest)
    return manifest


def snapshot_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save_snapshot(root, stage, bundle, source_name, manifest):
    digest = snapshot_digest(bundle)
    path = f"snapshots/arw/{digest}.tar.gz"
    target = root / path
    sources_path = root / "sources.json"
    sources = json.loads(sources_path.read_text(encoding="utf-8"))
    for entry in sources["snapshots"]:
        if entry["file"] == path:
            if entry["sha256"] != digest or snapshot_digest(target) != digest:
                raise ValueError(f"Registered snapshot does not match its SHA-256: {path}")
            return path

    sources["snapshots"].append({
        "file": path,
        "project": "ARW",
        "commit": manifest["arw"]["commit"],
        "path": source_name,
        "sha256": digest,
        "suite": "tests/fixtures/reviewer-capability",
        "fixtureTree": manifest["arw"]["fixtureTree"],
        "scoring": "lib/reviewer-capability/scoring.mjs",
        "arwVersion": manifest["arwVersion"],
        "harness": manifest["harness"],
    })
    next_sources = stage / "sources.json"
    next_sources.write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if snapshot_digest(target) != digest:
            raise ValueError(f"Existing snapshot does not match its SHA-256: {path}")
        next_sources.replace(sources_path)
    else:
        bundle.rename(target)
        try:
            next_sources.replace(sources_path)
        except OSError:
            target.unlink()
            raise
    return path


def import_bundle(bundle, root=ROOT, dry_run=False):
    if bundle.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError("Bundle exceeds the size limits")
    if dry_run:
        return {"cells": len(verify_bundle(bundle)["cells"])}

    stage = root / ".tmp" / "import-bundle"
    stage.parent.mkdir(exist_ok=True)
    # Exclusive staging serializes updates to the snapshot registry.
    stage.mkdir()
    try:
        prepared = stage / "bundle.tar.gz"
        shutil.copyfile(bundle, prepared)
        manifest = verify_bundle(prepared)
        path = save_snapshot(root, stage, prepared, bundle.name, manifest)
        return {"cells": len(manifest["cells"]), "snapshot": path}
    finally:
        shutil.rmtree(stage)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="gzip-compressed tar from arw reviewer-capability pack (or the retired remote_run pack)")
    parser.add_argument("--dry-run", action="store_true", help="Verify without saving a snapshot")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(import_bundle(args.bundle, dry_run=args.dry_run)))
    except (OSError, ValueError, EOFError, RecursionError, tarfile.TarError, zlib.error) as error:
        parser.exit(1, f"Import failed: {error}\n")


if __name__ == "__main__":
    main()
