import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import support  # noqa: F401  (sets sys.path)
import leakcheck

COMMIT = "0123456789abcdef0123456789abcdef01234567"
# Built at run time so that this public file does not itself contain a leak-shaped string.
ITEM_ID = "w3-" + "0123456789ab"
CANARY = "RBCANARY" + "-deadbeef00"
PASSAGE = "the quick brown fox jumps over the lazy dog near the river bank"
MANIFEST = leakcheck.merge_manifest(leakcheck.empty_manifest(), leakcheck.build_manifest(
    commits=[COMMIT], tokens=["SecretIdentifier"], texts=[PASSAGE]))


class ScanTests(unittest.TestCase):
    def test_item_id_and_canary_always_count(self):
        text = f"see {ITEM_ID} here\nand {CANARY}"
        self.assertEqual(leakcheck.scan_text(text, leakcheck.empty_manifest()),
                         [("canary", 2), ("item-id", 1)])

    def test_plain_text_is_clean_without_manifest(self):
        self.assertEqual(leakcheck.scan_text("w3-<12 hex> is a format\nnothing", leakcheck.empty_manifest()), [])

    def test_commit_prefix_of_any_length_hits_other_hex_does_not(self):
        self.assertEqual(leakcheck.scan_text(f"fixed in {COMMIT[:7]}", MANIFEST), [("commit", 1)])
        self.assertEqual(leakcheck.scan_text(f"fixed in {COMMIT}", MANIFEST), [("commit", 1)])
        self.assertEqual(leakcheck.scan_text("fixed in 89abcdef01", MANIFEST), [])

    def test_token_is_case_insensitive_and_whole(self):
        self.assertEqual(leakcheck.scan_text("call secretIDENTIFIER()", MANIFEST), [("token", 1)])
        self.assertEqual(leakcheck.scan_text("call secretIdentifierX()", MANIFEST), [])

    def test_passage_overlap_across_lines_reports_each_start_line(self):
        text = "intro\nthe quick brown fox\njumps over the lazy dog, near the river"
        self.assertEqual(leakcheck.scan_text(text, MANIFEST), [("passage", 2), ("passage", 3)])
        self.assertEqual(leakcheck.scan_text("the quick brown fox jumps over the", MANIFEST), [])

    def test_findings_never_carry_the_matched_text(self):
        hits = leakcheck.scan_text("SecretIdentifier", MANIFEST)
        self.assertTrue(all(isinstance(k, str) and isinstance(n, int) for k, n in hits))

    def test_binary_and_oversize_are_skipped(self):
        self.assertEqual(leakcheck.scan_bytes(ITEM_ID.encode() + b"\0", MANIFEST), [])
        self.assertEqual(leakcheck.scan_bytes(ITEM_ID.encode() + b" " + b"x" * leakcheck.MAX_BYTES, MANIFEST), [])


class ManifestTests(unittest.TestCase):
    def test_load_merges_files_and_notes_unreadable_sealed_part(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "a.json").write_text(json.dumps(leakcheck.build_manifest(tokens=["alphabravo"])))
            Path(tmp, "b.json").write_text(json.dumps(leakcheck.build_manifest(tokens=["charliedelta"])))
            Path(tmp, "test.json.gpg").write_bytes(b"x")

            def no_key(_data):
                raise RuntimeError("no key")
            manifest, notes = leakcheck.load_manifest(tmp, no_key)
        self.assertEqual(len(manifest["tokens"]), 2)
        self.assertEqual(notes, ["test.json.gpg not checked (RuntimeError)"])

    def test_missing_directory_is_pattern_only(self):
        manifest, notes = leakcheck.load_manifest("/nonexistent-bank/manifest")
        self.assertEqual((manifest, notes), (leakcheck.empty_manifest(), []))

    def test_cli_reports_kind_and_line_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "manifest").mkdir()
            Path(tmp, "manifest", "m.json").write_text(json.dumps(leakcheck.build_manifest(tokens=["SecretIdentifier"])))
            Path(tmp, "f.txt").write_text("ok\nSecretIdentifier\n")
            out, err = StringIO(), StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = leakcheck.main([str(Path(tmp, "f.txt")), "--bank", tmp])
        self.assertEqual(code, 1)
        self.assertTrue(out.getvalue().strip().endswith("f.txt:2: token"))
        self.assertNotIn("SecretIdentifier", out.getvalue() + err.getvalue())


if __name__ == "__main__":
    unittest.main()
