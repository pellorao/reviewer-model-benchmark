"""Import small ARW-format archives without an ARW installation or model."""

from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

if __package__:
    from . import import_bundle as importer
else:
    import import_bundle as importer

CELL = "example-model-high-code-spec-r1"
PREFIX = f"runs/{CELL}/"


def encode(value):
    return (json.dumps(value) + "\n").encode()


def file_entry(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


class ImportTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name) / "repo"
        self.root.mkdir()
        self.sources = self.root / "sources.json"
        self.original_sources = {"version": 1, "suite": {"id": "v1"}, "snapshots": [
            {"file": "benchmark-results.json", "sha256": "unchanged"},
        ]}
        self.sources.write_bytes(encode(self.original_sources))
        self.bundle = Path(directory.name) / "model-results.tar.gz"
        self.origin = dict(importer.ARW_ORIGIN)
        self.run = {"id": "i-0123456789ab", "arw": dict(self.origin),
                    "runtime": {"arwVersion": "0.5.5"}, "settings": {"modelProvider": "test-cli"},
                    "report": "report.txt", "repair": None}
        self.driver = {"inspection": "portable-scan", "outcome": "valid", "harnessVersion": ""}

    def files(self):
        return {"agent.json": b'{}\n', "score.json": b'{"score":1}\n', "report.txt": b"Test report\n",
                "run.json": encode(self.run), "driver.json": encode(self.driver)}

    def manifest(self, cells):
        return {"schema": 1, "tool": 1, "created": datetime.fromtimestamp(0, timezone.utc).isoformat(),
                "arw": dict(self.origin), "arwVersion": "0.5.5", "harness": {"provider": "test-cli", "version": ""},
                "cells": [{"dir": name, "files": {file: file_entry(data) for file, data in files.items()}}
                          for name, files in cells.items()]}

    def members(self, cells=None, manifest=None):
        if cells is None:
            cells = {CELL: self.files()}
        if manifest is None:
            manifest = self.manifest(cells)
        return [("manifest.json", encode(manifest))] + [
            (f"runs/{name}/{file}", data) for name, files in cells.items() for file, data in files.items()
        ]

    def make_bundle(self, members, mode="w:gz", archive_format=tarfile.PAX_FORMAT):
        with tarfile.open(self.bundle, mode, format=archive_format) as archive:
            for name, data in members:
                info = tarfile.TarInfo(name) if isinstance(name, str) else name
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
        return self.bundle

    def assert_rejected(self, pattern):
        with self.assertRaisesRegex(ValueError, pattern):
            importer.import_bundle(self.bundle, self.root)
        self.assertFalse((self.root / "snapshots").exists())
        self.assertEqual(self.sources.read_bytes(), encode(self.original_sources))
        self.assertFalse((self.root / ".tmp" / "import-bundle").exists())

    def test_dry_run_and_immutable_snapshot_with_provenance(self):
        # The manifest need not be the first member.
        self.make_bundle(list(reversed(self.members())))
        self.assertEqual(importer.import_bundle(self.bundle, self.root, dry_run=True), {"cells": 1})
        self.assertEqual(list(self.root.iterdir()), [self.sources])

        data = self.bundle.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        result = importer.import_bundle(self.bundle, self.root)
        self.assertEqual(result, {"cells": 1, "snapshot": f"snapshots/arw/{digest}.tar.gz"})
        self.assertEqual((self.root / result["snapshot"]).read_bytes(), data)
        sources = json.loads(self.sources.read_bytes())
        self.assertEqual(sources["suite"], self.original_sources["suite"])
        self.assertEqual(sources["snapshots"][:-1], self.original_sources["snapshots"])
        self.assertEqual(sources["snapshots"][-1], {
            "file": result["snapshot"], "project": "ARW", "commit": self.origin["commit"],
            "path": self.bundle.name, "sha256": digest, "suite": "tests/fixtures/reviewer-capability",
            "fixtureTree": self.origin["fixtureTree"], "scoring": "lib/reviewer-capability/scoring.mjs",
            "arwVersion": "0.5.5", "harness": {"provider": "test-cli", "version": ""},
        })
        saved_sources = self.sources.read_bytes()
        self.assertEqual(importer.import_bundle(self.bundle, self.root), result)
        self.assertEqual(self.sources.read_bytes(), saved_sources)

    def test_accepts_the_retired_remote_run_origin_and_records_its_commit(self):
        legacy = importer.LEGACY_ARW_ORIGIN
        self.assertNotEqual(legacy["commit"], self.origin["commit"])
        self.assertEqual(legacy["fixtureTree"], self.origin["fixtureTree"])
        self.origin, self.run["arw"] = dict(legacy), dict(legacy)
        self.make_bundle(self.members())
        result = importer.import_bundle(self.bundle, self.root)
        entry = json.loads(self.sources.read_bytes())["snapshots"][-1]
        self.assertEqual((entry["file"], entry["commit"], entry["fixtureTree"]),
                         (result["snapshot"], legacy["commit"], legacy["fixtureTree"]))

    def test_attempt_log_is_accepted_only_with_the_retired_remote_run_origin(self):
        members = self.members() + [("attempts.jsonl", b'{"cell": "x"}\n')]
        self.make_bundle(members)
        self.assert_rejected("members differ")
        self.origin, self.run["arw"] = dict(importer.LEGACY_ARW_ORIGIN), dict(importer.LEGACY_ARW_ORIGIN)
        self.make_bundle(self.members() + [("attempts.jsonl", b'{"cell": "x"}\n')])
        self.assertEqual(importer.import_bundle(self.bundle, self.root, dry_run=True), {"cells": 1})

    def test_refuses_instance_origin_that_differs_from_the_manifest_origin(self):
        self.run["arw"] = dict(importer.LEGACY_ARW_ORIGIN)
        self.make_bundle(self.members())
        self.assert_rejected("provenance")

    def test_reports_and_repair_are_relative_and_optional(self):
        self.run.update(report="report.jsonl", repair="repair.json")
        files = self.files()
        files["report.jsonl"] = files.pop("report.txt")
        files.update({"candidates.json": b"[]", "repair.json": b"{}"})
        second = CELL.removesuffix("1") + "2"
        self.run.update(id="i-abcdef012345", report=None, repair=None)
        self.driver["outcome"] = "timeout"
        no_report = self.files()
        del no_report["report.txt"]
        self.make_bundle(self.members({CELL: files, second: no_report}))
        self.assertEqual(importer.import_bundle(self.bundle, self.root, dry_run=True), {"cells": 2})

    def test_refuses_invalid_manifest_and_instance_file_sets(self):
        cells = {CELL: self.files()}
        for key, value in (("schema", True), ("tool", 2), ("created", "now"),
                           ("created", datetime.fromtimestamp(0, timezone(timedelta(hours=1))).isoformat()),
                           ("cells", []),
                           ("arw", {**self.origin, "fixtureTree": "0" * 40}),
                           ("arw", {**self.origin, "commit": "0" * 40}),
                           ("arw", {**self.origin, "treeDirty": True}),
                           ("arw", {**self.origin, "treeDirty": 0}),
                           ("arw", {**importer.LEGACY_ARW_ORIGIN, "fixtureTree": "0" * 40}),
                           ("arw", {**importer.LEGACY_ARW_ORIGIN, "treeDirty": True}), ("harness", {"provider": "test-cli"})):
            with self.subTest(key=key, value=value):
                manifest = self.manifest(cells)
                manifest[key] = value
                self.make_bundle(self.members(cells, manifest))
                self.assert_rejected("schema|timestamp|pinned clean ARW|instance|identity|Invalid isoformat")
        for files in ({**self.files(), "report.md": b"x"}, {"run.json": encode(self.run)}):
            self.make_bundle(self.members({CELL: files}))
            self.assert_rejected("invalid instance file set")
        manifest = self.manifest(cells)
        manifest["cells"] *= 2
        self.make_bundle(self.members(cells, manifest))
        self.assert_rejected("duplicate instance directory")
        self.make_bundle(self.members({"model-high-unknown-r1": self.files()}))
        self.assert_rejected("Invalid or duplicate instance directory")

    def test_refuses_extra_missing_duplicate_unsafe_and_nonregular_members(self):
        members = self.members()
        for name in ("../escape", "/absolute", PREFIX + "other.txt", "attempts.jsonl"):
            with self.subTest(name=name):
                self.make_bundle(members + [(name, b"")])
                self.assert_rejected("members differ")
        self.make_bundle(members[:-1])
        self.assert_rejected("members differ")
        for entry in (members[0], members[1]):
            self.make_bundle(members + [entry])
            self.assert_rejected("Duplicate archive path")
        for kind in (tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE, tarfile.FIFOTYPE):
            member = tarfile.TarInfo(PREFIX + "report.txt")
            member.type = kind
            self.make_bundle(members + [(member, b"")])
            self.assert_rejected("must be a regular file")

    def test_refuses_wrong_byte_count_and_same_length_tampering(self):
        files = self.files()
        for replacement, error in ((b"short", "byte count"), (b"x" * len(files["report.txt"]), "SHA-256")):
            with self.subTest(error=error):
                members = [(name, replacement if name == PREFIX + "report.txt" else data)
                           for name, data in self.members({CELL: files})]
                self.make_bundle(members)
                self.assert_rejected(error)

    def test_refuses_inconsistent_records_even_with_correct_member_hashes(self):
        for record, key, value, error in [
            (self.run, "arw", {**self.origin, "treeDirty": True}, "provenance"),
            (self.run, "runtime", {"arwVersion": "other"}, "provenance"),
            (self.run, "settings", {"modelProvider": "other"}, "provenance"),
            (self.driver, "harnessVersion", "other", "provenance"),
            (self.driver, "inspection", "other", "portable-scan"),
            (self.driver, "outcome", "failed", "completed"),
            (self.run, "id", "wrong", "instance ID"),
            (self.run, "repair", "../../file", "repair path"),
            (self.run, "report", "/report.txt", "report or repair"),
        ]:
            with self.subTest(key=key), patch.dict(record, {key: value}):
                self.make_bundle(self.members())
                self.assert_rejected(error)
        self.make_bundle(self.members({CELL: self.files(), CELL.removesuffix("1") + "2": self.files()}))
        self.assert_rejected("duplicate instance ID")

    def test_refuses_non_gzip_and_data_after_tar_terminator(self):
        self.make_bundle(self.members(), mode="w")
        with self.assertRaises(gzip.BadGzipFile):
            importer.import_bundle(self.bundle, self.root, dry_run=True)
        self.make_bundle(self.members())
        with self.bundle.open("ab") as stream:
            stream.write(gzip.compress(b"hidden data"))
        self.assert_rejected("Unexpected data after")

    def test_reads_gnu_and_pax_long_paths(self):
        cell = "model" + "x" * 112 + "-high-spec-readiness-r1"
        members = self.members({cell: self.files()})
        for archive_format in (tarfile.GNU_FORMAT, tarfile.PAX_FORMAT):
            with self.subTest(archive_format=archive_format):
                self.make_bundle(members, archive_format=archive_format)
                self.assertEqual(importer.import_bundle(self.bundle, self.root, dry_run=True), {"cells": 1})

    def test_refuses_oversized_extended_tar_header(self):
        member = tarfile.TarInfo(PREFIX + "report.txt")
        member.pax_headers = {"comment": "x" * importer.MAX_TAR_METADATA_BYTES}
        self.make_bundle(self.members()[:-1] + [(member, b"")])
        self.assert_rejected("metadata exceeds")

    def test_registry_write_failure_removes_new_archive(self):
        self.make_bundle(self.members())
        with patch.object(Path, "replace", side_effect=OSError("write failed")):
            with self.assertRaisesRegex(OSError, "write failed"):
                importer.import_bundle(self.bundle, self.root)
        self.assertEqual(self.sources.read_bytes(), encode(self.original_sources))
        self.assertEqual(list(self.root.glob("snapshots/arw/*")), [])


if __name__ == "__main__":
    unittest.main()
