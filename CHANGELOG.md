English · **[简体中文](CHANGELOG.zh-CN.md)**

# Changelog

## Unreleased

- Replace the local benchmark runner and packer with ARW's `reviewer-capability` commands. Import ARW bundles with `python3 tools/import_bundle.py` to verify and save immutable result snapshots with provenance in `sources.json`. The importer also accepts bundles from the retired `tools/remote_run` packer (ARW `6ca23a9`, same fixture tree).
