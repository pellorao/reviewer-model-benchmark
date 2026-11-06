# Reviewer Model Benchmark Page Builder

English · **[简体中文](README.zh-CN.md)**

[Open the published benchmark page](https://reviewer-model-benchmark.pages.dev/reviewer-model-benchmark/)

When choosing an AI model, agent harness, and reasoning effort for code or specification review, you need to weigh review quality against work time, token usage, cost, and speed across all tasks at once. Because the benchmark's own reports give per-task results only, this tool reads `benchmark-results.json` (a snapshot of the benchmark's per-run results) and builds `charts.html`, an offline interactive page that brings every configuration into one comparison view.

To let you move from the big picture to individual tasks, the page shows the overall weighted score first, then maps score against work time, token usage, and cost in three trade-off scatter plots (with an optional Pareto front), and finally breaks down per-task score, work time, token usage, cost, and speed. This page is an independent comparison view: it summarizes the per-task results into a weighted score without modifying the input data or replacing the benchmark's own reports.

## Version v2.1

Before reading the charts or building the page, it helps to know which dataset version is included and how it evolved.

Version v2.1 takes the v2.0 data and adds the GPT-6 Luna `xhigh` and `max` efforts (run in Codex) from the benchmark's phase-3 supplement, while keeping all other instances unchanged from v2.0. Because the supplement ran a day later, the served model or routing may have changed; as a result, each cell counts every valid run (5 to 8 per task), and the benchmark itself does not compare these two configurations with the others.

### v2.0

Underlying v2.1 is the v2.0 measurement, which was a complete redesign whose results are not comparable with v1:

- It evaluates a new set of models run through two agent harnesses: Codex 0.163.0 and Claude Code 2.1.303.
- It uses scoring r8.4: scores are not cut at 0 and can be negative; a model failure (no report) scores 0; and diagnostic scores count as is, with no 0.9 discount.
- Each configuration counts 5 runs per task (10 for the local Strata model), and the score charts show 95% confidence intervals.
- It adds task speeds and engine speeds (tok/s).
- Cost bases differ by vendor, and the local model uses a local running cost (see below).

Because of these changes, `build.py` supports v2.x data only (results file schema 1); the v1 page and script remain in the Git history.

## Scope

The benchmark tasks come from ARW, the software project that provides these development review tasks. In ARW's development process, a Reviewer is an AI agent that performs one specific code or document review task. The page combines four Reviewers, weighted by their share in the overall score:

| Reviewer | Work | Weight |
| --- | --- | ---: |
| Code Standards | Reviews code changes against repository instructions and implementation quality standards. | 20% |
| Code Spec | Checks whether code changes implement the supplied requirements accurately and completely. | 20% |
| Commit Audit | Audits a staged commit candidate: the selected files, required checks and coverage of the requirements. | 25% |
| Spec Readiness | Before implementation, checks whether requirement documents are complete, consistent, feasible and verifiable; each run has two independent review threads. | 35% |

Across those four tasks, the benchmark tests 29 configurations (27 main and 2 phase-3 supplement configurations):

| Harness | Models | Efforts | Cost basis |
| --- | --- | --- | --- |
| Codex | GPT-6.1 Sol | low, medium, high | Subscription run, reference API price |
| Codex | GPT-6 Luna | low, medium, high, xhigh, max (xhigh and max in the supplement) | Subscription run, reference API price |
| Codex | DeepSeek V4.1 Flash | low, high, max | DeepSeek price per request |
| Codex | Strata IQ3_XXS (local) | low, medium, high | Local running cost |
| Claude Code | Claude Opus 5.5, Sonnet 5.5, Haiku 5.5 | low, medium, high | Subscription run, reference API price |
| Claude Code | DeepSeek V4.1 Flash | low, high, max | DeepSeek price per request |
| Claude Code | Strata IQ3_XXS (local) | low, medium, high | Local running cost |

In this table, DeepSeek V4.1 Flash is the endpoint's `deepseek-flash` model (version DeepSeek-V4.1-Flash-1017), and Strata IQ3_XXS is a 3-bit quantization of Qwen3.8-Flash-Next run locally on a home PC (RTX 3080 Ti 12 GB, i9-13900, 64 GB RAM). Effort labels are each model's requested setting, not equal compute across models.

All runs took place from 2026-10-19 to 2026-10-22 (UTC), and the page counts 717 scored runs. When interpreting the results, keep three boundaries in mind:

- The tasks were calibrated on Claude Opus, which also judged the reports, so Opus may be placed too high.
- The results describe this fixed task set only and are not a general model ranking.
- The full scenarios, raw reports and hidden cases are not in this repository, so the charts can be recomputed from the snapshot, but the measurement cannot be rerun from it.

## Statistics

To turn those raw runs into the numbers plotted on the page, the build filters the snapshot and aggregates scores, resource usage, and speeds using the rules below.

### Counted runs

First, the page filters the snapshot so that it uses only the instances the benchmark counts in its main statistics (`selection.inMain` true and no `supplementaryNote`), plus the phase-3 supplement:

