# Reviewer Model Benchmark 页面生成工具

**[English](README.md)** · 简体中文

[打开已发布的 Benchmark 页面](https://reviewer-model-benchmark.pages.dev/reviewer-model-benchmark/)

工具变更见[更新记录](CHANGELOG.zh-CN.md)。

为代码或需求文档审查挑选 AI 模型、代理程序（harness）和推理强度时，往往需要同时权衡审查质量、耗时、token 用量、费用和速度。由于 benchmark 自身的报告只给出单项任务的结果，本工具读取同目录的 `benchmark-results.json`（benchmark 的逐实例结果快照），生成可离线打开的交互式页面 `charts.html`，将所有配置放在同一视图中对比。

为了让读者从整体结论逐步深入到具体任务，页面先展示汇总四项任务的综合分数，再用三张权衡散点图（可显示帕累托前沿）对比分数与耗时、token 用量及费用的关系，最后列出分任务的分数、耗时、token、费用和速度明细。这个页面是独立的比较视图：它把分任务结果汇总为综合分数，不修改输入数据，也不替代 benchmark 自身的正式报告。

## 版本 v2.6

在查看图表或构建页面前，需要先了解当前数据集的版本背景及其与早期版本的区别。

v2.6 再次只改费用口径，所有实例、分数、耗时和 token 数据与 v2.5 相同。所有套餐运行（Claude、GPT 与 Gemini 模型）现在都换算成订阅价格：该次运行用掉的 Claude $100 套餐周费用（$100 ÷ 30 × 7 = $23.33）的份额。例如用掉套餐周额度 1/100 的运行，费用就是周费用的 1/100，约 $0.23。份额经等效任务点求得（见“费用”一节），任务点只是在不同模型和套餐之间换算的途径。v2.6 相对 v2.5 把所有套餐运行乘以同一个常数，所以任意两个套餐运行之间的费用比例不变，Claude 的费用回到 v2.4 的值。DeepSeek 与 Strata 没有订阅，仍按实际花费的美元计，与套餐运行口径不同。页面文字和本 README 都按这个说法描述费用：悬停提示只放数据（数值、单位和短标签；每个点只有一个可比较的费用），费用口径的说明放在图表下方的说明区和页面底部的数据说明。

### v2.5

v2.5（已被 v2.6 取代）把所有套餐运行按每个等效任务点 $100 折成 Claude API 美元（API 等价费用 × 套餐类别的效率比 E）。v2.6 保留这些比例，只换了单位。

### v2.4

v2.4（已被 v2.5 与 v2.6 取代）把 Claude Code 与 Codex 上的套餐运行按该次运行占 $100 套餐周额度的比例乘以套餐周费用（$100 ÷ 30 × 7 = $23.33）计价，Gemini 4 Hydrogen 仍按参考 API 价。它用的周额度系数是每周 API 等价 $536（Claude $100 套餐）和 $470（OpenAI $100 套餐）。

### v2.3

v2.3 在 v2.2 的基础上，加入 Gemini 4 Hydrogen `low` 推理强度，Hydrogen 补测因此覆盖四档（`low`、`medium`、`high`、`xhigh`），其余实例与 v2.2 完全相同。low 比其余三档晚一天运行，方法相同（Antigravity 1.5.9，计入全部有效运行，每项任务 5 次，同一时限规则和盲裁）；它的 20 个实例没有作废或重跑。v2.2 说明的数据源事实同样适用于它。

### v2.2

v2.2 在 v2.1 的基础上，加入 benchmark 第四阶段补测的 Gemini 4 Hydrogen `medium`、`high` 和 `xhigh` 推理强度，其余实例与 v2.1 完全相同。以下是数据源的事实：补测比 v2.0 的运行晚约三周，服务端模型或路由可能已有变化；它使用另一种代理程序 Antigravity（`agy`），该程序自带系统提示、工具集和上下文管理，其版本在部分运行中为 1.5.8、部分为 1.5.9（每个实例都记录了版本）；Antigravity 的工作时间是 `agy` 进程墙钟时间按一次运行的各会话相加，每个会话含约 7 秒启动，benchmark 也不给它引擎速度（只有任务速度）。与上一次补测相同，每格计入全部有效运行（这里每项任务 5 次），benchmark 本身也不将这些配置与其他配置直接比较。本页则与其他配置一样绘制并比较它们。

### v2.1

v2.1 在 v2.0 数据的基础上，加入了 benchmark 第三阶段补测的 GPT-6 Luna `xhigh` 和 `max` 推理强度（通过 Codex 运行），其余实例与 v2.0 完全相同。由于补测晚一天进行，服务端模型或路由可能已有变化；因此每格计入全部有效运行（每项任务 5 至 8 次），benchmark 本身也不将这两个配置与其他配置直接比较。

### v2.0

作为 v2.1 的基础，v2.0 是一轮重新设计的测量，结果不能与 v1 直接比较：

- 采用新的模型集，并通过两种代理程序运行：Codex 0.163.0 和 Claude Code 2.1.303。
- 评分规则升级为 r8.4：分数不在 0 处截断，可以为负；模型失误（没有产出报告）记 0；诊断评分照常计入，不再乘以 0.9。
- 每个配置每项任务计入 5 次运行（本地 Strata 为 10 次），分数图新增 95% 置信区间。
- 新增任务速度与引擎速度（tok/s）。
- 费用按厂商分别取计价依据：套餐运行（Claude、GPT 与 Gemini 模型）按占 Claude $100 套餐周费用的份额计，API 运行按美元，本地模型按本地运行成本估算（见下文）。

受这些改动影响，`build.py` 只支持 v2.x 的数据（结果文件 schema 1）；v1 的页面和脚本保留在 Git 历史中。

## 测量范围

这组开发审查任务来自软件项目 ARW。v1 任务是冻结的 ARW 760007c 加补丁（计分 r8.4，存于私有工程 qwen-strata，tag `reviewer-bench-v1`）；之后版本的题目、答案键和计分代码公开在 ARW，按提交引用。在 ARW 的开发流程中，每个 Reviewer 是一个负责特定代码或文档审查任务的 AI Agent。页面汇总以下 4 项 Reviewer 任务，并按它们在流程中的比重赋予综合分数权重：

| Reviewer | 工作 | 综合分数权重 |
| --- | --- | ---: |
| Code Standards | 对照仓库指令与实现质量标准审查代码变更。 | 20% |
| Code Spec | 检查代码变更是否准确、完整地落实给出的要求。 | 20% |
| Commit Audit | 审计暂存的提交候选：选中的文件、必要检查和要求的覆盖情况。 | 25% |
| Spec Readiness | 实施前检查需求文档是否完整、一致、可实现且可验证；每次运行有两个独立审查线程。 | 35% |

围绕这 4 项任务，benchmark 共测试了 33 个配置（27 个主配置、2 个第三阶段和 4 个第四阶段补充配置）：

| 代理程序 | 模型 | 推理强度 | 费用依据 |
| --- | --- | --- | --- |
| Codex | GPT-6.1 Sol | low、medium、high | 套餐运行，按占 Claude $100 套餐周费用的份额计 |
| Codex | GPT-6 Luna | low、medium、high、xhigh、max（xhigh、max 为补测） | 套餐运行，按占 Claude $100 套餐周费用的份额计 |
| Codex | DeepSeek V4.1 Flash | low、high、max | DeepSeek 逐请求价格 |
| Codex | Strata IQ3_XXS（本地） | low、medium、high | 本地运行成本 |
| Claude Code | Claude Opus 5.5、Sonnet 5.5、Haiku 5.5 | low、medium、high | 套餐运行，按占 Claude $100 套餐周费用的份额计 |
| Claude Code | DeepSeek V4.1 Flash | low、high、max | DeepSeek 逐请求价格 |
| Claude Code | Strata IQ3_XXS（本地） | low、medium、high | 本地运行成本 |
| Antigravity | Gemini 4 Hydrogen | low、medium、high、xhigh（均为第四阶段补测） | 套餐运行，按占 Claude $100 套餐周费用的份额计（E 为估算） |

表中 DeepSeek V4.1 Flash 是 DeepSeek 端点的 `deepseek-flash` 模型（版本 DeepSeek-V4.1-Flash-1017）；Strata IQ3_XXS 是 Qwen3.8-Flash-Next 的 3 比特量化版本，在一台家用电脑（RTX 3080 Ti 12 GB、i9-13900、64 GB 内存）上本地运行。各配置的推理强度标签仅代表向模型请求的参数设置，不同模型间的同一标签并不代表相同的计算量。

全部测量于 2026-10-19 至 2026-10-22（UTC）进行，本页共计入 717 次计分运行。解读图表排名时需注意以下三点限制：

- 任务以 Claude Opus 标定，产出报告也由 Opus 裁决，因此 Opus 的排名位置可能偏高。
- 结果只反映这组固定任务上的表现，不是通用模型排名。
- v1 的场景、原始报告与隐藏用例不公开，因此可以用仓库中的快照重算图表，但不能重跑 v1 的测量；之后版本可按其引用的 ARW 提交重跑。

## 统计规则

为了将上述原始运行记录转化为图表中的数值，构建脚本会先筛选有效实例，再按以下规则汇总分数、资源消耗与速度。

### 计入哪些运行

首先，页面筛选快照中的运行记录，只采用 benchmark 主统计计入的实例（`selection.inMain` 为真且没有 `supplementaryNote`）以及第三、第四阶段补测实例（后者来自第二份快照文件 `benchmark-results-phase4.json`，由构建脚本合并）：

- 常规配置每项任务计入 5 次运行，本地模型 Strata 每项任务计入 10 次。
- GPT-6 Luna xhigh 和 max 属于第三阶段补充配置（`kind` 为 `phase3`），按 benchmark 的口径计入每格的全部有效实例，每项任务 5 至 8 次。
- Gemini 4 Hydrogen low、medium、high 和 xhigh 属于第四阶段补充配置（`kind` 为 `phase4`），计入每格的全部有效实例，每项任务 5 次。
- DeepSeek 请求设为 medium、但端点在相同时限下实际按 high 执行的运行，按 benchmark 口径并入 high 格。页面根据筛选后的数据生成运行数范围及各运行数对应的格数分布。
- 无效运行，以及因时限不同而单列的“请求 medium”补充配置，均不进入页面。
- Code Spec 与 Code Standards 的时限：每个实例的时限 T 按所测配置自身的速度算出，并限制在 15 至 60 分钟之间。到时限被中断的实例作废，并以 60 分钟重跑；60 分钟仍被中断则停下等待决定。最终只计在各自时限内完成的实例。因此交接提示里写的时限数字在实例和它的重跑之间不同，这是已知的小偏差。Gemini 4 Hydrogen 有 6 次这样的重跑（low 没有；medium 的 Code Spec 1 次，xhigh 的 Code Spec 2 次、Code Standards 3 次）。较早的模型里有 3 个实例撞到旧时限而作废：Claude Haiku low 的 Code Spec a7、a8，以及 DeepSeek-flash max（Claude Code）的 Code Spec a4。Haiku low 已以 60 分钟补跑（a9、a10，Claude Code 2.1.310，原为 2.1.303，事后另开一个盲裁池裁决）。DeepSeek 的补跑因 API 密钥被拒无法进行，该格主统计只有 4 个实例而不是 5 个。

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

每次运行计入分母的秒数取其自身速度对应的时间口径，从而保留 benchmark 的两套时间基准：任务速度用工作秒数（代表用户实际感受到的速度），引擎速度用请求或解码秒数（代表模型本身的速度）。在 token 口径上，输入速度用未缓存输入 token，输出速度用输出 token。由于远程 API 模型无法把输入处理时间从解码时间中拆出来，其引擎输入速度未知，引擎输出速度也只是下限（≥）；只有本地运行的 Strata 具有引擎输入速度。Antigravity 的运行没有任何引擎速度（benchmark 不给，因为其数据流没有把每次响应秒数换算成引擎速度的规则），只有任务速度；其工作秒数是 `agy` 进程墙钟时间，每个会话含约 7 秒启动。

### 缺值

最后，部分运行缺少某项具体指标的数据。缺失值一律不当作 0 处理：某次运行缺少某项数据时，只在该项指标中跳过，其余指标照常计入，并在图下方的说明中列出受影响的格。由于 API 模型的引擎输入速度和 Antigravity 的两项引擎速度按设计就是未知的，速度图下方的说明不再单独列出。标有 ≥ 的数值表示下限，例如 DeepSeek 因时限提醒丢弃了部分请求而未能完整计入的费用。

## 费用

在各项指标中，费用需要单独制定换算规则，因为不同配置分别通过订阅套餐、按请求计费 API 和本地硬件运行。因此，页面上的所有费用都不是实际账单；具体单价于 **2026-10-22** 核对（下文的套餐周额度与任务点系数于 **2026-11-18** 取值），换算规则保存在 `pricing.json` 中。所有配置仍以美元计，画在同一条费用轴上；套餐运行按订阅费计，DeepSeek 与 Strata 按实际花费计，两组口径不同：

| 厂商 | 依据 |
| --- | --- |
| OpenAI | 套餐运行，按占套餐周额度的份额：token × OpenAI Standard API 单价，再按下文折算 |
| Google | 套餐运行，按占套餐周额度的份额：token × Google Gemini API 单价（输出含思考），再按下文折算 |
| Anthropic | 套餐运行，按占套餐周额度的份额：Claude Code 报告的 API 等价费用（实例 `cost.usd`），再按下文折算 |
| DeepSeek | 实例 `cost.usd`：按官方价逐请求计算，区分高峰 / 低谷 |
| Strata（本地） | 本地运行成本：工作秒数 × 每小时成本 |

套餐费用折算（所有套餐运行：Claude、GPT 与 Gemini）：页面显示的费用是该次运行用掉的 Claude $100 套餐周额度的份额乘以该套餐的周费用（$100 ÷ 30 × 7 = $23.33）。例如同一个 $100 套餐一周可跑小模型 10G token、大模型只能跑 1G，图表里两者各用了 100M token，则小模型费用是周费用的 1/100，大模型是 1/10。份额经等效任务点求得，这是作者状态页的计量单位：1 点固定等于 $100 的 Claude API 花费（Claude Max 20x 周额度的 1/20）；Claude $100 套餐一周有 5.36 点（约 $536 的 Claude API 标价用量，2026-11-18 在本机 Max 20x 套餐上实测，$100 套餐按其四分之一取，误差约 ±10%；与 v2.4 用的系数相同）；套餐类别的效率比 E 是 Claude 做同类已完成的活会花的钱除以该套餐实际花的钱（取自作者自己最近 28 天的使用历史）。一次运行的点数 = API 等价费用 × E ÷ $100，费用 = 点数 ÷ 5.36 × $23.33。例如 API 等价费用 $1.7055 的 Claude Opus 运行（E = 1）是 0.0171 点，占套餐周额度的 0.318%，费用 $0.0742；$0.5084 的 GPT-6.1 Sol 运行为 $0.5084 × 1.88 = $0.957，0.00957 点，占 0.179%，费用 $0.0417。悬停悬停提示只显示最终价格，标注为换算成套餐订阅费的价格；点数、API 等价费用、E 和占套餐周额度的份额只在这里说明，不进提示。E 每个套餐类别一个值，该套餐的所有模型通用，不用各模型自己的 E，所以同一个套餐不会出现两种价格：

| 套餐类别 | E | 依据 |
| --- | ---: | --- |
| Claude 套餐 | 1 | 按定义（Claude 做 Claude 的活）；状态页 2026-11-18 的值。 |
| Codex 套餐（Sol 与 Luna 通用） | 1.88 | 状态页 2026-11-18 的类别值：95% 区间 1.55 至 2.34，历史覆盖率 52.5%；Luna 自己的 E（24.3）因低于页面 30% 的覆盖门槛不显示，不采用。 |
| Antigravity Gemini 套餐 | 1.19（估算） | 取自 2026-11-16 的一次分析，基线按 Claude 真实审核件数加权（其他基线为 1.08 至 1.15）；覆盖率 32% 至 48% 低于状态页的显示门槛，且 Antigravity 的统计已于 2026-11-17 撤除，这个值不会再更新。 |

E 是滚动 28 天的测量值，会随作者的使用变化，所以页面使用 `pricing.json`（`taskPoints`）中带日期的快照，不跟随之后的变化。Codex 的 E 在运行间的离散之外还带有上述区间大小的不确定度，Gemini 的 E 是页面上最不确定的数字。

其中，OpenAI 模型按 token 用量乘以 OpenAI Standard API 单价（美元 / 百万 token）：

| 模型 | 未缓存输入 | 缓存输入 | 输出 |
| --- | ---: | ---: | ---: |
| [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) | $2 | $0.10 | $10 |
| [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) | $0.10 | $0.01 | $0.50 |

对 Gemini 模型，token 数乘以下列 Google Gemini API 单价（美元每百万 token；来源 [Google AI 价格页](https://ai.google.dev/gemini-api/docs/pricing)，数值由本次更新的任务给定，加入时未重新抓取核对）；输出数已含思考 token：

| 模型 | 未缓存输入 | 缓存输入 | 输出 |
| --- | ---: | ---: | ---: |
| Gemini 4 Hydrogen | $1.50 | $0.075 | $7.50 |

缓存写入 token 不计价：`pricing.json` 中的 `cacheWriteRate` 仅作参考，若 OpenAI 实例带有缓存写入 token，构建会直接报错停止。

本地 Strata 模型的运行成本只粗略估算工作期间的电费和硬件维护，不含硬件购置、安装及实例之间的空闲时间：

| 项目 | 取值 | 说明 |
| --- | ---: | --- |
| 整机功率 | 400 W | 粗略的整机负载估计（GPU 板卡上限 350 W，受显存带宽限制的解码通常更低） |
| 电价 | $0.174 / kWh | 2026 年第一季度全球家庭平均电价（按国家平均，[GlobalPetrolPrices](https://www.globalpetrolprices.com/electricity_prices/)） |
| 维护 | $0.02 / 小时 | 风扇、电源等损耗件，约每年 $50、按每年约 2,500 负载小时摊 |
| 合计 | 约 $0.09 / 小时 | |

按工作时间折算后，本地成本恒大于 0，图表中的对数费用轴不会遇到 0。同时，由于本地运行比远程 API 慢得多，Strata 每次运行的成本约为 $0.015–0.019；与套餐费用放在一起，它高于最便宜的套餐运行（GPT-6 Luna、Claude Haiku 和 Gemini low，约 $0.002–0.013），低于其余套餐配置。

## 文件

了解页面的统计与计价口径后，可以查看仓库文件或自己在本地生成页面。仓库结构如下：

```text
./
├── build.py
├── stats.py
├── test_build.py
├── benchmark-results.json
├── benchmark-results-phase4.json
├── pricing.json
├── README.md
├── README.zh-CN.md
├── AGENTS.md
├── sources.json
├── tools/
│   └── import_bundle.py
└── resources/
    ├── site.css
    ├── favicon.svg
    └── fonts/
```

各文件在构建流程中分工如下：

- **代码与计价参数**：`stats.py` 保存统计与费用规则（纯 Python，不依赖 Plotly），`build.py` 绘制图表并组装页面，`test_build.py` 负责测试，`pricing.json` 保存计价参数。
- **样式、字体与生成物**：`resources/site.css` 是页面唯一的样式表，`resources/fonts/` 存放预下载的字体（字体许可与来源见 `resources/fonts/README.md`）。`resources/favicon.svg` 由脚本生成并保存在仓库中；`charts.html` 则是本地生成的文件，不提交到 Git。
- **数据快照**：`benchmark-results.json` 是输入数据的独立快照，`benchmark-results-phase4.json` 是第四阶段 Gemini 4 Hydrogen 运行的补充快照（同一格式，由构建脚本合并）。构建页面时只读取仓库中已提交的这些快照，不会从其他目录自动同步数据。`sources.json` 记下每份快照的来源（工程、提交、路径、sha256、题目套件与计分版本），`test_build.py` 会按它核对快照。主快照内的 `meta.source` 已过期，以 `sources.json` 为准。

当外部 benchmark 有新数据需要同步时，维护者从来源提交取出文件并核对哈希，再把新的提交、路径和 sha256 写进 `sources.json`。例如在仓库根目录（来源工程是本地克隆，取值来自 `sources.json`）：

```bash
git -C "$SOURCE_REPO" show "$COMMIT:$SRC_PATH" > benchmark-results.json
sha256sum benchmark-results.json   # 必须与 sources.json 中的 sha256 一致
```

第四阶段快照用同样方式更新到 `benchmark-results-phase4.json`。

## 运行 benchmark 并导入 ARW 结果

按照 [ARW 开发手册](https://github.com/Tranzvision/agent-repository-workflow/blob/83bdb6b4f5ec39e7b32b30862a9ece24aa9b7fc6/docs/manuals/development.md#run-the-capability-suite-with-a-command-line-model)检查模型配置、规划并运行题目套件，再用 `arw reviewer-capability pack` 生成结果包。
导入工具接受 fixture tree 为 `4326aca3cbd04ae126f6f4a3e26867f2b740e81a`、来自以下三个干净 ARW 提交之一的 schema 1、tool 1 结果包：

- `83bdb6b4f5ec39e7b32b30862a9ece24aa9b7fc6`，主提交。
- `6ca23a9d5b9d1116a9690bbbc39b42a408b8df07`，本仓库已撤掉的 `tools/remote_run` 打包工具所固定的提交；这类压缩包里还可以带该打包工具写入、清单未列出的 `attempts.jsonl` 日志。
- `5a4e304250dfd927be14026a9a327a0de4c05385`，用于检查记录为 `agy-record` 的结果包；压缩包内须有 `agy.jsonl`。只有这个提交可以使用 `agy-record`，另两个提交的包不得含 `agy.jsonl`。

不接受其他提交。

在本仓库根目录用 Python 3.11 或更新版本运行：

```bash
python3 tools/import_bundle.py /path/to/results.tar.gz --dry-run
python3 tools/import_bundle.py /path/to/results.tar.gz
```

导入工具检查压缩包的成员列表、字节数、SHA-256 哈希，以及每个实例记录的来源信息。它把压缩包的原始字节保存为 `snapshots/arw/<sha256>.tar.gz`，并把压缩包哈希、源文件名、ARW 提交与运行时版本、题目套件与 fixture tree、该提交的计分代码路径和代理程序（harness）一并写入 `sources.json`。再次导入相同字节会复用已有快照。新快照与登记项应一起审核并提交。这些压缩包保存原始运行结果，供之后裁决与汇总使用；页面构建读取已提交的 `benchmark-results*.json` 快照作为输入。

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

页面生成工具只处理已提交的 JSON 快照。benchmark 由 ARW 运行并计分，导入工具则按收到的原样保存原始结果。

为了便于独立验证统计逻辑，计算与绘图拆分为两个模块：

- `stats.py` 用纯 Python 读取 JSON 并计算各项指标（包括纯 Python 实现的 t 分布分位数），价格由调用方从 `pricing.json` 传入。由于不依赖 Plotly，即使未安装 Plotly 也能运行 `test_build.py` 检查统计逻辑（缺少 Plotly 时自动跳过页面生成测试）。
- `build.py` 调用 Plotly 生成图表并嵌入 HTML。页面文字和图表坐标轴支持在英文与中文之间切换，所有图表交互均在浏览器本地运行。

维护配置项或统计规则时，需要同步更新相关文件：

- **模型、权重与视觉配置**：模型顺序与名称、代理程序以及 4 项 Reviewer 的权重定义在 `stats.py` 顶部；模型颜色和评分版本定义在 `build.py` 顶部。
- **价格与本地成本参数**：保存在 `pricing.json`。页面方法说明中的价格、功率、电价和权重由 `pricing.json` 与 `REVIEWERS` 动态生成；调整价格或参数后，请更新 `checkedAt`、重新生成页面，并同步更新两份 README 中的费用表。套餐周额度与任务点系数（`taskPoints`：Claude $100 套餐一周的点数与费用、点值和每个套餐类别一个 E）有各自的 `checkedAt` 和来源；套餐或价目变动时，从状态页的 `taskpts.json` 重新取值。
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
