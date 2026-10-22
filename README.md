# Reviewer Model Benchmark Page Builder

English · **[简体中文](README.zh-CN.md)**

[Open the published benchmark page](https://cybersoul.net/reviewer-model-benchmark/)

This tool reads `benchmark-results.json` (a snapshot of the benchmark's per-run results) and builds `charts.html`, an offline page that compares models, agent harnesses and reasoning efforts on four reviewer tasks by score, work time, token usage, cost and speed. The page shows the weighted score first, then three trade-off scatter plots (with an optional Pareto front), then per-task score, time, token, cost and speed detail.

The page is an independent comparison view. It does not change the input data or replace the benchmark's own reports; those give per-task results only, and the weighted score is this page's summary of them.

## Version v2.0

v2.0 is a new measurement, and its results are not comparable with v1:

- A new set of models, run through two agent harnesses: Codex 0.163.0 and Claude Code 2.1.303.
- Scoring r8.4: scores are not cut at 0 and can be negative; a model failure (no report) scores 0; diagnostic scores count as is, with no 0.9 discount.
- Each configuration counts 5 runs per task (10 for the local Strata model), and score charts show 95% confidence intervals.
- New task and engine speeds (tok/s).
- Cost bases differ by vendor, and the local model uses a local running cost (see below).

`build.py` supports v2.0 data only; the v1 page and script remain in the Git history.

## Scope

ARW is the software project that provides these development review tasks. A Reviewer is an AI agent that performs one code or document review task in ARW's development process.

| Reviewer | Work | Weight |
| --- | --- | ---: |
| Code Standards | Reviews code changes against repository instructions and implementation quality standards. | 20% |
| Code Spec | Checks whether code changes implement the supplied requirements accurately and completely. | 20% |
| Commit Audit | Audits a staged commit candidate: the selected files, required checks and coverage of the requirements. | 25% |
| Spec Readiness | Before implementation, checks whether requirement documents are complete, consistent, feasible and verifiable; each run has two independent review threads. | 35% |

There are 27 main configurations:

| Harness | Models | Efforts | Cost basis |
| --- | --- | --- | --- |
| Codex | GPT-6.1 Sol, GPT-6 Luna | low, medium, high | Subscription run, reference API price |
| Codex | DeepSeek V4.1 Flash | low, high, max | DeepSeek price per request |
| Codex | Strata IQ3_XXS (local) | low, medium, high | Local running cost |
| Claude Code | Claude Opus 5.5, Sonnet 5.5, Haiku 5.5 | low, medium, high | Subscription run, reference API price |
| Claude Code | DeepSeek V4.1 Flash | low, high, max | DeepSeek price per request |
| Claude Code | Strata IQ3_XXS (local) | low, medium, high | Local running cost |

The runs took place from 2026-10-19 to 2026-10-22 (UTC), and the page counts 666 scored runs. Effort labels are each model's requested setting, not equal compute. The tasks were calibrated on Claude Opus, which also judged the reports, so Opus may be placed too high. The results describe this fixed task set only and are not a general model ranking. The full scenarios, raw reports and hidden cases are not in this repository, so the charts can be recomputed from the snapshot but the measurement cannot be rerun from it.

Strata IQ3_XXS is a 3-bit quantization of Qwen3.8-Flash-Next, run locally on a home PC (RTX 3080 Ti 12 GB, i9-13900, 64 GB RAM).

## Statistics

### Counted runs

The page uses only the instances the benchmark counts in its main statistics (`selection.inMain` true and no `supplementaryNote`): 10 per task for Strata and 5 for other configurations. DeepSeek runs requested as medium that the endpoint ran as high under the same time limit count as high, following the benchmark, so the two DeepSeek high cells in Commit Audit have 8 runs each. Invalid runs and the supplementary "requested as medium" configuration, which ran under a different time limit, are excluded.

### Scores

A run's score (r8.4) credits the answer-key problems a report finds and deducts its false findings, without a cut at 0. A task score is the mean of the cell's runs, with a 95% interval from the t distribution (half-width = t₀.₉₇₅,ₙ₋₁ × SD / √n). The weighted score is:

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

Time, tokens and cost average every counted run, including zero-score and model-failure runs, which still used resources. A task's value is the mean over its runs with data; a configuration's value is the arithmetic mean of its four task values. Time is work seconds, excluding setup and loading: Codex counts the agent's accumulated work time and Claude Code the session's wall time; Spec Readiness adds its two threads.

### Speed

A speed is always total tokens divided by total seconds, never a mean of per-run speeds:

- A task's speed = the sum of its runs' tokens ÷ the sum of their seconds.
- A configuration's speed = the tokens of one average run of each task, summed ÷ their seconds, summed.

Each run's seconds are the denominator of its own speed, which keeps the benchmark's time basis: task speeds use work seconds (the speed a user perceives) and engine speeds use request or decode seconds (the model alone). Input speeds use non-cached input tokens and output speeds output tokens. API models cannot separate input processing, so their engine input speed is unknown and their engine output speed is a lower bound (≥); only Strata has an engine input speed.

### Missing values

Missing values are not zero: a run missing one measure is skipped for that measure only, and notes under the charts list the affected cells. Values marked ≥ are lower bounds, for example DeepSeek costs that miss requests dropped by a time-limit reminder.

## Cost

No cost is an actual bill. Prices were checked on **2026-10-22**, and the rules live in `pricing.json`.

| Vendor | Basis |
| --- | --- |
| OpenAI | Subscription run, reference API price: tokens × OpenAI Standard API rates |
| Anthropic | Subscription run, reference API price: the API-equivalent cost Claude Code reports (instance `cost.usd`) |
| DeepSeek | Instance `cost.usd`: official prices per request, peak or off-peak |
| Strata (local) | Local running cost: work seconds × hourly cost |

OpenAI rates (USD per million tokens):

| Model | Non-cached input | Cached input | Output |
| --- | ---: | ---: | ---: |
| [GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol) | $2 | $0.10 | $10 |
| [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna) | $0.10 | $0.01 | $0.50 |

The local running cost covers electricity and upkeep only, excluding hardware purchase, setup and idle time between runs, and is a rough estimate:

| Item | Value | Note |
| --- | ---: | --- |
| Wall power | 400 W | Rough whole-system load (350 W GPU board limit; memory-bound decoding usually draws less) |
| Electricity | $0.174 / kWh | Q1 2026 world household average, by country ([GlobalPetrolPrices](https://www.globalpetrolprices.com/electricity_prices/)) |
| Upkeep | $0.02 / hour | Fans, power supply and other wear parts, about $50 a year over about 2,500 loaded hours |
| Total | about $0.09 / hour | |

The local cost is always above 0, so the log cost axis never meets 0. Because local runs are much slower than API runs, Strata costs about $0.011–0.026 per task run, the same order as GPT-6 Luna low.

## Files

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

`benchmark-results.json` is an independent snapshot of the input data. To update it, a maintainer copies `.env.example` to the ignored `.env` and sets `BENCHMARK_SOURCE_RESULTS` to the absolute path of the trusted source file. The build reads only the committed snapshot; it does not read `.env` or sync data from other directories. `charts.html` is a generated local file and is not committed; `resources/favicon.svg` is also generated but kept in the repository. `resources/site.css` and `resources/fonts/` are pre-downloaded page assets; see `resources/fonts/README.md` for font licenses and sources.

Copy and check a new snapshot with Bash from the repository root:

```bash
. ./.env
: "${BENCHMARK_SOURCE_RESULTS:?Set BENCHMARK_SOURCE_RESULTS in .env}"
cp -- "$BENCHMARK_SOURCE_RESULTS" benchmark-results.json
cmp -- "$BENCHMARK_SOURCE_RESULTS" benchmark-results.json
```

## Usage

Building the page needs Python and Plotly; it has been checked with Python 3.14 and Plotly 6.9.0. Run these commands in this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install plotly==6.9.0
.venv/bin/python test_build.py
.venv/bin/python build.py
```

If the system Python lacks `venv` or `pip`, use [uv](https://docs.astral.sh/uv/) instead: `uv venv .venv`, then `uv pip install --python .venv/bin/python plotly==6.9.0`. On Windows, use `py -m venv .venv` and `.venv\Scripts\python`.

By default the script reads `benchmark-results.json` next to it and overwrites `charts.html` there; other paths can be given:

```bash
.venv/bin/python build.py path/to/benchmark-results.json path/to/charts.html
```

The page loads `resources/` by relative path, so another output directory needs its own `resources/`. Open `charts.html` directly in a browser; viewing it needs no Python, network or web server. The footer's "Updated" date is the build date, not the measurement or price-check date.

## Implementation and maintenance

`build.py` reads the JSON and computes the measures in Python, including a pure-Python t-distribution quantile; Plotly draws the charts, which are embedded in the HTML. Page text and chart axes switch between English and Chinese, and chart interaction runs locally in the browser.

Model order and colors, harnesses, the four reviewer weights and the scoring version are defined at the top of `build.py`. Prices and local cost settings live in `pricing.json`; after a change, update `checkedAt`, rebuild the page and update the cost tables in both READMEs. Agree any change to the statistics rules first, as `AGENTS.md` describes, and update both READMEs afterwards.

This tool does not run the benchmark or modify the input JSON.

## Publishing

Cloudflare Pages is connected to this GitHub repository and builds the page from the `master` branch with Python 3.12 and Plotly 6.9.0, into the `_site` output directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install plotly==6.9.0
mkdir -p _site/reviewer-model-benchmark/resources
cp -R resources/. _site/reviewer-model-benchmark/resources/
.venv/bin/python build.py benchmark-results.json _site/reviewer-model-benchmark/index.html
```

Page assets use relative paths, so the page works under that subpath. The local `charts.html` and `_site/` are not committed. The custom domain is configured outside the repository.
