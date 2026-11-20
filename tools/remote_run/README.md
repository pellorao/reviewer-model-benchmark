# remote_run: run the Reviewer benchmark with a command-line model, on any machine

This tool lets a machine that has its own model CLI (for example `agy -p` with its own account) run the Reviewer capability
suite, and hand the results back as one file that the benchmark owner imports and judges. The questions, answer keys and
scoring stay in ARW and are used unchanged; this script only replaces the part of ARW's `run` that needs ARW's own
background-agent daemon (which has no provider for your CLI).

If you are an agent asked to do this run: follow "Steps" below in order, change nothing under the ARW checkout, and
report the command output where a step says so. If a step fails, stop and report the output instead of working around it.

## What you need

- Python 3.9+ (standard library only), Node.js 24+, and Git on `PATH`. Tested on Linux; on Windows use WSL, because ARW's scenario
  setup is POSIX-style.
- The model CLI, logged in with the account that should be measured.
- Two checkouts: this repository, and ARW at the pinned commit (`pin.json` in this folder names it; the script refuses any other).

## Steps

1. Get the code (no ARW install is needed, only the checkout):

   ```
   git clone https://github.com/pellorao/reviewer-model-benchmark.git
   git clone https://github.com/Tranzvision/agent-repository-workflow.git arw
   git -C arw checkout "$(python3 -c "import json;print(json.load(open('reviewer-model-benchmark/tools/remote_run/pin.json'))['arw_commit'])")"
   ```

2. Copy `config.example.json` and adapt it (see "Config"). Use the real model names of your account; the example is for `agy`.
   Put the work directory (`--work`) on a short path that does not name the model or you, for example `/tmp/rbwork`: the path
   appears in the prompt and the model quotes it in its reports.

3. Check everything, including one real model call (one tiny prompt, a few tokens):

   ```
   python3 reviewer-model-benchmark/tools/remote_run/remote_run.py check --arw arw --config my.json \
     --model hydrogen --efforts high --out rbout --work /tmp/rbwork --call
   ```

   It must print `matches the pin`, `setup ...: succeeded` for four scenarios, and `call: exit 0` with a sensible answer.
   If the model command fails, fix `my.json` until this passes.

4. Smoke run: one instance, then look at the result.

   ```
   python3 .../remote_run.py run --arw arw --config my.json --model hydrogen --efforts high \
     --scenarios code-spec --n 1 --out rbout --work /tmp/rbwork
   ```

   `rbout/runs/hydrogen-high-code-spec-r1/` must exist, and `run.json` should say `"valid": true`. Report the wall time and
   the token numbers if the command printed them. If the instance came out void, read `rbout/voids/*/command-output.txt`.

5. Full run. `plan` shows the expected usage first (it also prints at the start of `run`); the full matrix is
   4 scenarios x each effort x 5 rounds, one model call per instance, each up to 60 minutes:

   ```
   python3 .../remote_run.py plan --arw arw --config my.json --model hydrogen --efforts low,medium,high,xhigh --out rbout --work /tmp/rbwork
   python3 .../remote_run.py run  --arw arw --config my.json --model hydrogen --efforts low,medium,high,xhigh --out rbout --work /tmp/rbwork
   ```

   The run can be interrupted (Ctrl-C) and started again with the same command: finished instances are skipped. Create the
   file `rbout/STOP` to stop cleanly before the next instance. Run one model at a time with one process; run another model
   after this one ends, with its own `--model` and the same `--out`.

6. Pack and send back:

   ```
   python3 .../remote_run.py pack --out rbout
   ```

   It prints the path of `rbout/bundle-<time>.tar.gz` (a few MB). Hand that one file back. It holds only the scores,
   reports and run records; no credentials or logs of your CLI. If it warns about the home directory path, that path appears
   inside some model reports and is harmless to the import.

## Config (`my.json`)

