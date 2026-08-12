"""Pinned, gold-separated materialization of the official OOLONG dataset."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from datasets import load_dataset

from oolong_codex.config import BenchmarkConfig, BenchmarkPaths
from oolong_codex.models import CaseRecord
from oolong_codex.storage import read_json, write_json_atomic

QUESTION_INSTRUCTION = (
    "The context contains thousands of general-knowledge questions, one per "
    "line. Each line has a User ID and a question, and each question's answer "
    "falls into one of 6 categories: 'numeric value', 'entity', 'location', "
    "'description and abstract concept', 'abbreviation', 'human being'. "
    "Answer the following aggregate question."
)
PINNED_SHARD = "validation-00007-of-00009.parquet"


def select_rows(rows: Iterable[dict[str, Any]], config: BenchmarkConfig) -> list[dict[str, Any]]:
    """Keep the first configured official rows from an already shuffled stream."""

    selected: list[dict[str, Any]] = []
    for row in rows:
        if row.get("dataset") != config.dataset_subset:
            continue
        if row.get("context_len") != config.context_len:
            continue
        selected.append(row)
        if len(selected) == config.num_cases:
            return selected
    raise ValueError(
        f"dataset yielded only {len(selected)} matching rows; expected {config.num_cases}"
    )


def build_root_prompt(question: str) -> str:
    """Build the upstream root prompt without context or evaluator-only data."""

    return f"{QUESTION_INSTRUCTION}\n\nQuestion: {question}"


def materialize_rows(
    rows: Sequence[dict[str, Any]], config: BenchmarkConfig, paths: BenchmarkPaths
) -> list[CaseRecord]:
    """Write execution inputs, isolated gold answers, and a gold-free manifest."""

    if len(rows) != config.num_cases:
        raise ValueError(f"expected {config.num_cases} rows, received {len(rows)}")

    cases: list[CaseRecord] = []
    seen_ids: set[str] = set()
    corpus_paths: dict[str, Path] = {}
    for row in rows:
        case_id = _case_id(row)
        if case_id in seen_ids:
            raise ValueError(f"duplicate case id: {case_id}")
        seen_ids.add(case_id)

        context = _required_string(row, "context_window_text")
        question = _required_string(row, "question")
        context_sha256 = _sha256(context)
        question_text = build_root_prompt(question)
        question_sha256 = _sha256(question_text)

        context_path = corpus_paths.get(context_sha256)
        if context_path is None:
            context_path = paths.dataset_dir / "corpus" / context_sha256 / "context.txt"
            context_path.parent.mkdir(parents=True, exist_ok=True)
            context_path.write_text(context, encoding="utf-8", newline="\n")
            corpus_paths[context_sha256] = context_path

        case_dir = paths.case_dir(case_id)
        question_path = case_dir / "question.txt"
        gold_path = case_dir / "gold.json"
        case_dir.mkdir(parents=True, exist_ok=True)
        question_path.write_text(question_text, encoding="utf-8", newline="\n")
        write_json_atomic(
            gold_path,
            {
                "answer": _required_string(row, "answer"),
                "answer_type": _required_string(row, "answer_type"),
            },
        )
        cases.append(
            CaseRecord(
                id=case_id,
                context_path=context_path,
                question_path=question_path,
                gold_path=gold_path,
                context_sha256=context_sha256,
                question_sha256=question_sha256,
            )
        )

    write_json_atomic(paths.manifest_path, _manifest(cases, config, paths))
    return cases


def materialize_dataset(config: BenchmarkConfig, paths: BenchmarkPaths) -> list[CaseRecord]:
    """Stream only the pinned shard containing the frozen OOLONG slice."""

    if config.dataset_split != "validation":
        raise ValueError("the frozen benchmark supports only the validation split")
    source = (
        f"https://huggingface.co/datasets/{config.dataset_name}/resolve/"
        f"{config.dataset_revision}/data/{PINNED_SHARD}"
    )
    stream = load_dataset(
        "parquet",
        data_files={config.dataset_split: source},
        split=config.dataset_split,
        streaming=True,
        cache_dir=paths.artifacts_dir / "cache" / "huggingface",
    ).filter(
        lambda row: (
            row.get("dataset") == config.dataset_subset
            and row.get("context_len") == config.context_len
        )
    )
    stream = stream.shuffle(seed=config.seed, buffer_size=100)
    return materialize_rows(select_rows(stream, config), config, paths)


def load_cases(paths: BenchmarkPaths) -> list[CaseRecord]:
    """Reconstruct materialized records from the durable, gold-free manifest."""

    manifest = read_json(paths.manifest_path)
    entries = manifest.get("cases") if isinstance(manifest, dict) else None
    if not isinstance(entries, list):
        raise ValueError("manifest must contain a cases list")
    cases: list[CaseRecord] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("manifest case entry must be an object")
        case_id = _required_string(entry, "id")
        case_dir = paths.case_dir(case_id)
        case = CaseRecord(
            id=case_id,
            context_path=paths.dataset_dir / _required_string(entry, "context_file"),
            question_path=case_dir / "question.txt",
            gold_path=case_dir / "gold.json",
            context_sha256=_required_string(entry, "context_sha256"),
            question_sha256=_required_string(entry, "question_sha256"),
        )
        if _sha256(case.context_path.read_text(encoding="utf-8")) != case.context_sha256:
            raise ValueError(f"case {case_id} context hash mismatch")
        if _sha256(case.question_path.read_text(encoding="utf-8")) != case.question_sha256:
            raise ValueError(f"case {case_id} question hash mismatch")
        cases.append(case)
    return cases


def _manifest(
    cases: Sequence[CaseRecord], config: BenchmarkConfig, paths: BenchmarkPaths
) -> dict[str, Any]:
    return {
        "dataset": config.dataset_name,
        "revision": config.dataset_revision,
        "split": config.dataset_split,
        "subset": config.dataset_subset,
        "context_len": config.context_len,
        "seed": config.seed,
        "cases": [
            {
                "id": case.id,
                "context_file": str(case.context_path.relative_to(paths.dataset_dir)),
                "context_sha256": case.context_sha256,
                "question_sha256": case.question_sha256,
            }
            for case in cases
        ],
    }


def _required_string(row: dict[str, Any], name: str) -> str:
    value = row.get(name)
    if not isinstance(value, str) or not value:
        raise ValueError(f"row {name} must be a non-empty string")
    return value


def _case_id(row: dict[str, Any]) -> str:
    value = row.get("id")
    if isinstance(value, bool) or not isinstance(value, (int, str)) or str(value) == "":
        raise ValueError("row id must be a non-empty string or integer")
    return str(value)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
