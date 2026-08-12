# OOLONG Codex Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and execute an isolated, resumable 25-case OOLONG benchmark comparing direct Codex with depth-1 RLM Codex and producing deterministic quality and E2E reports.

**Architecture:** A nested `uv` project owns benchmark-only dependencies, configuration, cached official data, raw outputs, scoring, and reports. Preparation pins and materializes 25 official `trec_coarse` cases; two sequential runners write atomic per-case artifacts; a treatment-blind scorer and a separate reporter aggregate paired quality and operational telemetry.

**Tech Stack:** Python 3.11+, `uv`, `datasets>=4.0`, `python-dateutil`, `psutil`, `pytest`, `CodexClient`, and the global `rlm-codex` JSON CLI.

## Global Constraints

- Use official dataset revision `f0d59eaf0febf130664cfceb710436c8e3216b2b`.
- Select `validation`, `trec_coarse`, `context_len == 131072`, 25 cases, seed 42.
- Use `gpt-5.6-terra`, reasoning effort `medium`, depth 1, 12 iterations, and 1,800 seconds per case.
- Keep `OPENAI_API_KEY` unset and use ChatGPT subscription authentication only.
- Execute candidate code with `LocalREPL`; no Docker, WSL, or MCP.
- Run cases sequentially and never silently duplicate a terminal attempt.
- Keep cache, corpus, gold answers, checkpoints, and raw outputs under ignored `artifacts/`.
- Treat `total_cost == null` as unavailable, never as zero.
- Score before revealing A/B assignment; preserve raw outputs.
- Material gain requires mean paired delta at least `+0.10` and paired 95% bootstrap lower bound above zero.

---

### Task 1: Isolated project, configuration, and storage contracts

**Files:**
- Create: `benchmarks/oolong_codex/pyproject.toml`
- Create: `benchmarks/oolong_codex/benchmark.toml`
- Create: `benchmarks/oolong_codex/README.md`
- Create: `benchmarks/oolong_codex/oolong_codex/__init__.py`
- Create: `benchmarks/oolong_codex/oolong_codex/__main__.py`
- Create: `benchmarks/oolong_codex/oolong_codex/config.py`
- Create: `benchmarks/oolong_codex/oolong_codex/models.py`
- Create: `benchmarks/oolong_codex/oolong_codex/storage.py`
- Create: `benchmarks/oolong_codex/artifacts/.gitignore`
- Test: `benchmarks/oolong_codex/tests/test_config.py`
- Test: `benchmarks/oolong_codex/tests/test_storage.py`

**Interfaces:**
- Produces: `BenchmarkConfig`, `BenchmarkPaths`, `CaseRecord`, `RawResult`, `load_config(path)`, `read_json(path)`, and `write_json_atomic(path, value)`.
- Consumes: no benchmark code from later tasks.

- [ ] **Step 1: Write failing configuration and atomic-storage tests**

```python
def test_load_config_resolves_artifacts_relative_to_project(tmp_path: Path) -> None:
    config_path = tmp_path / "benchmark.toml"
    config_path.write_text(VALID_CONFIG, encoding="utf-8")
    config = load_config(config_path)
    assert config.num_cases == 25
    assert config.dataset_revision == "f0d59eaf0febf130664cfceb710436c8e3216b2b"
    assert config.artifacts_dir == tmp_path / "artifacts"


def test_atomic_json_never_leaves_temporary_file(tmp_path: Path) -> None:
    target = tmp_path / "result.json"
    write_json_atomic(target, {"response": "ok"})
    assert read_json(target) == {"response": "ok"}
    assert list(tmp_path.iterdir()) == [target]
```

- [ ] **Step 2: Run tests and verify RED**

Run: `uv run --project benchmarks/oolong_codex pytest tests/test_config.py tests/test_storage.py -q`

Expected: collection fails because `oolong_codex.config` and `oolong_codex.storage` do not exist.

