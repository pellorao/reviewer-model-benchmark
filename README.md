# Reviewer Model Benchmark Page Builder

English · **[简体中文](README.zh-CN.md)**

[Open the published benchmark page](https://reviewer-model-benchmark.pages.dev/reviewer-model-benchmark/)

When choosing an AI model, agent harness, and reasoning effort for code or specification review, you need to weigh review quality against work time, token usage, cost, and speed across all tasks at once. Because the benchmark's own reports give per-task results only, this tool reads `benchmark-results.json` (a snapshot of the benchmark's per-run results) and builds `charts.html`, an offline interactive page that brings every configuration into one comparison view.

To let you move from the big picture to individual tasks, the page shows the overall weighted score first, then maps score against work time, token usage, and cost in three trade-off scatter plots (with an optional Pareto front), and finally breaks down per-task score, work time, token usage, cost, and speed. This page is an independent comparison view: it summarizes the per-task results into a weighted score without modifying the input data or replacing the benchmark's own reports.

## Version v2.6

Before reading the charts or building the page, it helps to know which dataset version is included and how it evolved.

Version v2.6 changes only the cost basis again; no instance, score, time or token value changes from v2.5. Every subscription-plan run (Claude, GPT and Gemini models) is now priced as a subscription fee: the share of the Claude $100 plan's weekly fee ($100 ÷ 30 × 7 = $23.33) that the run used up. For example, a run that uses 1/100 of the plan's weekly quota costs 1/100 of the weekly fee, about $0.23. The share is found through equivalent task points (see the Cost section), which only serve as the way of converting between models and plans. Because v2.6 multiplies every plan run by the same constant relative to v2.5, the cost ratios between any two plan runs are unchanged, and Claude costs return to their v2.4 values. DeepSeek and Strata have no subscription and keep their actual-cost dollars, so they are not on the same footing as the plan runs. The page text, tooltips and this README describe the cost this way.

### v2.5

