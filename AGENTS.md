# Agent 工作规则

本文件给在本仓库工作的 agent（Claude Code、Codex 等）。工程说明见 `README.zh-CN.md`。

- **临时文件**：一律放在仓库内的 `.tmp/`（已被 Git 忽略），不用系统 `/tmp` 或会话 scratchpad；确认不再需要后删除。
- **输入数据只读**：benchmark 结果来自外部工程，复制进本仓库的快照后不修改；来源（工程、提交、路径、sha256、套件与计分版本）记在跟踪的 `sources.json`，`test_build.py` 核对快照的 sha256。构建只读仓库内的快照。
- **统计口径先定后做**：改变统计规则（分数、耗时、token、费用的算法，缺值处理，图表含义）前，先与用户讨论并达成一致；实现后同步更新两份 README 的对应章节。
- **生成物不提交**：`charts.html`、`_site/` 由 `build.py` 生成，不加入 Git。
- **文档语言**：`README.md` 为英文，`README.zh-CN.md` 为简体中文，两份内容保持一致；代码注释沿用现有英文。
- **验证**：改动 `build.py` 或 `stats.py` 后运行 `test_build.py` 并重新生成页面，在浏览器中确认图表正常显示。
- **悬停提示只放数据**：页面上所有悬停提示（散点图提示、柱状图提示）是看数据的地方，只放标题、数值、单位和必要的短标签（如“费用 $0.074”），不放解释性句子，也不重复图表下方说明区已有的内容。费用口径、等效任务点、估算来源、≥ 的含义等说明文字放在对应图表下方的说明区（`*_read`）或页面底部的数据说明（`method_*`），两处都说过的只留一处，提示里最多指向它。每个量只放一个可比较的值（费用就是换算成套餐订阅费后的价格，无套餐的用实际花费），中间量（等效任务点、API 等价费用、E、套餐周占比等）和口径说明都放说明区；提示项数以改费用口径之前的版本为准，不增加。新增或修改提示时，用 `~/.claude/bin/uishot.mjs` 在 390 和 1280 宽度、中英文下逐个核对提示内容、无横向溢出、位于视口内；`test_build.py` 中的提示测试守着这条规则。
- **题库 `.bank/`（v3，用户 #1164）**：隐藏的嵌套 git 仓库，被外层 `.gitignore` 忽略，没有远程，自己的 pre-push 一律拒绝；题目、答案键、逐题信号、逐次运行结果只放这里。只有测试集（`.bank/test/`）加密：`python3 -I bench/v3/bank.py seal|open`，密钥是 `~/.config/reviewer-bench/test-key`（`REVBENCH_KEY_FILE` 可改），不在任何仓库里，丢了测试集就没了。`bank.py check` 核对这套防护。题目内容不进 README、CHANGELOG、快照、提交信息、任务文件与报告（只写计数和口径）；任何模型的输入也不含题库内容。
- **钩子**：`.git/hooks` 不被跟踪，新克隆后先运行 `python3 -I bench/v3/install_hooks.py`。外层 pre-commit 拒绝 `.bank` 路径（含 gitlink）并对暂存内容跑 `leakcheck`，pre-push 对整段推送范围（含提交信息）再跑一次；不要用 `--no-verify` 绕过。`leakcheck` 的检测逻辑公开在 `bench/v3/leakcheck.py`，检测清单是 `.bank/manifest/` 里的哈希，不进外层仓库。
- **`bench/v3/` 测试**：`TMPDIR=<tmpfs 目录> python3 -I -m unittest discover -s bench/v3/tests`（只用合成假题；全套 ≤5 s、每例 ≤100 ms）；`test_build.py` 另有一条检查构建出的页面里没有 `.bank` 路径和题库内容。
