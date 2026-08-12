# Publish Partial OOLONG Codex Verdict Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the complete Codex integration and OOLONG benchmark in the existing fork, with a reproducible partial report that recommends direct Codex calls over RLM CLI for the measured configuration.

**Architecture:** Add a partial-report path to the benchmark instead of fabricating a full 25-case report. It scores only successful A/B pairs, preserves failures and missing cases as coverage evidence, and renders versioned JSON and Markdown. The root README links to the canonical benchmark report; the ADR and governance documents explain the product decision without duplicating the report's measurements.

**Tech Stack:** Python 3.11+, `uv`, `pytest`, `ruff`, existing `oolong_codex` CLI, Markdown, Git/GitHub.

## Global Constraints

- Publish in the existing `raphaelmarra/rlm` fork; retain `upstream` as `alexzhang13/rlm`.
- Do not version anything beneath `benchmarks/oolong_codex/artifacts/` except its `.gitignore`.
- The public conclusion applies only to `gpt-5.6-terra`, ChatGPT/Codex subscription, `LocalREPL`, OOLONG `trec_coarse` 131K, and the frozen benchmark configuration.
- State the observed coverage exactly: A completed 25/25; B has 8 successes, 1 failure, and 16 cases not started.
- Call/token/time comparisons use only the eight successful paired cases; report the failed B attempt separately.
- Do not claim a monetary cost: subscription usage has no per-token price.
- Run commands from `benchmarks/oolong_codex/`, or pass `--config benchmarks/oolong_codex/benchmark.toml` explicitly.

---

### Task 1: Implement partial-report aggregation and rendering

**Files:**
- Create: `benchmarks/oolong_codex/tests/test_partial_report.py`
- Modify: `benchmarks/oolong_codex/oolong_codex/report.py`

**Interfaces:**
- Consumes: `Sequence[CaseRecord]`, `Mapping[str, Sequence[RawResult]]`, and `BenchmarkConfig`.
- Produces: `build_partial_report(cases, results_by_arm, config) -> dict[str, Any]` and `partial_markdown(report) -> str`.
- Preserves: `build_report()` and `_markdown()` for complete benchmark reports.

- [ ] **Step 1: Write tests for pair selection, coverage, and failed attempts**

Create `test_partial_report.py` with two materialized cases and deterministic gold files. Give A a successful result for both cases; give B one successful result and one `failed` result. Assert the partial report contains one paired score, reports two planned cases, one B success, one B failure, zero B missing cases, and metrics for only the successful pair.

```python
report = build_partial_report(cases, {"A": baseline, "B": rlm}, config)

assert report["kind"] == "partial"
assert report["coverage"]["paired_succeeded"] == 1
assert report["coverage"]["arms"]["B"] == {
    "available": 2,
    "succeeded": 1,
    "failed": 1,
    "missing": 0,
}
assert report["metrics"]["A"]["calls"] == 1
assert report["metrics"]["B"]["calls"] == 3
assert report["attempt_metrics"]["B"]["failures"] == 1
```

Add a rendering assertion that `partial_markdown(report)` includes `# OOLONG Codex partial benchmark`, `Paired successful cases`, and `RLM failures`.

- [ ] **Step 2: Run the new test and confirm RED**

Run: `uv run --project benchmarks/oolong_codex pytest -q tests/test_partial_report.py`

Expected: FAIL because `build_partial_report` and `partial_markdown` do not exist.

- [ ] **Step 3: Add the minimal partial-report implementation**

In `report.py`, add a helper that indexes results by `case_id`, then select case IDs for which both A and B have `status == "succeeded"`. Reuse `score_arms()` and `build_report()` only on those selected cases and results. Return this exact top-level shape:

```python
{
    "kind": "partial",
    "coverage": {
        "planned_cases": len(cases),
        "paired_succeeded": len(paired_cases),
        "arms": {"A": arm_counts, "B": arm_counts},
    },
    "e2e": {"verdict": "partial", "errors": []},
    "quality": {**paired_report["quality"], "conclusive": False},
    "scores": paired_report["scores"],
    "paired_cases": paired_report["paired_cases"],
    "metrics": paired_report["metrics"],
    "attempt_metrics": _metrics(results_by_arm),
}
```