- [ ] **Step 3: Implement the minimal contracts and nested project**

Use frozen dataclasses and fail-loud validation. `BenchmarkConfig` contains the dataset filters, model limits, bootstrap settings, arm assignment and resolved artifact path. `BenchmarkPaths` derives dataset, raw, attempt, score and report paths. `CaseRecord` contains `id`, `context_path`, `question_path`, `gold_path`, `context_sha256`, and `question_sha256`. `RawResult` contains `case_id`, `arm`, `response`, `status`, `wall_seconds`, token/call fields, optional `run_id`, optional worker PID fields, metadata and error. `benchmark.toml` must contain the exact global constants, opaque arms `A` and `B`, and `artifacts_dir = "artifacts"`. `write_json_atomic` writes UTF-8 JSON to a sibling temporary file, flushes, calls `os.fsync`, and replaces the target with `Path.replace`.

- [ ] **Step 4: Run the isolated tests and format checks**

Run: `uv run --project benchmarks/oolong_codex pytest tests/test_config.py tests/test_storage.py -q`

Expected: PASS.

Run: `uv run --project benchmarks/oolong_codex ruff check .`

Run: `uv run --project benchmarks/oolong_codex ruff format --check .`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add benchmarks/oolong_codex
git commit -m "feat: scaffold isolated OOLONG benchmark"
```

### Task 2: Official upstream scorer and paired statistics

**Files:**
- Create: `benchmarks/oolong_codex/oolong_codex/scorer.py`
- Test: `benchmarks/oolong_codex/tests/test_scorer.py`

**Interfaces:**
- Produces: `parse_answer(output: str) -> str`, `score_answer(gold: str, answer_type: str, output: str) -> float`, and `paired_bootstrap(deltas: Sequence[float], samples: int, seed: int) -> tuple[float, float]`.
- Consumes: standard library and `python-dateutil` only.

- [ ] **Step 1: Write failing literal scorer tests**

```python
@pytest.mark.parametrize(
    ("gold", "answer_type", "output", "expected"),
    [
        ("['entity']", "ANSWER_TYPE.LABEL", "Label: entity", 1.0),
        ("[10]", "ANSWER_TYPE.NUMERIC", "Answer: 12", 0.5625),
        ("[10]", "ANSWER_TYPE.NUMERIC", "Answer: 15", 0.2373046875),
        ("['more common than']", "ANSWER_TYPE.LABEL", "more common than", 1.0),
    ],
)
def test_score_answer_matches_upstream_literals(gold, answer_type, output, expected):
    assert score_answer(gold, answer_type, output) == expected


def test_paired_bootstrap_of_uniform_gain_has_exact_interval() -> None:
    assert paired_bootstrap([0.25] * 25, samples=1_000, seed=42) == (0.25, 0.25)
```

- [ ] **Step 2: Run scorer tests and verify RED**

Run: `uv run --project benchmarks/oolong_codex pytest tests/test_scorer.py -q`

Expected: FAIL because scorer functions are missing.

- [ ] **Step 3: Port the upstream parsing and scoring behavior**

Copy `_find_comparison_phrase`, `_attempt_answer_parse`, and `_synth_score` behavior from `upstream/main:training/environments/oolong/oolong/env.py`, retaining attribution in the module docstring. Implement bootstrap with `random.Random(seed).choices`, sorted sample means, and 2.5/97.5 percentiles.

- [ ] **Step 4: Run scorer tests and verify GREEN**

Run: `uv run --project benchmarks/oolong_codex pytest tests/test_scorer.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add benchmarks/oolong_codex/oolong_codex/scorer.py benchmarks/oolong_codex/tests/test_scorer.py
git commit -m "feat: port official OOLONG scoring"
```

### Task 3: Pin and materialize 25 official OOLONG cases

**Files:**
- Create: `benchmarks/oolong_codex/oolong_codex/dataset.py`
- Test: `benchmarks/oolong_codex/tests/test_dataset.py`

**Interfaces:**
- Consumes: `BenchmarkConfig`, `BenchmarkPaths`, `CaseRecord`, `write_json_atomic`.
- Produces: `select_rows(rows, config) -> list[dict[str, Any]]`, `build_root_prompt(question: str) -> str`, `materialize_rows(rows, config, paths) -> list[CaseRecord]`, `materialize_dataset(config, paths) -> list[CaseRecord]`, and `load_cases(paths) -> list[CaseRecord]`.

- [ ] **Step 1: Write failing selection and leakage tests**

```python
def test_select_rows_filters_then_deterministically_selects_25() -> None:
    selected = select_rows(SYNTHETIC_ROWS, CONFIG)
    assert len(selected) == 25
    assert [row["id"] for row in selected] == EXPECTED_IDS


