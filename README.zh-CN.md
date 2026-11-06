# Reviewer Model Benchmark 页面生成工具

**[English](README.md)** · 简体中文

[打开已发布的 Benchmark 页面](https://reviewer-model-benchmark.pages.dev/reviewer-model-benchmark/)

为代码或需求文档审查挑选 AI 模型、代理程序（harness）和推理强度时，往往需要同时权衡审查质量、耗时、token 用量、费用和速度。由于 benchmark 自身的报告只给出单项任务的结果，本工具读取同目录的 `benchmark-results.json`（benchmark 的逐实例结果快照），生成可离线打开的交互式页面 `charts.html`，将所有配置放在同一视图中对比。

为了让读者从整体结论逐步深入到具体任务，页面先展示汇总四项任务的综合分数，再用三张权衡散点图（可显示帕累托前沿）对比分数与耗时、token 用量及费用的关系，最后列出分任务的分数、耗时、token、费用和速度明细。这个页面是独立的比较视图：它把分任务结果汇总为综合分数，不修改输入数据，也不替代 benchmark 自身的正式报告。

## 版本 v2.1

在查看图表或构建页面前，需要先了解当前数据集的版本背景及其与早期版本的区别。

v2.1 在 v2.0 数据的基础上，加入了 benchmark 第三阶段补测的 GPT-6 Luna `xhigh` 和 `max` 推理强度（通过 Codex 运行），其余实例与 v2.0 完全相同。由于补测晚一天进行，服务端模型或路由可能已有变化；因此每格计入全部有效运行（每项任务 5 至 8 次），benchmark 本身也不将这两个配置与其他配置直接比较。

### v2.0

作为 v2.1 的基础，v2.0 是一轮重新设计的测量，结果不能与 v1 直接比较：

- 采用新的模型集，并通过两种代理程序运行：Codex 0.163.0 和 Claude Code 2.1.303。
- 评分规则升级为 r8.4：分数不在 0 处截断，可以为负；模型失误（没有产出报告）记 0；诊断评分照常计入，不再乘以 0.9。
- 每个配置每项任务计入 5 次运行（本地 Strata 为 10 次），分数图新增 95% 置信区间。
- 新增任务速度与引擎速度（tok/s）。
- 费用按厂商分别取计价依据，本地模型改为按本地运行成本估算（见下文）。

受这些改动影响，`build.py` 只支持 v2.x 的数据（结果文件 schema 1）；v1 的页面和脚本保留在 Git 历史中。

## 测量范围

这组开发审查任务来自软件项目 ARW。在 ARW 的开发流程中，每个 Reviewer 是一个负责特定代码或文档审查任务的 AI Agent。页面汇总以下 4 项 Reviewer 任务，并按它们在流程中的比重赋予综合分数权重：

| Reviewer | 工作 | 综合分数权重 |
| --- | --- | ---: |
| Code Standards | 对照仓库指令与实现质量标准审查代码变更。 | 20% |
| Code Spec | 检查代码变更是否准确、完整地落实给出的要求。 | 20% |
| Commit Audit | 审计暂存的提交候选：选中的文件、必要检查和要求的覆盖情况。 | 25% |
| Spec Readiness | 实施前检查需求文档是否完整、一致、可实现且可验证；每次运行有两个独立审查线程。 | 35% |

围绕这 4 项任务，benchmark 共测试了 29 个配置（27 个主配置和 2 个第三阶段补充配置）：

| 代理程序 | 模型 | 推理强度 | 费用依据 |
| --- | --- | --- | --- |
| Codex | GPT-6.1 Sol | low、medium、high | 套餐运行，参考 API 价 |
| Codex | GPT-6 Luna | low、medium、high、xhigh、max（xhigh、max 为补测） | 套餐运行，参考 API 价 |
| Codex | DeepSeek V4.1 Flash | low、high、max | DeepSeek 逐请求价格 |
| Codex | Strata IQ3_XXS（本地） | low、medium、high | 本地运行成本 |
| Claude Code | Claude Opus 5.5、Sonnet 5.5、Haiku 5.5 | low、medium、high | 套餐运行，参考 API 价 |
| Claude Code | DeepSeek V4.1 Flash | low、high、max | DeepSeek 逐请求价格 |
| Claude Code | Strata IQ3_XXS（本地） | low、medium、high | 本地运行成本 |

表中 DeepSeek V4.1 Flash 是 DeepSeek 端点的 `deepseek-flash` 模型（版本 DeepSeek-V4.1-Flash-1017）；Strata IQ3_XXS 是 Qwen3.8-Flash-Next 的 3 比特量化版本，在一台家用电脑（RTX 3080 Ti 12 GB、i9-13900、64 GB 内存）上本地运行。各配置的推理强度标签仅代表向模型请求的参数设置，不同模型间的同一标签并不代表相同的计算量。

全部测量于 2026-10-19 至 2026-10-22（UTC）进行，本页共计入 717 次计分运行。解读图表排名时需注意以下三点限制：

- 任务以 Claude Opus 标定，产出报告也由 Opus 裁决，因此 Opus 的排名位置可能偏高。
- 结果只反映这组固定任务上的表现，不是通用模型排名。
- 完整场景、原始报告与隐藏用例不在本仓库内，因此可以用仓库中的快照重算图表，但不能仅靠快照重跑测量。

## 统计规则

为了将上述原始运行记录转化为图表中的数值，构建脚本会先筛选有效实例，再按以下规则汇总分数、资源消耗与速度。

### 计入哪些运行

首先，页面筛选快照中的运行记录，只采用 benchmark 主统计计入的实例（`selection.inMain` 为真且没有 `supplementaryNote`）以及第三阶段补测实例：

- 常规配置每项任务计入 5 次运行，本地模型 Strata 每项任务计入 10 次。
- GPT-6 Luna xhigh 和 max 属于第三阶段补充配置（`kind` 为 `phase3`），按 benchmark 的口径计入每格的全部有效实例，每项任务 5 至 8 次。
- DeepSeek 请求设为 medium、但端点在相同时限下实际按 high 执行的运行，按 benchmark 口径并入 high 格；因此 Commit Audit 中的两个 DeepSeek high 格各有 8 次运行。
- 无效运行，以及因时限不同而单列的“请求 medium”补充配置，均不进入页面。

### 分数

筛选出有效运行后，脚本先计算单次运行得分，再逐层汇总为单项任务分数和跨任务的综合分数。

单次运行的分数（r8.4）按报告找出的答案键问题加分、按误报扣分，且不在 0 处截断。单项任务分数是该格各次运行的算术平均值，并按 t 分布计算 95% 置信区间（半宽 = t₀.₉₇₅,ₙ₋₁ × SD / √n）。在此基础上，按四项任务的权重加权得出综合分数：

```text
综合分数 = 100 × (
    0.20 × Code Standards
  + 0.20 × Code Spec
  + 0.25 × Commit Audit
  + 0.35 × Spec Readiness
)
```

综合分数的 95% 置信区间半宽为 t × √Σ(wᵢ² · SEᵢ²)，自由度按 Welch–Satterthwaite 公式计算。

### 耗时、token、费用

分数衡量审查质量，而耗时、token 和费用衡量资源消耗。由于得 0 分的运行和模型失误的运行同样消耗了资源，这三项指标对全部计入的运行求平均。

具体计算时，单项任务的值取该格有数据的运行的平均值；配置的值取四项任务均值的算术平均。耗时只计工作秒数（不含环境准备与模型加载）：Codex 统计代理的累计工作时间，Claude Code 统计会话的墙钟时间；Spec Readiness 包含两个独立审查线程，耗时取两个线程之和。

### 速度

有了 token 用量和耗时，页面进一步计算处理速度。为了真实反映整体吞吐率，速度一律用总 token 除以总耗时，绝不对各次运行的速度求简单平均：

- 任务的速度 = 该格各次运行的 token 之和 ÷ 秒数之和。

每次运行计入分母的秒数取其自身速度对应的时间口径，从而保留 benchmark 的两套时间基准：任务速度用工作秒数（代表用户实际感受到的速度），引擎速度用请求或解码秒数（代表模型本身的速度）。在 token 口径上，输入速度用未缓存输入 token，输出速度用输出 token。由于远程 API 模型无法把输入处理时间从解码时间中拆出来，其引擎输入速度未知，引擎输出速度也只是下限（≥）；只有本地运行的 Strata 具有引擎输入速度。

### 缺值

最后，部分运行缺少某项具体指标的数据。缺失值一律不当作 0 处理：某次运行缺少某项数据时，只在该项指标中跳过，其余指标照常计入，并在图下方的说明中列出受影响的格。由于 API 模型的引擎输入速度按设计就是未知的，速度图下方的说明不再单独列出。标有 ≥ 的数值表示下限，例如 DeepSeek 因时限提醒丢弃了部分请求而未能完整计入的费用。

## 费用

在各项指标中，费用需要单独制定换算规则，因为不同配置分别通过订阅套餐、按请求计费 API 和本地硬件运行。因此，页面上的所有费用都不是实际账单；具体单价于 **2026-10-22** 核对，换算规则保存在 `pricing.json` 中：

| 厂商 | 依据 |
| --- | --- |
| OpenAI | 套餐运行，参考 API 价：token × OpenAI Standard API 单价 |
| Anthropic | 套餐运行，参考 API 价：Claude Code 报告的 API 等价费用（实例 `cost.usd`） |
| DeepSeek | 实例 `cost.usd`：按官方价逐请求计算，区分高峰 / 低谷 |
| Strata（本地） | 本地运行成本：工作秒数 × 每小时成本 |

其中，OpenAI 模型按 token 用量乘以 OpenAI Standard API 单价（美元 / 百万 token）：

| 模型 | 未缓存输入 | 缓存输入 | 输出 |
| --- | ---: | ---: | ---: |
| [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) | $2 | $0.10 | $10 |
| [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) | $0.10 | $0.01 | $0.50 |

缓存写入 token 不计价：`pricing.json` 中的 `cacheWriteRate` 仅作参考，若 OpenAI 实例带有缓存写入 token，构建会直接报错停止。

本地 Strata 模型的运行成本只粗略估算工作期间的电费和硬件维护，不含硬件购置、安装及实例之间的空闲时间：

| 项目 | 取值 | 说明 |
| --- | ---: | --- |
| 整机功率 | 400 W | 粗略的整机负载估计（GPU 板卡上限 350 W，受显存带宽限制的解码通常更低） |
| 电价 | $0.174 / kWh | 2026 年第一季度全球家庭平均电价（按国家平均，[GlobalPetrolPrices](https://www.globalpetrolprices.com/electricity_prices/)） |
| 维护 | $0.02 / 小时 | 风扇、电源等损耗件，约每年 $50、按每年约 2,500 负载小时摊 |
| 合计 | 约 $0.09 / 小时 | |

按工作时间折算后，本地成本恒大于 0，图表中的对数费用轴不会遇到 0。同时，由于本地运行比远程 API 慢得多，Strata 在每项任务每次运行上的成本约为 $0.011–0.026，与 GPT-6 Luna low 处于同一量级。

## 文件

了解页面的统计与计价口径后，可以查看仓库文件或自己在本地生成页面。仓库结构如下：

```text
./
├── build.py
├── stats.py
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

各文件在构建流程中分工如下：

- **代码与计价参数**：`stats.py` 保存统计与费用规则（纯 Python，不依赖 Plotly），`build.py` 绘制图表并组装页面，`test_build.py` 负责测试，`pricing.json` 保存计价参数。
- **样式、字体与生成物**：`resources/site.css` 是页面唯一的样式表，`resources/fonts/` 存放预下载的字体（字体许可与来源见 `resources/fonts/README.md`）。`resources/favicon.svg` 由脚本生成并保存在仓库中；`charts.html` 则是本地生成的文件，不提交到 Git。
- **数据快照**：`benchmark-results.json` 是输入数据的独立快照。构建页面时只读取仓库中已提交的这份快照，不读取 `.env`，也不会从其他目录自动同步数据。

当外部 benchmark 有新数据需要同步时，维护者先将 `.env.example` 复制为已被 Git 忽略的 `.env`，在 `BENCHMARK_SOURCE_RESULTS` 中填入可信来源文件的绝对路径，然后在仓库根目录用 Bash 复制并校验新快照：

```bash
. ./.env
: "${BENCHMARK_SOURCE_RESULTS:?请在 .env 设置 BENCHMARK_SOURCE_RESULTS}"
cp -- "$BENCHMARK_SOURCE_RESULTS" benchmark-results.json
cmp -- "$BENCHMARK_SOURCE_RESULTS" benchmark-results.json
```

## 使用

准备好快照后，即可在本地运行测试并生成 `charts.html`。生成页面需要 Python 和 Plotly（已用 Python 3.14 与 Plotly 6.9.0 验证）。在本目录依次执行以下命令：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install plotly==6.9.0
.venv/bin/python test_build.py
.venv/bin/python build.py
```

如果系统 Python 没有自带 `venv` 或 `pip`，可以改用 [uv](https://docs.astral.sh/uv/)：先运行 `uv venv .venv`，再运行 `uv pip install --python .venv/bin/python plotly==6.9.0`。在 Windows 中，请使用 `py -m venv .venv` 和 `.venv\Scripts\python`。

`build.py` 默认读取同目录的 `benchmark-results.json`，并覆盖同目录的 `charts.html`；如需指定其他输入或输出路径，可作为参数传入：

```bash
.venv/bin/python build.py path/to/benchmark-results.json path/to/charts.html
```

由于输出页面通过相对路径加载 `resources/`，指定其他输出目录时，该目录下也必须备有对应的 `resources/`，构建脚本不会自动创建。

生成完毕后，用浏览器直接打开 `charts.html` 即可查看，无需 Python 环境、网络连接或 Web 服务器。注意页脚显示的“更新于”是页面的构建日期，不代表测量日期或价格核对日期。

## 实现和维护

如需修改代码或更新价格，请注意本工具只负责处理数据快照：它不运行 benchmark，也不修改输入 JSON。

为了便于独立验证统计逻辑，计算与绘图拆分为两个模块：

- `stats.py` 用纯 Python 读取 JSON 并计算各项指标（包括纯 Python 实现的 t 分布分位数），价格由调用方从 `pricing.json` 传入。由于不依赖 Plotly，即使未安装 Plotly 也能运行 `test_build.py` 检查统计逻辑（缺少 Plotly 时自动跳过页面生成测试）。
- `build.py` 调用 Plotly 生成图表并嵌入 HTML。页面文字和图表坐标轴支持在英文与中文之间切换，所有图表交互均在浏览器本地运行。

维护配置项或统计规则时，需要同步更新相关文件：

- **模型、权重与视觉配置**：模型顺序与名称、代理程序以及 4 项 Reviewer 的权重定义在 `stats.py` 顶部；模型颜色和评分版本定义在 `build.py` 顶部。
- **价格与本地成本参数**：保存在 `pricing.json`。页面方法说明中的价格、功率、电价和权重由 `pricing.json` 与 `REVIEWERS` 动态生成；调整价格或参数后，请更新 `checkedAt`、重新生成页面，并同步更新两份 README 中的费用表。
- **统计规则**：改动任何统计规则前，须先按 `AGENTS.md` 所述的流程确认一致，实现后同步更新两份 README。

## 发布

代码推送到 GitHub 的 `master` 分支后，连接该仓库的 Cloudflare Pages 会使用 Python 3.12 和 Plotly 6.9.0 自动构建页面，并将产物输出到 `_site` 目录：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install plotly==6.9.0
mkdir -p _site/reviewer-model-benchmark/resources
cp -R resources/. _site/reviewer-model-benchmark/resources/
.venv/bin/python build.py benchmark-results.json _site/reviewer-model-benchmark/index.html
```

由于页面资源全部使用相对路径，部署后即可在 `/reviewer-model-benchmark/` 子路径下正常访问。本地生成的 `charts.html` 和 `_site/` 不加入 Git，自定义域名则在仓库外部配置。