`arm_counts` must have exactly `available`, `succeeded`, `failed`, and `missing`; `missing` is `len(cases) - available`. `partial_markdown()` must render coverage, paired quality, paired metrics, attempt metrics, and every B failure with its case ID and error string. It must say that the quality sample is not conclusive and must not label the E2E benchmark as passed.

- [ ] **Step 4: Run the focused report tests and format the changed module**

Run: `uv run --project benchmarks/oolong_codex pytest -q tests/test_report.py tests/test_partial_report.py`

Run: `uv run --project benchmarks/oolong_codex ruff check oolong_codex/report.py tests/test_partial_report.py`

Run: `uv run --project benchmarks/oolong_codex ruff format --check oolong_codex/report.py tests/test_partial_report.py`

Expected: all commands exit 0.

- [ ] **Step 5: Commit the partial-report API**

```powershell
git add benchmarks/oolong_codex/oolong_codex/report.py benchmarks/oolong_codex/tests/test_partial_report.py
git commit -m "feat: add partial OOLONG report"
```

### Task 2: Expose partial reports through the benchmark CLI

**Files:**
- Create: `benchmarks/oolong_codex/tests/test_cli.py`
- Modify: `benchmarks/oolong_codex/oolong_codex/cli.py`

**Interfaces:**
- Consumes: existing materialized manifest, raw A/B JSON files, and `--report-id`.
- Produces: `oolong-codex partial-report --report-id <id>` that writes `<id>.json` and `<id>.md` in `benchmarks/oolong_codex/reports/`.
- Depends on: `build_partial_report()` and `partial_markdown()` from Task 1.

- [ ] **Step 1: Write the failing CLI integration test**

Build a temporary `benchmark.toml`, materialize two local cases, and write raw results with `write_json_atomic()`: two successful A results, one successful B result, and one failed B result. Invoke:

```python
exit_code = main(
    [
        "--config", str(config_path),
        "--report-id", "fixture-partial",
        "partial-report",
    ]
)
```

Assert `exit_code == 0`, `reports/fixture-partial.json` and `.md` exist next to the config, and the JSON has `kind == "partial"`, `coverage["paired_succeeded"] == 1`, and `e2e["verdict"] == "partial"`.

- [ ] **Step 2: Run the CLI test and confirm RED**

Run: `uv run --project benchmarks/oolong_codex pytest -q tests/test_cli.py`

Expected: FAIL because `partial-report` and `--report-id` are unrecognized.

- [ ] **Step 3: Implement one explicit partial-report command**

Extend `build_parser()` with `partial-report` and `--report-id`. Add `_load_available_results()` that iterates the frozen case order and loads only existing raw files; leave `_load_results()` strict for complete `score`, `report`, and `verify` commands. For `partial-report`, call `_load_available_results()`, `build_partial_report()`, and `partial_markdown()`; require a nonempty `--report-id`, write exactly:

```python
versioned_dir = arguments.config.resolve().parent / "reports"
write_json_atomic(versioned_dir / f"{arguments.report_id}.json", report)
_write_text_atomic(versioned_dir / f"{arguments.report_id}.md", partial_markdown(report))
```

Emit a successful command envelope with `e2e: "partial"`; generating a truthful partial report is command success even when the benchmark itself did not complete.

- [ ] **Step 4: Run the CLI and complete benchmark test suites**

Run: `uv run --project benchmarks/oolong_codex pytest -q tests/test_cli.py tests/test_report.py tests/test_partial_report.py`

Run: `uv run --project benchmarks/oolong_codex pytest -q`

Expected: all tests pass.

- [ ] **Step 5: Commit the CLI surface**

```powershell
git add benchmarks/oolong_codex/oolong_codex/cli.py benchmarks/oolong_codex/tests/test_cli.py
git commit -m "feat: expose partial OOLONG report"
```

### Task 3: Generate evidence and publish the fork narrative