def test_materialized_prompt_does_not_contain_gold(tmp_path: Path) -> None:
    cases = materialize_rows([OFFICIAL_SHAPED_ROW], CONFIG_ONE, BenchmarkPaths(tmp_path))
    prompt = cases[0].question_path.read_text(encoding="utf-8")
    gold = json.loads(cases[0].gold_path.read_text(encoding="utf-8"))["answer"]
    assert gold not in prompt
```

The synthetic fixture must mirror every official row field: `id`, `context_len`, `dataset`, `context_window_text`, `question`, `task_group`, `task`, `answer`, `answer_type`, `input_subset`, `num_labels`, and `context_window_id`.

- [ ] **Step 2: Run dataset tests and verify RED**

Run: `uv run --project benchmarks/oolong_codex pytest tests/test_dataset.py -q`

Expected: FAIL because dataset functions are missing.

- [ ] **Step 3: Implement official loading and materialization**

Use:

```python
stream = load_dataset(
    "oolongbench/oolong-synth",
    split=config.dataset_split,
    revision=config.dataset_revision,
    streaming=True,
).shuffle(seed=config.seed, buffer_size=10_000)
```

Filter `dataset` and `context_len`, stop at exactly 25, and fail if exhausted early. Write `context.txt`, `question.txt`, separate `gold.json`, and a gold-free manifest containing case IDs and SHA-256 hashes. Set `HF_HOME` to `artifacts/cache/huggingface` only for this benchmark process.

- [ ] **Step 4: Run dataset tests and verify GREEN**

Run: `uv run --project benchmarks/oolong_codex pytest tests/test_dataset.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add benchmarks/oolong_codex/oolong_codex/dataset.py benchmarks/oolong_codex/tests/test_dataset.py
git commit -m "feat: prepare pinned OOLONG cases"
```

### Task 4: Direct baseline and durable RLM runners

**Files:**
- Create: `benchmarks/oolong_codex/oolong_codex/runner.py`
- Test: `benchmarks/oolong_codex/tests/test_runner.py`

**Interfaces:**
- Consumes: config, case files, `CodexClient`, `rlm-codex` JSON envelopes, `psutil.pid_exists`, and atomic storage.
- Produces: `run_baseline_case(case, config, client_factory=CodexClient) -> RawResult`, `run_rlm_case(case, config, paths, cli_invoker=invoke_cli) -> RawResult`, and `run_arm(method, cases, config, paths) -> list[RawResult]`.

- [ ] **Step 1: Write failing baseline contract test**

```python
def test_baseline_uses_context_without_gold_and_records_usage(case, config) -> None:
    result = run_baseline_case(case, config, client_factory=RecordingClient)
    assert result.response == "Answer: 7"
    assert "gold-secret" not in RecordingClient.prompt
    assert case.context_path.read_text(encoding="utf-8") in RecordingClient.prompt
    assert result.input_tokens == 101
    assert result.output_tokens == 4
    assert result.total_cost is None
