**[English](CHANGELOG.md)** · 简体中文

# 更新记录

## Unreleased

- 新增 v2 页面：`stats.extract_v2` 读取 ARW 导出和 `tools/v2_supplement.py` 生成的补充文件，`build.py --v2` 渲染（页面 3.0.0，评分 r8.5，两项任务速度，分池、交接与分组说明，版本切换链到 `v1/`）。新增 `pricing-v2.json` 与 `snapshots/v2/` 快照及 `sources.json` 条目。v1 页新增存档提示。统计规则变更：v2 每格恰为 5 次计分运行，模型失败计 0 分，DeepSeek 与 GLM（OpenCode Go 套餐，无 E）没有费用、不画进费用图，其他套餐厂商用 2026-11-26 刷新 `taskPoints` 后的套餐换算。
- 用 ARW 的 `reviewer-capability` 命令替换本地的 benchmark 运行器与打包工具。使用 `python3 tools/import_bundle.py` 导入 ARW 结果包，验证并保存带来源记录的不可变结果快照，来源记在 `sources.json` 中。导入工具也接受已撤掉的 `tools/remote_run` 打包工具生成的结果包（ARW `6ca23a9`，fixture tree 相同）。
