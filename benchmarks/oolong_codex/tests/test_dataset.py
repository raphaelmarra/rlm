import hashlib
import json
from pathlib import Path

import oolong_codex.dataset as dataset
import pytest
from oolong_codex.config import BenchmarkConfig, BenchmarkPaths
from oolong_codex.dataset import (
    build_root_prompt,
    load_cases,
    materialize_rows,
    select_rows,
)


def make_config(num_cases: int) -> BenchmarkConfig:
    return BenchmarkConfig(
        dataset_name="oolongbench/oolong-synth",
        dataset_revision="revision",
        dataset_split="validation",
        dataset_subset="trec_coarse",
        context_len=131072,
        num_cases=num_cases,
        seed=42,
        model_name="model",
        reasoning_effort="medium",
        max_depth=1,
        max_iterations=12,
        max_timeout=1800,
        bootstrap_samples=1000,
        quality_threshold=0.1,
        artifacts_dir=Path("artifacts"),
        arms={"A": "baseline", "B": "rlm"},
    )


def make_row(
    case_id: str | int, *, context: str = "shared context", **overrides: object
) -> dict[str, object]:
    row: dict[str, object] = {
        "id": case_id,
        "context_len": 131072,
        "dataset": "trec_coarse",
        "context_window_text": context,
        "question": f"Which category is {case_id}?",
        "task_group": "classification",
        "task": "aggregate",
        "answer": "['entity']",
        "answer_type": "ANSWER_TYPE.LABEL",
        "input_subset": "validation",
        "num_labels": 6,
        "context_window_id": "window-1",
    }
    row.update(overrides)
    return row


def test_select_rows_filters_then_deterministically_selects_25() -> None:
    rows = [make_row(f"case-{index:02}") for index in range(30)]
    rows.insert(4, make_row("wrong-dataset", dataset="other"))
    rows.insert(9, make_row("wrong-length", context_len=1024))

    selected = select_rows(rows, make_config(25))

    assert [row["id"] for row in selected] == [f"case-{index:02}" for index in range(25)]


def test_materialized_prompt_does_not_contain_gold(tmp_path: Path) -> None:
    secret = "gold-secret"
    cases = materialize_rows(
        [make_row("case-1", answer=f"['{secret}']")], make_config(1), BenchmarkPaths(tmp_path)
    )

    prompt = cases[0].question_path.read_text(encoding="utf-8")
    gold = json.loads(cases[0].gold_path.read_text(encoding="utf-8"))["answer"]

    assert gold not in prompt
    assert prompt == build_root_prompt("Which category is case-1?")


def test_materialization_accepts_official_integer_case_id(tmp_path: Path) -> None:
    [case] = materialize_rows([make_row(17000208)], make_config(1), BenchmarkPaths(tmp_path))

    assert case.id == "17000208"


def test_materialization_reuses_shared_context_and_writes_gold_free_manifest(
    tmp_path: Path,
) -> None:
    context = "the shared 131k corpus"
    cases = materialize_rows(
        [make_row("case-1", context=context), make_row("case-2", context=context)],
        make_config(2),
        BenchmarkPaths(tmp_path),
    )

    manifest = (tmp_path / "dataset" / "manifest.json").read_text(encoding="utf-8")

    assert cases[0].context_path == cases[1].context_path
    assert cases[0].context_path.read_text(encoding="utf-8") == context
    assert cases[0].context_sha256 == hashlib.sha256(context.encode()).hexdigest()
    assert "['entity']" not in manifest
    assert json.loads(manifest)["cases"][0]["context_sha256"] == cases[0].context_sha256


def test_load_cases_reconstructs_manifest_records(tmp_path: Path) -> None:
    paths = BenchmarkPaths(tmp_path)
    materialized = materialize_rows([make_row("case-1")], make_config(1), paths)

    assert load_cases(paths) == materialized


def test_load_cases_rejects_tampered_context(tmp_path: Path) -> None:
    paths = BenchmarkPaths(tmp_path)
    [case] = materialize_rows([make_row("case-1")], make_config(1), paths)
    case.context_path.write_text("tampered", encoding="utf-8")

    with pytest.raises(ValueError, match="context hash mismatch"):
        load_cases(paths)


def test_materialize_dataset_streams_pinned_rows_without_network(
    tmp_path: Path, monkeypatch
) -> None:
    calls: dict[str, object] = {}

    class Stream:
        def filter(self, predicate):
            calls["filter"] = predicate(make_row("probe"))
            return self

        def shuffle(self, *, seed: int, buffer_size: int) -> list[dict[str, object]]:
            calls["shuffle"] = (seed, buffer_size)
            return [make_row("case-1")]

    def fake_load_dataset(*args: object, **kwargs: object) -> Stream:
        calls["load"] = (args, kwargs)
        return Stream()

    monkeypatch.setattr(dataset, "load_dataset", fake_load_dataset)
    paths = BenchmarkPaths(tmp_path)

    cases = dataset.materialize_dataset(make_config(1), paths)

    assert cases[0].id == "case-1"
    assert calls["load"] == (
        ("parquet",),
        {
            "split": "validation",
            "data_files": {
                "validation": "https://huggingface.co/datasets/oolongbench/oolong-synth/resolve/revision/data/validation-00007-of-00009.parquet"
            },
            "streaming": True,
            "cache_dir": tmp_path / "cache" / "huggingface",
        },
    )
    assert calls["filter"] is True
    assert calls["shuffle"] == (42, 100)