| Key | Meaning |
|---|---|
| `command` | The model call as an argument list (no shell). It runs inside the instance directory. |
| `provider` | Written to `settings.modelProvider` (default `agy`). |
| `version_command` | Optional; its first output line is recorded as the harness version. |
| `files` | Optional side files (name -> text, or a JSON object) written next to the prompt, outside the instance, with placeholders filled; reach one with `{file.<name>}` (the example builds the CLI's permission settings this way). |
| `env` | Extra environment variables. |

Placeholders: `{prompt}` (the whole prompt as one argument; a very long argument can exceed an OS limit), `{prompt_file}`
(the prompt in a file; tell the model to read it, as the example does), `{cwd}` (the instance, a Git repository to review),
`{report_path}`, `{report_dir}` (where the model must write its review), `{model}`, `{model_id}`, `{effort}`, `{scenario}`.
With neither `{prompt}` nor `{prompt_file}` in the command, the prompt is sent on standard input. The command also gets the
environment variables `RB_REPORT_PATH`, `RB_CWD`, `RB_PROMPT_FILE`, `RB_MODEL`, `RB_EFFORT`, `RB_SCENARIO`.

The model must write its review to `{report_path}` (the prompt says so). An exit code is not checked: an instance counts as
delivered when the report file exists and is not empty. If the command prints JSON with a `usage` object
(`input_tokens`, `cache_read_tokens`, `output_tokens`), the token counts are recorded.

## Isolation (read this)

The answer keys are in the ARW checkout. ARW's own runner keeps the reviewer from reading them with a sandbox and checks the
session record afterwards; neither exists for another CLI. So the config must confine the model: it may read the instance
directory (`{cwd}`) and the prompt file, may write only the report directory, and nothing else. The example does this with
`agy` permission settings and `--sandbox`; check that your CLI enforces it. As a net the script also voids an instance
whose command output or report mentions the ARW checkout path or `tests/fixtures/reviewer-capability` (`inspect-flags`).
That scan is weak: it cannot see files the model read silently.

## What differs from ARW's own run

- The role instructions and the task text are one prompt (`PROMPT_TEMPLATE` in the script), not a system prompt plus a message.
- No ARW `inspect` (see above); each `driver.json` records `"inspection": "portable-scan"`.
- No pause notices (the pause deduction is 0), and token counts exist only when the command prints them.
- `time.durationSeconds` is the command's wall time (`durationEstimated: true`).
- Instance ids are random (`i-<12 hex>`), so a candidate's id does not name the model; the cell (`<model>-<effort>-<scenario>-r<n>`)
  is the directory name and `driver.json` `id`.
- A run past the limit (default 3600 s) is stopped and scored as it stands, not rerun; no report means 0. A void instance
  (no report, answer-key location seen) is rerun at the end of the run, up to 8 attempts per cell.

## Stops and the usage watch

Before it starts, `run` prints the expected number of calls and model time. After every call it compares the actual with that.
It stops itself, writes `rbout/STOPPED.json` and exits 75 when the calls pass twice the expected number, the model time passes
twice the expected, or one call prints more than 300000 output tokens. It exits 3 after two void attempts in a row
(three for `no-completion`) or three failed ones (ARW refused the report, for example). Find the cause in
`rbout/events.log`, `rbout/attempts.jsonl` and `rbout/voids/`, then continue with `run ... --ack "<what you checked>"`.
The tunables are at the top of `remote_run.py`.

## Importing a bundle (benchmark owner)

```
python3 tools/remote_run/remote_run.py import bundle-....tar.gz --runs-dir <.../v2/data/runs> [--dry-run] [--replace]
```

It reads the bundle in memory (only expected file names), checks the manifest hashes, that every `run.json` carries the pinned
ARW commit and fixture tree, that no instance id collides with an existing one, and that no existing cell is overwritten
(unless `--replace`). It rewrites each `run.json` `report` / `repair` to the unpacked copies, in the layout the local driver
writes. Judging the late candidates is then a new pool with the existing decision store (`pool build ... --decisions`), as
for any arm that finishes after the others.

## Files

`remote_run.py` (the tool), `pin.json` (the ARW commit and fixture tree it accepts), `config.example.json`, `fake_model.py`
(a stand-in command that copies a given file to the report path, for trying the flow without a model),
`test_remote_run.py` (`python -m unittest tools.remote_run.test_remote_run` from the repository root; set `RB_ARW_DIR` to
an ARW checkout at the pin to include the end-to-end case).