```

- [ ] **Step 2: Write failing durable RLM resume test**

```python
def test_rlm_resume_reuses_saved_run_id_without_second_start(case, config, paths) -> None:
    write_json_atomic(paths.attempt_path("A", case.id), {"run_id": "run-7", "pid": 991})
    invoker = RecordingInvoker(result=SUCCEEDED_RESULT, status=TERMINAL_STATUS)
    result = run_rlm_case(case, config, paths, cli_invoker=invoker)
    assert [call[0] for call in invoker.calls] == ["result", "status"]
    assert result.run_id == "run-7"
```

- [ ] **Step 3: Run runner tests and verify RED**

Run: `uv run --project benchmarks/oolong_codex pytest tests/test_runner.py -q`

Expected: FAIL because runner functions are missing.

- [ ] **Step 4: Implement minimal sequential runners**

The baseline creates a fresh `CodexClient` per case with the frozen model, effort, and timeout. The RLM runner resolves `rlm-codex` from `PATH`, persists `run_id` and initial PID immediately after `start`, then calls `result --wait --wait-timeout 1800` and `status`. It stores the complete CLI result, status, wall time, context hash, original PID liveness, metadata call count, and usage. Existing terminal raw results are skipped; incomplete candidates resume the saved run ID.

- [ ] **Step 5: Run runner tests and verify GREEN**

Run: `uv run --project benchmarks/oolong_codex pytest tests/test_runner.py -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add benchmarks/oolong_codex/oolong_codex/runner.py benchmarks/oolong_codex/tests/test_runner.py
git commit -m "feat: run direct and RLM benchmark arms"
```

### Task 5: Blind scoring, reports, verification, and CLI

**Files:**
- Create: `benchmarks/oolong_codex/oolong_codex/report.py`
- Create: `benchmarks/oolong_codex/oolong_codex/cli.py`
- Test: `benchmarks/oolong_codex/tests/test_report.py`
- Test: `benchmarks/oolong_codex/tests/test_cli.py`

**Interfaces:**
- Consumes: materialized cases, raw results, scorer, arm assignment, RLM metadata and PIDs.
- Produces: `score_arms(...) -> dict[str, Any]`, `build_report(...) -> dict[str, Any]`, `verify_e2e(...) -> list[str]`, `Services` dependency bundle, `main(argv=None, *, services=None) -> int`, and CLI commands `prepare`, `run`, `score`, `report`, `verify`.

- [ ] **Step 1: Write failing paired-report tests**

```python
def test_report_separates_e2e_pass_from_quality_verdict() -> None:
    report = build_report(PAIRED_RESULTS_WITH_SMALL_GAIN, CONFIG)
    assert report["e2e"]["verdict"] == "passed"
    assert report["quality"]["verdict"] == "not_demonstrated"
    assert report["quality"]["mean_delta"] == 0.04


def test_verify_rejects_live_worker_even_after_success() -> None:
    errors = verify_e2e(SUCCEEDED_RESULTS_WITH_LIVE_PID, CASES, pid_exists=lambda pid: True)
    assert errors == ["case-1: worker PID 991 is still alive"]
```

- [ ] **Step 2: Write failing CLI smoke test**

```python
def test_cli_score_writes_json_without_revealing_assignment_to_scorer(tmp_path: Path) -> None:
    exit_code = main(["--config", str(CONFIG_PATH), "score"], services=FAKE_SERVICES)
    assert exit_code == 0
    assert read_json(SCORES_PATH)["arms"].keys() == {"A", "B"}
    assert "method" not in read_json(SCORES_PATH)["arms"]["A"]["cases"][0]
