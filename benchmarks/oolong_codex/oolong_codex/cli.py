"""Command-line orchestration for the isolated OOLONG benchmark."""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

from oolong_codex.config import BenchmarkConfig, BenchmarkPaths, load_config
from oolong_codex.dataset import load_cases, materialize_dataset
from oolong_codex.models import CaseRecord, RawResult
from oolong_codex.report import (
    build_partial_report,
    build_report,
    partial_markdown,
    score_arms,
    verify_e2e,
)
from oolong_codex.runner import run_arm
from oolong_codex.storage import read_json, write_json_atomic


@dataclass(frozen=True)
class Services:
    prepare: Callable[[BenchmarkConfig, BenchmarkPaths], list[CaseRecord]] = materialize_dataset
    run: Callable[[str, Sequence[CaseRecord], BenchmarkConfig, BenchmarkPaths], list[RawResult]] = (
        run_arm
    )
    pid_exists: Callable[[int], bool] = psutil.pid_exists


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="oolong-codex")
    parser.add_argument("--config", type=Path, default=Path("benchmark.toml"))
    parser.add_argument(
        "command", choices=["prepare", "run", "score", "report", "partial-report", "verify"]
    )
    parser.add_argument("--report-id", default=None)
    return parser


def main(argv: Sequence[str] | None = None, *, services: Services | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    selected_services = services or Services()
    config = load_config(arguments.config)
    paths = BenchmarkPaths(config.artifacts_dir)
    command = arguments.command

    if command == "prepare":
        cases = (
            load_cases(paths)
            if paths.manifest_path.exists()
            else selected_services.prepare(config, paths)
        )
        return _emit({"ok": True, "command": command, "cases": len(cases)})

    cases = load_cases(paths)
    if command == "run":
        counts = {}
        for method in ("baseline", "rlm"):
            counts[method] = len(selected_services.run(method, cases, config, paths))
        return _emit({"ok": True, "command": command, "results": counts})

    if command == "partial-report":
        if not arguments.report_id:
            raise ValueError("--report-id is required for partial-report")
        results = _load_available_results(config, paths, cases)
        report = build_partial_report(cases, results, config)
        versioned_dir = arguments.config.resolve().parent / "reports"
        write_json_atomic(versioned_dir / f"{arguments.report_id}.json", report)
        _write_text_atomic(versioned_dir / f"{arguments.report_id}.md", partial_markdown(report))
        return _emit(
            {"ok": True, "command": command, "report": str(versioned_dir), "e2e": "partial"}
        )

    results = _load_results(config, paths, cases)
    scores_path = paths.scores_dir / "opaque.json"
    if command == "score":
        scores = score_arms(cases, results)
        write_json_atomic(scores_path, scores)
        return _emit({"ok": True, "command": command, "path": str(scores_path)})

    scores = read_json(scores_path)
    rlm_arm = next(arm for arm, method in config.arms.items() if method == "rlm")
    errors = verify_e2e(
        results,
        cases,
        rlm_arm=rlm_arm,
        pid_exists=selected_services.pid_exists,
    )
    if command == "verify":
        return _emit({"ok": not errors, "command": command, "errors": errors}, code=bool(errors))

    report = build_report(scores, config, results, errors)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    artifact_json = paths.report_path("latest")
    artifact_markdown = paths.report_path("latest", ".md")
    write_json_atomic(artifact_json, report)
    _write_text_atomic(artifact_markdown, _markdown(report))
    versioned_dir = arguments.config.resolve().parent / "reports"
    versioned_json = versioned_dir / f"{run_id}.json"
    versioned_markdown = versioned_dir / f"{run_id}.md"
    write_json_atomic(versioned_json, report)
    _write_text_atomic(versioned_markdown, _markdown(report))
    return _emit(
        {
            "ok": not errors,
            "command": command,
            "report": str(versioned_json),
            "e2e": report["e2e"]["verdict"],
            "quality": report["quality"]["verdict"],
        },
        code=bool(errors),
    )


def entrypoint() -> None:
    raise SystemExit(main())


def _load_results(
    config: BenchmarkConfig, paths: BenchmarkPaths, cases: Sequence[CaseRecord]
) -> dict[str, list[RawResult]]:
    loaded: dict[str, list[RawResult]] = {}
    for arm in config.arms:
        loaded[arm] = []
        for case in cases:
            path = paths.raw_path(arm, case.id)
            if not path.exists():
                raise ValueError(f"missing raw result: {path}")
            loaded[arm].append(RawResult(**read_json(path)))
    return loaded


def _load_available_results(
    config: BenchmarkConfig, paths: BenchmarkPaths, cases: Sequence[CaseRecord]
) -> dict[str, list[RawResult]]:
    loaded: dict[str, list[RawResult]] = {arm: [] for arm in config.arms}
    for arm in config.arms:
        for case in cases:
            path = paths.raw_path(arm, case.id)
            if path.exists():
                loaded[arm].append(RawResult(**read_json(path)))
    return loaded


def _emit(payload: dict[str, Any], *, code: bool = False) -> int:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return int(code)


def _write_text_atomic(path: Path, value: str) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(value, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _markdown(report: dict[str, Any]) -> str:
    quality = report["quality"]
    lines = [
        "# OOLONG Codex benchmark",
        "",
        f"- E2E: **{report['e2e']['verdict']}**",
        f"- Quality: **{quality['verdict']}**",
        f"- Mean paired delta: `{quality['mean_delta']}`",
        f"- Paired bootstrap 95%: `{quality['bootstrap_95']}`",
        "",
        "## Paired cases",
        "",
        "| Case | Baseline | RLM | Delta |",
        "|---|---:|---:|---:|",
    ]
    lines.extend(
        f"| {item['case_id']} | {item['baseline']:.6f} | {item['rlm']:.6f} | {item['delta']:+.6f} |"
        for item in report["paired_cases"]
    )
    if report["e2e"]["errors"]:
        lines.extend(["", "## E2E errors", ""])
        lines.extend(f"- {error}" for error in report["e2e"]["errors"])
    return "\n".join(lines) + "\n"