- Standard configurations count 5 runs per task, while Strata counts 10 per task.
- GPT-6 Luna xhigh and max are phase-3 supplement configurations (`kind` `phase3`); following the benchmark, every valid instance of each cell counts, giving 5 to 8 runs per task.
- DeepSeek runs requested as medium that the endpoint ran as high under the same time limit count as high, following the benchmark, so the two DeepSeek high cells in Commit Audit have 8 runs each.
- Invalid runs and the supplementary "requested as medium" configuration, which ran under a different time limit, are excluded.

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

Each run's seconds are the denominator of its own speed, which preserves the benchmark's two time bases: task speeds use work seconds (the speed a user perceives) and engine speeds use request or decode seconds (the model alone). On the token side, input speeds use non-cached input tokens and output speeds use output tokens. Because API models cannot separate input processing time from output decoding, their engine input speed is unknown and their engine output speed is a lower bound (≥); only the local Strata model has an engine input speed.

### Missing values

Finally, some runs lack a specific measurement. Missing values are never treated as zero: a run missing one measure is skipped for that measure only, and notes under the charts list the affected cells. The speed chart's note leaves out the engine input speed of API models, since that is unknown by design. Where a value is only partially captured—for example, DeepSeek costs that miss requests dropped by a time-limit reminder—it is marked with ≥ to indicate a lower bound.

## Cost

Among the metrics above, cost requires special handling because configurations ran under different billing methods—subscription plans, per-request API billing, and local hardware. Consequently, no cost on the page is an actual bill. Instead, prices were checked on **2026-10-22**, and the rules in `pricing.json` put each vendor on a defined cost basis:

| Vendor | Basis |
| --- | --- |
| OpenAI | Subscription run, reference API price: tokens × OpenAI Standard API rates |
| Anthropic | Subscription run, reference API price: the API-equivalent cost Claude Code reports (instance `cost.usd`) |
| DeepSeek | Instance `cost.usd`: official prices per request, peak or off-peak |
| Strata (local) | Local running cost: work seconds × hourly cost |

For OpenAI models, token counts are multiplied by these OpenAI Standard API rates (USD per million tokens):

| Model | Non-cached input | Cached input | Output |
| --- | ---: | ---: | ---: |
| [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) | $2 | $0.10 | $10 |
| [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) | $0.10 | $0.01 | $0.50 |

Cache-write tokens are not priced: `cacheWriteRate` in `pricing.json` is kept for reference only, and the build stops with an error if an OpenAI instance reports cache-write tokens.

For the local Strata model, the running cost is a rough estimate that covers electricity and upkeep during active work only, excluding hardware purchase, setup, and idle time between runs:

| Item | Value | Note |
| --- | ---: | --- |
| Wall power | 400 W | Rough whole-system load (350 W GPU board limit; memory-bound decoding usually draws less) |
| Electricity | $0.174 / kWh | Q1 2026 world household average, by country ([GlobalPetrolPrices](https://www.globalpetrolprices.com/electricity_prices/)) |
| Upkeep | $0.02 / hour | Fans, power supply and other wear parts, about $50 a year over about 2,500 loaded hours |
| Total | about $0.09 / hour | |

Because this local cost is always above 0, the logarithmic cost axis on the charts never meets 0. And because local runs are much slower than API runs, Strata works out to about $0.011–0.026 per task run, putting it in the same order of magnitude as GPT-6 Luna low.

## Files

Once you understand what the page shows and how its metrics are defined, you can inspect the repository or build the page yourself. The project contains these files:

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

Each file has a distinct role in turning the data snapshot into the finished page:

- **Code and rules**: `stats.py` holds the statistics and cost rules (pure Python, no Plotly), `build.py` draws the charts and assembles the page, `test_build.py` tests them, and `pricing.json` stores the pricing parameters.
- **Styles, fonts, and generated outputs**: `resources/site.css` is the page's only stylesheet, and `resources/fonts/` holds pre-downloaded fonts (see `resources/fonts/README.md` for font licenses and sources). `resources/favicon.svg` is generated by the script and kept in the repository, whereas `charts.html` is a generated local file and is not committed.
- **Data snapshot**: `benchmark-results.json` is an independent snapshot of the input data. The build reads only this committed snapshot; it does not read `.env` or sync data from other directories.

To update `benchmark-results.json` when new benchmark data is ready, a maintainer copies `.env.example` to the ignored `.env`, sets `BENCHMARK_SOURCE_RESULTS` to the absolute path of the trusted source file, and runs these Bash commands from the repository root to copy and verify the snapshot:

```bash
. ./.env
: "${BENCHMARK_SOURCE_RESULTS:?Set BENCHMARK_SOURCE_RESULTS in .env}"
cp -- "$BENCHMARK_SOURCE_RESULTS" benchmark-results.json
cmp -- "$BENCHMARK_SOURCE_RESULTS" benchmark-results.json
```

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
- **Pricing**: Prices and local cost settings live in `pricing.json`. Because the page's method text reads the prices, power, electricity rate, and weights directly from `pricing.json` and `REVIEWERS`, after any pricing change you must update `checkedAt`, rebuild the page, and update the cost tables in both READMEs.
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