```

- [ ] **Step 3: Run report/CLI tests and verify RED**

Run: `uv run --project benchmarks/oolong_codex pytest tests/test_report.py tests/test_cli.py -q`

Expected: FAIL because report and CLI modules are missing.

- [ ] **Step 4: Implement scoring, aggregation, gates, and commands**

`score` writes opaque arm scores. `report` reveals assignment and writes both JSON and Markdown with individual gaps, A/B scores, candidate-only wins, shared failures, validity limits, verdict, minimum next adjustment, and consolidated metrics. `verify` exits nonzero for any E2E gate failure. Every command prints one JSON object to stdout and writes durable artifacts atomically.

- [ ] **Step 5: Run the full isolated deterministic suite**

Run: `uv run --project benchmarks/oolong_codex pytest -q`

Expected: PASS with no live model calls.

Run: `uv run --project benchmarks/oolong_codex ruff check .`

Run: `uv run --project benchmarks/oolong_codex ruff format --check .`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add benchmarks/oolong_codex
git commit -m "feat: score and verify OOLONG benchmark"
```

### Task 6: Materialize and execute the 25 × 2 official benchmark

**Files:**
- Create: `benchmarks/oolong_codex/reports/<run-id>.json`
- Create: `benchmarks/oolong_codex/reports/<run-id>.md`
- Modify: `benchmarks/oolong_codex/README.md`

**Interfaces:**
- Consumes: all benchmark commands and ChatGPT subscription.
- Produces: 50 scored outputs, operational evidence, quality verdict, and exact reproduction commands.

- [ ] **Step 1: Verify prerequisites**

Run: `rlm-codex doctor`

Expected: `ok=true`, `chatgpt_account=chatgpt`, `OPENAI_API_KEY` unset, skill synchronized, local trusted execution.

- [ ] **Step 2: Sync isolated dependencies and prepare official cases**

Run: `uv sync --project benchmarks/oolong_codex --group test`

Run: `uv run --project benchmarks/oolong_codex oolong-codex prepare`

Expected: exactly 25 cases at 131072, pinned revision and hashes in manifest.

- [ ] **Step 3: Execute both arms sequentially**

Run: `uv run --project benchmarks/oolong_codex oolong-codex run`

Expected: 25 baseline and 25 candidate raw results; candidates reuse durable run IDs on resume.

- [ ] **Step 4: Score, report, and verify**

Run: `uv run --project benchmarks/oolong_codex oolong-codex score`

Run: `uv run --project benchmarks/oolong_codex oolong-codex report`

Run: `uv run --project benchmarks/oolong_codex oolong-codex verify`

Expected: deterministic score files, compiled JSON/Markdown report, and E2E PASS or a precise nonzero failure without overstating quality.

- [ ] **Step 5: Commit reproducible report**

```powershell
git add benchmarks/oolong_codex/README.md benchmarks/oolong_codex/reports
git commit -m "test: benchmark RLM Codex on OOLONG"
```

### Task 7: Repository-wide verification and governance

**Files:**
- Modify: `docs/STRUCTURE.md`
- Modify: `docs/INDEX.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/CHANGELOG.md`
- Modify: `docs/ABERTO.md` only if the run discovers a real unresolved blocker.

**Interfaces:**
- Consumes: final benchmark report and repository gates.
- Produces: synchronized project state and a clean committed worktree.

- [ ] **Step 1: Synchronize canonical documentation**

Add `benchmarks/oolong_codex/` to structure and index, mark the benchmark stage according to actual E2E outcome, and record exact counts and verdicts in the changelog. Do not mark quality gain if the frozen threshold is not met.

- [ ] **Step 2: Run benchmark and repository gates fresh**

Run: `uv run --project benchmarks/oolong_codex pytest -q`

Run: `uv run --project benchmarks/oolong_codex ruff check .`

Run: `uv run --project benchmarks/oolong_codex ruff format --check .`

Run: `uv run pre-commit run --all-files`

Run: `uv run pytest -q`

Expected: all commands exit 0.

- [ ] **Step 3: Verify repository state and commit governance**

Run: `git diff --check`

Run: `git status --short`

Expected: only intended governance/report changes before commit.

```powershell
git add docs benchmarks/oolong_codex
git commit -m "docs: record OOLONG benchmark verdict"
```