Version v2.5 (superseded by v2.6) priced every subscription-plan run in Claude API dollars at $100 per equivalent task point (API-equivalent cost × the plan category's efficiency ratio E). v2.6 keeps those ratios and only changes the unit.

### v2.4

Version v2.4 (superseded by v2.5 and v2.6) priced Claude Code and Codex subscription runs by the share of the $100 plan's weekly quota the run used, times the plan's weekly cost ($100 ÷ 30 × 7 = $23.33), and left Gemini 4 Hydrogen at its reference API price. Its factors were $536 (Claude $100 plan) and $470 (OpenAI $100 plan) of API-equivalent quota a week.

### v2.3

Version v2.3 adds Gemini 4 Hydrogen at `low` effort, so the Hydrogen supplement now covers four tiers (`low`, `medium`, `high`, `xhigh`), and leaves every other instance unchanged from v2.2. Low ran one day after the other three tiers with the same method (Antigravity 1.5.9, every valid run counted, 5 per task, the same time-limit rule and blind adjudication); none of its 20 instances was voided or rerun. The same data-source facts as v2.2 apply to it.

### v2.2

Version v2.2 adds Gemini 4 Hydrogen at `medium`, `high` and `xhigh` effort, from the benchmark's phase-4 supplement, and leaves every other instance unchanged from v2.1. As data-source facts: the supplement ran about three weeks after the v2.0 runs, so the served model or routing may have changed; it ran in a different harness, Antigravity (`agy`), which brings its own system prompt, tools and context management, and its version was 1.5.8 for some runs and 1.5.9 for others (each instance records its version); the Antigravity work time is the `agy` process wall time summed over a run's sessions, which includes about 7 seconds of start-up per session, and the benchmark gives no engine speeds for it (only task speeds). As for the earlier supplement, each cell counts every valid run (5 per task here), and the benchmark itself does not compare these configurations with the others. The page draws and compares them like every other configuration.

### v2.1

Version v2.1 takes the v2.0 data and adds the GPT-6 Luna `xhigh` and `max` efforts (run in Codex) from the benchmark's phase-3 supplement, while keeping all other instances unchanged from v2.0. Because the supplement ran a day later, the served model or routing may have changed; as a result, each cell counts every valid run (5 to 8 per task), and the benchmark itself does not compare these two configurations with the others.

### v2.0

Underlying v2.1 is the v2.0 measurement, which was a complete redesign whose results are not comparable with v1:

- It evaluates a new set of models run through two agent harnesses: Codex 0.163.0 and Claude Code 2.1.303.
- It uses scoring r8.4: scores are not cut at 0 and can be negative; a model failure (no report) scores 0; and diagnostic scores count as is, with no 0.9 discount.
- Each configuration counts 5 runs per task (10 for the local Strata model), and the score charts show 95% confidence intervals.
- It adds task speeds and engine speeds (tok/s).
- Cost bases differ by vendor: subscription runs (Claude, GPT and Gemini models) are priced as their share of the Claude $100 plan's weekly fee, API runs in USD, and the local model by a local running cost (see below).

Because of these changes, `build.py` supports v2.x data only (results file schema 1); the v1 page and script remain in the Git history.

## Scope

The benchmark tasks come from ARW, the software project that provides these development review tasks. In ARW's development process, a Reviewer is an AI agent that performs one specific code or document review task. The page combines four Reviewers, weighted by their share in the overall score:

| Reviewer | Work | Weight |
| --- | --- | ---: |
| Code Standards | Reviews code changes against repository instructions and implementation quality standards. | 20% |
| Code Spec | Checks whether code changes implement the supplied requirements accurately and completely. | 20% |
| Commit Audit | Audits a staged commit candidate: the selected files, required checks and coverage of the requirements. | 25% |
| Spec Readiness | Before implementation, checks whether requirement documents are complete, consistent, feasible and verifiable; each run has two independent review threads. | 35% |

Across those four tasks, the benchmark tests 33 configurations (27 main, 2 phase-3 and 4 phase-4 supplement configurations):

| Harness | Models | Efforts | Cost basis |
| --- | --- | --- | --- |
| Codex | GPT-6.1 Sol | low, medium, high | Subscription run, priced as its share of the Claude $100 plan's weekly fee |
| Codex | GPT-6 Luna | low, medium, high, xhigh, max (xhigh and max in the supplement) | Subscription run, priced as its share of the Claude $100 plan's weekly fee |
| Codex | DeepSeek V4.1 Flash | low, high, max | DeepSeek price per request |
| Codex | Strata IQ3_XXS (local) | low, medium, high | Local running cost |
| Claude Code | Claude Opus 5.5, Sonnet 5.5, Haiku 5.5 | low, medium, high | Subscription run, priced as its share of the Claude $100 plan's weekly fee |
| Claude Code | DeepSeek V4.1 Flash | low, high, max | DeepSeek price per request |
| Claude Code | Strata IQ3_XXS (local) | low, medium, high | Local running cost |
| Antigravity | Gemini 4 Hydrogen | low, medium, high, xhigh (all in the phase-4 supplement) | Plan run, priced as its share of the Claude $100 plan's weekly fee (estimated E) |

In this table, DeepSeek V4.1 Flash is the endpoint's `deepseek-flash` model (version DeepSeek-V4.1-Flash-1017), and Strata IQ3_XXS is a 3-bit quantization of Qwen3.8-Flash-Next run locally on a home PC (RTX 3080 Ti 12 GB, i9-13900, 64 GB RAM). Effort labels are each model's requested setting, not equal compute across models.

All runs took place from 2026-10-19 to 2026-10-22 (UTC), and the page counts 717 scored runs. When interpreting the results, keep three boundaries in mind:

- The tasks were calibrated on Claude Opus, which also judged the reports, so Opus may be placed too high.
- The results describe this fixed task set only and are not a general model ranking.
- The full scenarios, raw reports and hidden cases are not in this repository, so the charts can be recomputed from the snapshot, but the measurement cannot be rerun from it.

## Statistics

To turn those raw runs into the numbers plotted on the page, the build filters the snapshot and aggregates scores, resource usage, and speeds using the rules below.

### Counted runs

First, the page filters the snapshot so that it uses only the instances the benchmark counts in its main statistics (`selection.inMain` true and no `supplementaryNote`), plus the phase-3 and phase-4 supplements (the latter comes from a second snapshot file, `benchmark-results-phase4.json`, merged by the build):

- Standard configurations count 5 runs per task, while Strata counts 10 per task.
- GPT-6 Luna xhigh and max are phase-3 supplement configurations (`kind` `phase3`); following the benchmark, every valid instance of each cell counts, giving 5 to 8 runs per task.
- Gemini 4 Hydrogen low, medium, high and xhigh are phase-4 supplement configurations (`kind` `phase4`); every valid instance of each cell counts, giving 5 runs per task.
- DeepSeek runs requested as medium that the endpoint ran as high under the same time limit count as high, following the benchmark. The page generates its run-count range and cell-count distribution from the selected data.
- Invalid runs and the supplementary "requested as medium" configuration, which ran under a different time limit, are excluded.
- Time limit for Code Spec and Code Standards: the limit T of an instance is computed from the configuration's own speed and held between 15 and 60 minutes. An instance stopped by the limit is voided and rerun at 60 minutes; if it is stopped again at 60 minutes the run halts for a decision. Only instances that finished within their limit are counted. The limit stated in the hand-off prompt therefore differs between an instance and its rerun, a known small deviation. Gemini 4 Hydrogen had 6 such reruns (low had none; medium Code Spec 1, xhigh Code Spec 2, xhigh Code Standards 3). Among the earlier models, three instances hit the old limit and were voided: Claude Haiku low Code Spec a7 and a8, and DeepSeek-flash max (Claude Code) Code Spec a4. Haiku low was rerun at 60 minutes (a9, a10, Claude Code 2.1.310 instead of 2.1.303, blind-adjudicated afterwards as one separate pool). The DeepSeek rerun could not run (its API key was rejected), so that cell has 4 instances in the main statistic instead of 5.

### Scores

Next, for all counted runs, scores are calculated at the run level and then rolled up to each task and to the overall weighted score.

A single run's score (r8.4) credits the answer-key problems a report finds and deducts its false findings, without a cut at 0. A task score is the mean of the cell's runs, paired with a 95% confidence interval from the t distribution (half-width = t₀.₉₇₅,ₙ₋₁ × SD / √n). From the four task means, the page computes the overall weighted score:

```text
weighted score = 100 × (
    0.20 × Code Standards
  + 0.20 × Code Spec
  + 0.25 × Commit Audit
  + 0.35 × Spec Readiness
)
```

Its 95% half-width is t × √Σ(wᵢ² · SEᵢ²), with Welch–Satterthwaite degrees of freedom.

### Time, tokens and cost

While scores measure review quality, time, tokens, and cost measure the resources spent. Because zero-score and model-failure runs still consumed resources, these three measures average every counted run.

For each measure, a task's value is the mean over its runs with data, and a configuration's overall value is the arithmetic mean of its four task values. Time is measured in work seconds, excluding setup and loading: Codex counts the agent's accumulated work time and Claude Code counts the session's wall time. Because Spec Readiness runs two independent review threads, its time adds both threads together.

### Speed

Using the token and time totals, the page also computes processing speeds. To reflect true throughput across runs, a speed is always total tokens divided by total seconds, never a mean of per-run speeds:

- A task's speed = the sum of its runs' tokens ÷ the sum of their seconds.

Each run's seconds are the denominator of its own speed, which preserves the benchmark's two time bases: task speeds use work seconds (the speed a user perceives) and engine speeds use request or decode seconds (the model alone). On the token side, input speeds use non-cached input tokens and output speeds use output tokens. Because API models cannot separate input processing time from output decoding, their engine input speed is unknown and their engine output speed is a lower bound (≥); only the local Strata model has an engine input speed. Antigravity runs have no engine speeds at all (the benchmark gives none, since its stream has no rule for turning per-response seconds into one), only task speeds; their work seconds are the `agy` process wall time, including about 7 seconds of start-up per session.

### Missing values

Finally, some runs lack a specific measurement. Missing values are never treated as zero: a run missing one measure is skipped for that measure only, and notes under the charts list the affected cells. The speed chart's note leaves out the engine input speed of API models and both engine speeds of Antigravity, since those are unknown by design. Where a value is only partially captured—for example, DeepSeek costs that miss requests dropped by a time-limit reminder—it is marked with ≥ to indicate a lower bound.

## Cost

Among the metrics above, cost requires special handling because configurations ran under different billing methods—subscription plans, per-request API billing, and local hardware. Consequently, no cost on the page is an actual bill. Instead, prices were checked on **2026-10-22** (the plan-week and task-point factors below on **2026-11-18**), and the rules in `pricing.json` put each vendor on a defined cost basis. All configurations stay in US dollars on one cost axis. Subscription runs are priced as a subscription fee while DeepSeek and Strata are priced by actual spending, so the two groups are not on the same footing:

| Vendor | Basis |
| --- | --- |
| OpenAI | Subscription run, share of the plan week: tokens × OpenAI Standard API rates, then the conversion below |
| Google | Plan run, share of the plan week: tokens × Google Gemini API rates (output includes thinking), then the conversion below |
| Anthropic | Subscription run, share of the plan week: the API-equivalent cost Claude Code reports (instance `cost.usd`), then the conversion below |
| DeepSeek | Instance `cost.usd`: official prices per request, peak or off-peak |
| Strata (local) | Local running cost: work seconds × hourly cost |

Plan-fee conversion (all subscription-plan runs: Claude, GPT and Gemini): the cost shown is the run's share of the Claude $100 plan's weekly quota times that plan's weekly fee ($100 ÷ 30 × 7 = $23.33). If a $100 plan week allowed 10G tokens of a small model but only 1G of a large one, and both used 100M tokens in a chart, the small model costs 1/100 of the weekly fee and the large one 1/10. The share is found through equivalent task points, the unit of the author's status page: one point is a fixed $100 of Claude API spending (1/20 of a Claude Max 20x weekly quota); a Claude $100 plan week holds 5.36 points (about $536 of Claude API-priced use, measured on 2026-11-18 on the local Max 20x plan with the $100 plan taken as a quarter of it, about ±10%; the same factor v2.4 used); and a plan category's efficiency ratio E is what Claude would have spent on the same kind of finished work divided by what that plan actually spent (from the author's own 28-day usage history). A run's points are its API-equivalent cost × E ÷ $100, and its cost is points ÷ 5.36 × $23.33. A Claude Opus run with an API-equivalent cost of $1.7055 (E = 1) is 0.0171 points, 0.318% of a plan week, $0.0742; a GPT-6.1 Sol run of $0.5084 is $0.5084 × 1.88 = $0.957, 0.00957 points, 0.179% of a plan week, $0.0417. The tooltips show the points, the API-equivalent cost, E and the share of the plan week. E is one value per plan category and is used for every model of that plan, not each model's own E, so one plan never has two prices:

