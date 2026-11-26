**[English](CHANGELOG.md)** · 简体中文

# 更新记录

## Unreleased

- v2 费用口径：每次订阅运行按它自己所用的套餐计价，费用 = API 等价美元 ÷ 该套餐周额度 × 该套餐周费用（Claude Max 20x、Codex $200、Gemini $200、OpenCode Go $10；OpenCode Go 的周额度取各模型月额度 ÷ 30 × 7，DeepSeek $23.33、GLM $46.67，不用实测的周窗口）。`pricing-v2.json` 去掉等效任务点与效率比 E（schema 7，新增 `planCost` 一节）；DeepSeek V4.1 Flash 与 GLM 5.3 现在有费用，出现在费用图上。v1 不变。
- 发布：Cloudflare 命令 `build.py benchmark-results.json _site/reviewer-model-benchmark/index.html` 现在在该路径写 v2 页面，并把 v1 存档写到 `v1/index.html`（经 `../` 共用 `resources/`）；`tools/check_release.py` 比对两个页面。
- 新增 v2 页面：`stats.extract_v2` 读取 ARW 导出和 `tools/v2_supplement.py` 生成的补充文件，`build.py --v2` 渲染（页面 3.0.0，评分 r8.5，两项任务速度，分池、交接与分组说明，版本切换链到 `v1/`）。新增 `pricing-v2.json` 与 `snapshots/v2/` 快照及 `sources.json` 条目。v1 页新增存档提示。统计规则变更：v2 每格恰为 5 次计分运行，模型失败计 0 分，DeepSeek 与 GLM（OpenCode Go 套餐，无 E）没有费用、不画进费用图，其他套餐厂商用 2026-11-26 刷新 `taskPoints` 后的套餐换算。
- 用 ARW 的 `reviewer-capability` 命令替换本地的 benchmark 运行器与打包工具。使用 `python3 tools/import_bundle.py` 导入 ARW 结果包，验证并保存带来源记录的不可变结果快照，来源记在 `sources.json` 中。导入工具也接受已撤掉的 `tools/remote_run` 打包工具生成的结果包（ARW `6ca23a9`，fixture tree 相同）。
