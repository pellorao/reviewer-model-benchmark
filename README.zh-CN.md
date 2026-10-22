# Reviewer Model Benchmark 页面生成工具

**[English](README.md)** · 简体中文

[打开已发布的 Benchmark 页面](https://cybersoul.net/reviewer-model-benchmark/)

本工具读取同目录的 `benchmark-results.json`（benchmark 的逐实例结果快照），生成可离线打开的 `charts.html`，比较不同模型、代理程序（harness）和推理强度在 4 项 Reviewer 任务中的分数、耗时、token 用量、费用和速度。页面先给综合分数，再给三张权衡散点图（可显示帕累托前沿），最后是分任务的分数、耗时、token、费用和速度明细。

这个页面是独立的比较视图。它不修改输入数据，也不替代 benchmark 自身的正式报告；benchmark 自己的报告只给分任务结果，综合分数是本页的汇总。

## 版本 v2.0

v2.0 是一轮全新的测量，结果不能与 v1 直接比较：

- 新的模型集，并通过两种代理程序运行：Codex 0.163.0 和 Claude Code 2.1.303。
- 评分改为 r8.4：分数不在 0 处截断，可以为负；模型失误（没有产出报告）记 0；诊断评分照常计入，不再乘 0.9。
- 每个配置每项任务计入 5 次运行（本地 Strata 为 10 次），分数图加 95% 置信区间。
- 新增任务速度与引擎速度（tok/s）。
- 费用按厂商分别取依据，本地模型改为本地运行成本（见下文）。

`build.py` 只支持 v2.0 的数据；v1 页面和脚本保留在 Git 历史中。

## 测量范围

ARW 是提供这组开发审查任务的软件项目。Reviewer 是 ARW 开发流程中执行特定代码或文档审查任务的 AI Agent。

| Reviewer | 工作 | 综合分数权重 |
| --- | --- | ---: |
| Code Standards | 对照仓库指令与实现质量标准审查代码变更。 | 20% |
| Code Spec | 检查代码变更是否准确、完整地落实给出的要求。 | 20% |
| Commit Audit | 审计暂存的提交候选：选中的文件、必要检查和要求的覆盖情况。 | 25% |
| Spec Readiness | 实施前检查需求文档是否完整、一致、可实现且可验证；每次运行有两个独立审查线程。 | 35% |

共 27 个主配置：

| 代理程序 | 模型 | 推理强度 | 费用依据 |
| --- | --- | --- | --- |
| Codex | GPT-6.1 Sol、GPT-6 Luna | low、medium、high | 套餐运行，参考 API 价 |
| Codex | DeepSeek V4.1 Flash | low、high、max | DeepSeek 逐请求价格 |
| Codex | Strata IQ3_XXS（本地） | low、medium、high | 本地运行成本 |
| Claude Code | Claude Opus 5.5、Sonnet 5.5、Haiku 5.5 | low、medium、high | 套餐运行，参考 API 价 |
| Claude Code | DeepSeek V4.1 Flash | low、high、max | DeepSeek 逐请求价格 |
| Claude Code | Strata IQ3_XXS（本地） | low、medium、high | 本地运行成本 |

测量于 2026-10-19 至 2026-10-22（UTC）进行，本页共计入 666 次计分运行。推理强度标签是各模型的请求设置，不代表相同的计算量。任务以 Claude Opus 标定、报告也由 Opus 裁决，所以 Opus 的位置可能偏高。结果只描述这组固定任务，不是通用模型排名。完整场景、原始报告与隐藏用例不在本仓库，因此可以从快照重算图表，不能仅靠快照重跑测量。

DeepSeek V4.1 Flash 是 DeepSeek 端点的 `deepseek-flash` 模型，版本为 DeepSeek-V4.1-Flash-1017。

Strata IQ3_XXS 是 Qwen3.8-Flash-Next 的 3 比特量化版本，在一台家用电脑（RTX 3080 Ti 12 GB、i9-13900、64 GB 内存）上本地运行。

## 统计规则

### 计入哪些运行

只用 benchmark 主统计计入的实例（`selection.inMain` 为真且没有 `supplementaryNote`）：Strata 每项任务 10 次，其他配置 5 次。DeepSeek 请求为 medium、但端点在相同时限下按 high 执行的运行，按 benchmark 的口径并入 high 格，所以 Commit Audit 的两个 DeepSeek high 格各有 8 次。无效运行，以及时限不同而单列的“请求 medium”补充配置，都不进入页面。

### 分数

单次运行的分数（r8.4）按报告找到的答案键问题加分、按错误发现扣分，不在 0 处截断。任务分数是该格各次运行的平均值，95% 区间按 t 分布计算（半宽 = t₀.₉₇₅,ₙ₋₁ × SD / √n）。综合分数：

```text
综合分数 = 100 × (
    0.20 × Code Standards
  + 0.20 × Code Spec
  + 0.25 × Commit Audit
  + 0.35 × Spec Readiness
)
```

综合分数的 95% 区间半宽为 t × √Σ(wᵢ² · SEᵢ²)，自由度按 Welch–Satterthwaite 计算。

### 耗时、token、费用

耗时、token 和费用对全部计入的运行求平均，包括 0 分和模型失误的运行，因为它们同样消耗了资源。任务的值是有数据的运行的平均值；配置的值是四项任务的值的算术平均。耗时是工作秒数（不含准备与加载）：Codex 计代理的累计工作时间，Claude Code 计会话的墙钟时间；Spec Readiness 的两个线程耗时相加。

### 速度

速度一律是总 token 除以总耗时，不对各次运行的速度求平均：

- 任务的速度 = 该格各次运行的 token 之和 ÷ 秒数之和。
- 配置的速度 = 四项任务各一次平均运行的 token 之和 ÷ 秒数之和。

每次运行的秒数取它自己速度的分母，所以沿用 benchmark 的时间口径：任务速度用工作秒数（用户感受到的速度），引擎速度用请求或解码秒数（模型本身的速度）。输入速度用未缓存输入 token，输出速度用输出 token。API 模型分不出输入处理时间，所以引擎输入速度未知，引擎输出速度是下限（≥）；只有 Strata 有引擎输入速度。

### 缺值

缺失值不是 0：某项缺数据的运行只在该项中跳过，其余项照常计入，图下的说明列出这些格。标 ≥ 的值是下限，例如 DeepSeek 有请求因时限提醒被丢弃而未计入的费用。

## 费用

所有费用都不是实际账单，价格于 **2026-10-22** 核对，规则保存在 `pricing.json`。

| 厂商 | 依据 |
| --- | --- |
| OpenAI | 套餐运行，参考 API 价：token × OpenAI Standard API 单价 |
| Anthropic | 套餐运行，参考 API 价：Claude Code 报告的 API 等价费用（实例 `cost.usd`） |
| DeepSeek | 实例 `cost.usd`：按官方价逐请求计算，区分高峰 / 低谷 |
| Strata（本地） | 本地运行成本：工作秒数 × 每小时成本 |

OpenAI 单价（美元 / 百万 token）：

| 模型 | 未缓存输入 | 缓存输入 | 输出 |
| --- | ---: | ---: | ---: |
| [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) | $2 | $0.10 | $10 |
| [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) | $0.10 | $0.01 | $0.50 |

本地运行成本只算电费和维护，不含硬件购置、安装和实例之间的空闲时间，精度不高：

| 项目 | 取值 | 说明 |
| --- | ---: | --- |
| 整机功率 | 400 W | 粗略的整机负载估计（GPU 板卡上限 350 W，受显存带宽限制的解码通常更低） |
| 电价 | $0.174 / kWh | 2026 年第一季度全球家庭平均电价（按国家平均，[GlobalPetrolPrices](https://www.globalpetrolprices.com/electricity_prices/)） |
| 维护 | $0.02 / 小时 | 风扇、电源等损耗件，约每年 $50、按每年约 2,500 负载小时摊 |
| 合计 | 约 $0.09 / 小时 | |

本地成本天然大于 0，对数费用轴不会遇到 0。由于本地实例比 API 慢得多，Strata 每项任务每次约 $0.011–0.026，与 GPT-6 Luna low 同一量级。

## 文件

```text
./
├── build.py
├── test_build.py
├── benchmark-results.json
├── pricing.json
├── README.md
├── README.zh-CN.md
├── AGENTS.md
├── .env.example
└── resources/
    ├── site.css
    ├── favicon.svg
    └── fonts/
```

`benchmark-results.json` 是输入数据的独立快照。维护者更新它时，先将 `.env.example` 复制为已忽略的 `.env`，再把可信来源文件的绝对路径填入 `BENCHMARK_SOURCE_RESULTS`。构建页面只读取已提交的快照，不读取 `.env`，也不会从其他目录自动同步数据。`charts.html` 是生成的本地文件，不提交到 Git；`resources/favicon.svg` 也由脚本生成，但保存在仓库中。`resources/site.css` 和 `resources/fonts/` 是页面所需的预下载资源，字体许可和来源见 `resources/fonts/README.md`。

在仓库根目录用 Bash 复制并核对新快照：

```bash
. ./.env
: "${BENCHMARK_SOURCE_RESULTS:?请在 .env 设置 BENCHMARK_SOURCE_RESULTS}"
cp -- "$BENCHMARK_SOURCE_RESULTS" benchmark-results.json
cmp -- "$BENCHMARK_SOURCE_RESULTS" benchmark-results.json
```

## 使用

生成页面需要 Python 和 Plotly，已用 Python 3.14 与 Plotly 6.9.0 验证。以下命令在本目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install plotly==6.9.0
.venv/bin/python test_build.py
.venv/bin/python build.py
```

如果系统 Python 没有 `venv` 或 `pip`，可以改用 [uv](https://docs.astral.sh/uv/)：`uv venv .venv`，然后 `uv pip install --python .venv/bin/python plotly==6.9.0`。Windows 中使用 `py -m venv .venv` 和 `.venv\Scripts\python`。

默认读取同目录的 `benchmark-results.json`，并覆盖同目录的 `charts.html`；也可以传入其他路径：

```bash
.venv/bin/python build.py path/to/benchmark-results.json path/to/charts.html
```

输出页面通过相对路径加载 `resources/`，指定其他输出目录时，该目录也必须有对应的 `resources/`。用浏览器直接打开 `charts.html` 即可，查看图表不需要 Python、网络或 Web 服务器。页脚的“更新于”是页面构建日期，不代表测量或价格核对日期。

## 实现和维护

`build.py` 用 Python 读取 JSON 和计算指标，t 分布分位数用纯 Python 实现；Plotly 生成图表并嵌入 HTML。页面文字和图表坐标轴可在英文与中文之间切换，图表交互在浏览器本地运行。

模型顺序与颜色、代理程序、4 项 Reviewer 的权重和评分版本定义在 `build.py` 顶部。价格与本地成本参数保存在 `pricing.json`；调整后更新 `checkedAt`，重新生成页面，并同步更新本 README 的费用表。改动统计规则前先在 `AGENTS.md` 所述流程中确认，实现后同步更新两份 README。

本工具不运行 benchmark，也不修改输入 JSON。

## 发布

Cloudflare Pages 连接到这个 GitHub 仓库，使用 Python 3.12 和 Plotly 6.9.0 从 `master` 分支构建页面，构建输出目录为 `_site`：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install plotly==6.9.0
mkdir -p _site/reviewer-model-benchmark/resources
cp -R resources/. _site/reviewer-model-benchmark/resources/
.venv/bin/python build.py benchmark-results.json _site/reviewer-model-benchmark/index.html
```

页面资源使用相对路径，因此可以在该子路径访问。本地的 `charts.html` 和 `_site/` 不加入 Git。自定义域名在仓库外配置。