| Plan category | E | Basis |
| --- | ---: | --- |
| Claude plan | 1 | By definition (Claude's cost of Claude's work); status page value on 2026-11-18. |
| Codex plan (Sol and Luna alike) | 1.88 | Status page category value on 2026-11-18: 95% interval 1.55 to 2.34, 52.5% coverage of the history; Luna's own E (24.3) is hidden by the page's 30% coverage rule and is not used. |
| Antigravity Gemini plan | 1.19 (estimate) | From a 2026-11-16 analysis, baseline weighted by Claude's real review counts (1.08 to 1.15 under other baselines); coverage 32 to 48% is below the status page's display threshold, and the Antigravity tracking was removed on 2026-11-17, so the figure will not be updated. |

E is a rolling 28-day measurement and moves with the author's usage, so the page uses the dated snapshot in `pricing.json` (`taskPoints`) and does not follow later changes. The Codex E carries roughly the interval above on top of the usual run-to-run spread, and the Gemini E is the least certain figure on the page.

For OpenAI models, token counts are multiplied by these OpenAI Standard API rates (USD per million tokens):

| Model | Non-cached input | Cached input | Output |
| --- | ---: | ---: | ---: |
| [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) | $2 | $0.10 | $10 |
| [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) | $0.10 | $0.01 | $0.50 |

