English · **[简体中文](CHANGELOG.zh-CN.md)**

# Changelog

## Unreleased

- Add the v2 page: `stats.extract_v2` reads an ARW export plus the supplement file from `tools/v2_supplement.py`; `build.py --v2` renders it (page 3.0.0, scoring r8.5, two task speeds, batch-pool, handoff and per-arm notes, version switch to `v1/`). Add `pricing-v2.json` and the `snapshots/v2/` snapshots with `sources.json` entries. The v1 page gains an archive banner. Statistics rule changes: v2 cells hold exactly 5 scored runs, model failures count as 0, DeepSeek and GLM (OpenCode Go plan, no E) have no cost and are not drawn on the cost charts, the other plan vendors use the plan conversion with `taskPoints` refreshed on 2026-11-26.
- Replace the local benchmark runner and packer with ARW's `reviewer-capability` commands. Import ARW bundles with `python3 tools/import_bundle.py` to verify and save immutable result snapshots with provenance in `sources.json`. The importer also accepts bundles from the retired `tools/remote_run` packer (ARW `6ca23a9`, same fixture tree).