**Files:**
- Create: `benchmarks/oolong_codex/reports/2026-08-12-partial-verdict.json`
- Create: `benchmarks/oolong_codex/reports/2026-08-12-partial-verdict.md`
- Create: `docs/decisions/0005-nao-recomendar-rlm-cli-codex-no-cenario-oolong.md`
- Modify: `README.md`
- Modify: `benchmarks/oolong_codex/README.md`
- Modify: `docs/INDEX.md`
- Modify: `docs/STRUCTURE.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/DECISOES.md`

**Interfaces:**
- Consumes: the durable raw A/B results under ignored `artifacts/` and the Task 2 CLI.
- Produces: a committed report, a discoverable root link, and synchronized governance.

- [ ] **Step 1: Generate the canonical report from the saved attempts**

Run from `benchmarks/oolong_codex/`:

```powershell
uv run oolong-codex --report-id 2026-08-12-partial-verdict partial-report
```

Read the generated JSON and Markdown. Confirm the report records exactly eight successful pairs, one failed B attempt, sixteen B cases missing, the eight-pair resource totals, and no monetary total.

- [ ] **Step 2: Write the root and benchmark reader paths**

Add a concise callout after the root README overview with a link to the canonical Markdown report. It must say that the fork's measured configuration does not justify RLM as a generic CLI layer over Codex and that direct Codex calls are recommended for this scenario.

Replace the benchmark README command block with a working `Push-Location benchmarks/oolong_codex` / `Pop-Location` workflow. Include the normal full commands, the partial-report command above, and a link to the canonical report. State that only `run` consumes the subscription and that `artifacts/` is intentionally excluded from version control.

- [ ] **Step 3: Record the decision and synchronize governance**

Create ADR 0005 with `status: accepted`, the measured configuration, the partial coverage, the decision not to recommend generic RLM CLI use, and links to the canonical report and benchmark spec. Add ADR 0005 to `DECISOES.md` and `INDEX.md`.

Mark roadmap stages 8 and 9 `Concluída`, with gate text that says the benchmark ended partial after the observed resource penalty and points to the report. Add the published partial benchmark and its resource totals to `CHANGELOG.md`. Add the reports directory to `STRUCTURE.md`; do not copy report tables into any governance file.

- [ ] **Step 4: Verify publication boundaries before staging**

Run: `git check-ignore -v benchmarks/oolong_codex/artifacts/raw/A/17000213.json`

Run: `git check-ignore -v benchmarks/oolong_codex/artifacts/dataset/manifest.json`

Run: `git status --short`

Expected: both artifact paths are ignored; the status lists benchmark source, tests, reports, and intended documentation only.

- [ ] **Step 5: Commit the benchmark, evidence, and documentation**

```powershell
git add README.md benchmarks/oolong_codex docs
git commit -m "docs: publish partial OOLONG Codex verdict"
```

### Task 4: Verify the complete fork and publish it to origin/main

**Files:**
- Modify: no source files expected

**Interfaces:**
- Consumes: all commits through Task 3 and remote `origin/main`.
- Produces: a verified fast-forward publication of the complete fork on its default branch.

- [ ] **Step 1: Run fresh benchmark and repository checks**

Run: `uv run --project benchmarks/oolong_codex pytest -q`

Run: `uv run --project benchmarks/oolong_codex ruff check .`

Run: `uv run --project benchmarks/oolong_codex ruff format --check .`

Run: `uv run pytest -q`

Run: `uv run ruff check .`

Run: `uv run ruff format --check .`

Run: `uv run pre-commit run --all-files`

Expected: every command exits 0.

- [ ] **Step 2: Verify the exact publication diff**

Run: `git diff --check origin/main...HEAD`

Run: `git status --short`

Run: `git merge-base --is-ancestor origin/main HEAD`

Expected: no whitespace errors, a clean worktree, and exit 0 from the ancestry check.

- [ ] **Step 3: Publish the complete fork default branch**

Run: `git push origin HEAD:main`

Run: `git ls-remote --heads origin main`

Expected: the remote `main` SHA equals local `HEAD`; the fork's default branch contains the Codex integration, benchmark code, partial report, and verdict.
