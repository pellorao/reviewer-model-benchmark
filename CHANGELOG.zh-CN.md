**[English](CHANGELOG.md)** · 简体中文

# 更新记录

## Unreleased

- 用 ARW 的 `reviewer-capability` 命令替换本地的 benchmark 运行器与打包工具。使用 `python3 tools/import_bundle.py` 导入 ARW 结果包，验证并保存带来源记录的不可变结果快照，来源记在 `sources.json` 中。
