English · **[简体中文](CHANGELOG.zh-CN.md)**

# Changelog

## Unreleased

- v2 cost basis: each subscription run is priced against its own plan, cost = API-equivalent USD ÷ the plan's weekly quota × the plan's weekly fee (Claude Max 20x, Codex $200, Gemini $200, OpenCode Go $10; OpenCode Go's weekly quota is the per-model monthly allowance ÷ 30 × 7, DeepSeek $23.33 and GLM $46.67, not the measured weekly window). Equivalent task points and the efficiency ratio E are removed from `pricing-v2.json` (schema 7, new `planCost` section); DeepSeek V4.1 Flash and GLM 5.3 now have a cost and appear on the cost charts. v1 is unchanged.
- Publishing: the Cloudflare command `build.py benchmark-results.json _site/reviewer-model-benchmark/index.html` now writes the v2 page there and the v1 archive to `v1/index.html` (shared `resources/` via `../`); `tools/check_release.py` compares both pages.
- Add the v2 page: `stats.extract_v2` reads an ARW export plus the supplement file from `tools/v2_supplement.py`; `build.py --v2` renders it (page 3.0.0, scoring r8.5, two task speeds, batch-pool, handoff and per-arm notes, version switch to `v1/`). Add `pricing-v2.json` and the `snapshots/v2/` snapshots with `sources.json` entries. The v1 page gains an archive banner. Statistics rule changes: v2 cells hold exactly 5 scored runs, model failures count as 0, DeepSeek and GLM (OpenCode Go plan, no E) have no cost and are not drawn on the cost charts, the other plan vendors use the plan conversion with `taskPoints` refreshed on 2026-11-26.
- Replace the local benchmark runner and packer with ARW's `reviewer-capability` commands. Import ARW bundles with `python3 tools/import_bundle.py` to verify and save immutable result snapshots with provenance in `sources.json`. The importer also accepts bundles from the retired `tools/remote_run` packer (ARW `6ca23a9`, same fixture tree).