For Gemini models, token counts are multiplied by these Google Gemini API rates (USD per million tokens; source [Google AI pricing](https://ai.google.dev/gemini-api/docs/pricing), as given for this update and not re-fetched when it was added); the output count already includes thinking tokens:

| Model | Non-cached input | Cached input | Output |
| --- | ---: | ---: | ---: |
| Gemini 4 Hydrogen | $1.50 | $0.075 | $7.50 |

Cache-write tokens are not priced: `cacheWriteRate` in `pricing.json` is kept for reference only, and the build stops with an error if an OpenAI instance reports cache-write tokens.

For the local Strata model, the running cost is a rough estimate that covers electricity and upkeep during active work only, excluding hardware purchase, setup, and idle time between runs:

| Item | Value | Note |
| --- | ---: | --- |
| Wall power | 400 W | Rough whole-system load (350 W GPU board limit; memory-bound decoding usually draws less) |
| Electricity | $0.174 / kWh | Q1 2026 world household average, by country ([GlobalPetrolPrices](https://www.globalpetrolprices.com/electricity_prices/)) |
| Upkeep | $0.02 / hour | Fans, power supply and other wear parts, about $50 a year over about 2,500 loaded hours |
| Total | about $0.09 / hour | |

Because this local cost is always above 0, the logarithmic cost axis on the charts never meets 0. And because local runs are much slower than API runs, Strata works out to about $0.015–0.019 per run; next to the plan-fee prices it is above the cheapest plan runs (GPT-6 Luna, Claude Haiku and Gemini low, about $0.002–0.013) and below the other plan configurations.

## Files

Once you understand what the page shows and how its metrics are defined, you can inspect the repository or build the page yourself. The project contains these files:

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
├── .env.example
└── resources/
    ├── site.css
    ├── favicon.svg
    └── fonts/
```

Each file has a distinct role in turning the data snapshot into the finished page:

- **Code and rules**: `stats.py` holds the statistics and cost rules (pure Python, no Plotly), `build.py` draws the charts and assembles the page, `test_build.py` tests them, and `pricing.json` stores the pricing parameters.
- **Styles, fonts, and generated outputs**: `resources/site.css` is the page's only stylesheet, and `resources/fonts/` holds pre-downloaded fonts (see `resources/fonts/README.md` for font licenses and sources). `resources/favicon.svg` is generated by the script and kept in the repository, whereas `charts.html` is a generated local file and is not committed.
- **Data snapshot**: `benchmark-results.json` is an independent snapshot of the input data, and `benchmark-results-phase4.json` is the supplement-only snapshot of the phase-4 Gemini 4 Hydrogen runs (same schema, merged by the build). The build reads only these committed snapshots; it does not read `.env` or sync data from other directories.

To update `benchmark-results.json` when new benchmark data is ready, a maintainer copies `.env.example` to the ignored `.env`, sets `BENCHMARK_SOURCE_RESULTS` to the absolute path of the trusted source file, and runs these Bash commands from the repository root to copy and verify the snapshot:

```bash
. ./.env
: "${BENCHMARK_SOURCE_RESULTS:?Set BENCHMARK_SOURCE_RESULTS in .env}"
cp -- "$BENCHMARK_SOURCE_RESULTS" benchmark-results.json
cmp -- "$BENCHMARK_SOURCE_RESULTS" benchmark-results.json
```

The phase-4 snapshot is updated the same way from `BENCHMARK_SOURCE_SUPPLEMENT_PHASE4` into `benchmark-results-phase4.json`.

## Usage

With the snapshot in place, you can run the tests and generate `charts.html` locally. Building the page requires Python and Plotly (checked with Python 3.14 and Plotly 6.9.0). Run these commands in this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install plotly==6.9.0
.venv/bin/python test_build.py
.venv/bin/python build.py
```

If the system Python lacks `venv` or `pip`, use [uv](https://docs.astral.sh/uv/) instead: run `uv venv .venv`, then `uv pip install --python .venv/bin/python plotly==6.9.0`. On Windows, use `py -m venv .venv` and `.venv\Scripts\python`.

By default, `build.py` reads `benchmark-results.json` next to it and overwrites `charts.html` in the same directory. If you want to use different input or output paths, pass them as arguments:

```bash
.venv/bin/python build.py path/to/benchmark-results.json path/to/charts.html
```

Because the page loads `resources/` by relative path, any custom output directory needs its own `resources/`; the build does not create it for you.

Once `charts.html` is built, open it directly in a browser—viewing it needs no Python, network, or web server. Note that the footer's "Updated" date is the build date, not the measurement or price-check date.

## Implementation and maintenance

If you are modifying the code or updating prices, keep in mind that this tool only processes the snapshot: it does not run the benchmark or modify the input JSON.

Computation and rendering are split between two modules so that the statistical logic can be tested on its own:

- `stats.py` reads the JSON and computes all measures in Python, including a pure-Python t-distribution quantile, using prices passed in by the caller from `pricing.json`. Because it does not depend on Plotly, `test_build.py` can check `stats.py` even without Plotly installed (the page tests are skipped when Plotly is missing).
- `build.py` uses Plotly to draw the charts and embeds them in the HTML. Page text and chart axes switch between English and Chinese, and all chart interaction runs locally in the browser.

When maintaining configuration values or rules, update the matching files together:

- **Models, weights, and visual settings**: Model order and names, harnesses, and the four reviewer weights are defined at the top of `stats.py`; model colors and the scoring version are at the top of `build.py`.
- **Pricing**: Prices and local cost settings live in `pricing.json`. Because the page's method text reads the prices, power, electricity rate, and weights directly from `pricing.json` and `REVIEWERS`, after any pricing change you must update `checkedAt`, rebuild the page, and update the cost tables in both READMEs. The plan-week and task-point factors (`taskPoints`: the Claude $100 plan's weekly points and fee, the point value and one E per plan category) carry their own `checkedAt` and source; refresh them from the status page's `taskpts.json` when the plans or the price lists change.
- **Statistical rules**: Agree on any change to the statistics rules first, as `AGENTS.md` describes, and update both READMEs afterwards.

## Publishing

When changes land on the `master` branch, Cloudflare Pages (which is connected to this GitHub repository) automatically builds and deploys the public site using Python 3.12 and Plotly 6.9.0 into the `_site` output directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install plotly==6.9.0
mkdir -p _site/reviewer-model-benchmark/resources
cp -R resources/. _site/reviewer-model-benchmark/resources/
.venv/bin/python build.py benchmark-results.json _site/reviewer-model-benchmark/index.html
```

Because page assets use relative paths, the published page works under that `/reviewer-model-benchmark/` subpath. Neither the local `charts.html` nor `_site/` is committed to Git, and the custom domain is configured outside the repository.
