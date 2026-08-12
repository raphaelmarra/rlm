"""Blind scoring, paired aggregation, and independent benchmark gates."""

from __future__ import annotations

import hashlib
import statistics
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from oolong_codex.config import BenchmarkConfig
from oolong_codex.models import CaseRecord, RawResult
from oolong_codex.scorer import paired_bootstrap, score_answer
from oolong_codex.storage import read_json


def score_arms(
    cases: Sequence[CaseRecord],
    results_by_arm: Mapping[str, Sequence[RawResult]],
) -> dict[str, Any]:
    """Score opaque arms without including their method assignment."""

    cases_by_id = {case.id: case for case in cases}
    arms: dict[str, Any] = {}
    for arm, results in results_by_arm.items():
        scored = []
        for result in results:
            case = cases_by_id[result.case_id]
            gold = read_json(case.gold_path)
            value = score_answer(gold["answer"], gold["answer_type"], result.response)
            scored.append(
                {
                    "case_id": result.case_id,
                    "score": value,
                    "exact": value == 1.0,
                    "terminal_status": result.status,
                }
            )
        arms[arm] = {
            "cases": scored,
            "mean_score": statistics.fmean(item["score"] for item in scored),
            "exact_hits": sum(item["exact"] for item in scored),
        }
    return {"arms": arms}


def build_report(
    scores: Mapping[str, Any],
    config: BenchmarkConfig,
    results_by_arm: Mapping[str, Sequence[RawResult]] | None = None,
    verification_errors: Sequence[str] = (),
) -> dict[str, Any]:
    baseline_arm = _arm_for_method(config.arms, "baseline")
    rlm_arm = _arm_for_method(config.arms, "rlm")
    arms = scores["arms"]
    baseline = {item["case_id"]: item for item in arms[baseline_arm]["cases"]}
    candidate = {item["case_id"]: item for item in arms[rlm_arm]["cases"]}
    if baseline.keys() != candidate.keys():
        verification_errors = [*verification_errors, "baseline and RLM case sets differ"]
    case_ids = sorted(baseline.keys() & candidate.keys())
    gaps = [candidate[case_id]["score"] - baseline[case_id]["score"] for case_id in case_ids]
    mean_delta = statistics.fmean(gaps) if gaps else 0.0
    interval = paired_bootstrap(gaps, config.bootstrap_samples, config.seed) if gaps else (0.0, 0.0)
    if verification_errors:
        quality_verdict = "invalid"
    elif mean_delta < 0:
        quality_verdict = "regression"
    elif mean_delta >= config.quality_threshold and interval[0] > 0:
        quality_verdict = "demonstrated"
    else:
        quality_verdict = "not_demonstrated"
    return {
        "protocol": {
            "num_cases": len(case_ids),
            "arms": dict(config.arms),
            "quality_threshold": config.quality_threshold,
        },
        "e2e": {
            "verdict": "failed" if verification_errors else "passed",
            "errors": list(verification_errors),
        },
        "quality": {
            "verdict": quality_verdict,
            "mean_delta": round(mean_delta, 12),
            "bootstrap_95": [interval[0], interval[1]],
        },
        "scores": arms,
        "paired_cases": [
            {
                "case_id": case_id,
                "baseline": baseline[case_id]["score"],
                "rlm": candidate[case_id]["score"],
                "delta": candidate[case_id]["score"] - baseline[case_id]["score"],
            }
            for case_id in case_ids
        ],
        "metrics": _metrics(results_by_arm or {}),
        "minimum_next_adjustment": (
            None
            if quality_verdict == "demonstrated"
            else "Increase sample size before changing the frozen protocol."
        ),
    }


def build_partial_report(
    cases: Sequence[CaseRecord],
    results_by_arm: Mapping[str, Sequence[RawResult]],
    config: BenchmarkConfig,
) -> dict[str, Any]:
    """Build an explicitly inconclusive report from the completed result pairs."""

    baseline_arm = _arm_for_method(config.arms, "baseline")
    rlm_arm = _arm_for_method(config.arms, "rlm")
    results_by_case = {
        arm: _results_by_case(results_by_arm.get(arm, ())) for arm in (baseline_arm, rlm_arm)
    }
    paired_case_ids = [
        case.id
        for case in cases
        if all(
            case.id in results_by_case[arm] and results_by_case[arm][case.id].status == "succeeded"
            for arm in (baseline_arm, rlm_arm)
        )
    ]
    paired_cases = [case for case in cases if case.id in paired_case_ids]
    paired_results = {
        arm: [results_by_case[arm][case_id] for case_id in paired_case_ids]
        for arm in (baseline_arm, rlm_arm)
    }
    paired_scores = _score_partial_pairs(paired_cases, paired_results)
    paired_report = build_report(paired_scores, config, paired_results)
    attempt_metrics = _metrics(results_by_arm)
    attempt_metrics[rlm_arm]["failure_details"] = [
        {"case_id": result.case_id, "error": result.error or "unknown error"}
        for result in results_by_arm.get(rlm_arm, ())
        if result.status != "succeeded"
    ]

    return {
        "kind": "partial",
        "coverage": {
            "planned_cases": len(cases),
            "paired_succeeded": len(paired_cases),
            "arms": {
                arm: _arm_counts(results_by_arm.get(arm, ()), len(cases)) for arm in config.arms
            },
        },
        "e2e": {"verdict": "partial", "errors": []},
        "quality": {**paired_report["quality"], "conclusive": False},
        "scores": paired_report["scores"],
        "paired_cases": paired_report["paired_cases"],
        "metrics": paired_report["metrics"],
        "attempt_metrics": attempt_metrics,
    }


def partial_markdown(report: Mapping[str, Any]) -> str:
    """Render an auditable, non-conclusive partial benchmark report."""

    coverage = report["coverage"]
    quality = report["quality"]
    lines = [
        "# OOLONG Codex partial benchmark",
        "",
        "This partial result is not conclusive and does not pass the E2E benchmark.",
        "",
        "## Coverage",
        "",
        f"- Planned cases: `{coverage['planned_cases']}`",
        f"- Paired successful cases: `{coverage['paired_succeeded']}`",
    ]
    lines.extend(
        f"- {arm}: available `{counts['available']}`, succeeded `{counts['succeeded']}`, "
        f"failed `{counts['failed']}`, missing `{counts['missing']}`"
        for arm, counts in coverage["arms"].items()
    )
    lines.extend(
        [
            "",
            "## Paired quality",
            "",
            f"- Verdict: **{quality['verdict']}** (not conclusive)",
            f"- Mean paired delta: `{quality['mean_delta']}`",
            f"- Paired bootstrap 95%: `{quality['bootstrap_95']}`",
            "",
            "## Paired metrics",
            "",
        ]
    )
    lines.extend(_metric_lines(report["metrics"]))
    lines.extend(["", "## Attempt metrics", ""])
    lines.extend(_metric_lines(report["attempt_metrics"]))

    rlm_failures = [
        result for result in report["attempt_metrics"].get("B", {}).get("failure_details", [])
    ]
    if rlm_failures:
        lines.extend(["", "## RLM failures", ""])
        lines.extend(f"- {item['case_id']}: {item['error']}" for item in rlm_failures)
    return "\n".join(lines) + "\n"


def verify_e2e(
    results_by_arm: Mapping[str, Sequence[RawResult]],
    cases: Sequence[CaseRecord],
    *,
    rlm_arm: str,
    pid_exists: Callable[[int], bool],
    verify_hashes: bool = True,
) -> list[str]:
    errors: list[str] = []
    candidates = list(results_by_arm.get(rlm_arm, []))
    if len(candidates) != len(cases):
        errors.append(f"RLM result count is {len(candidates)}; expected {len(cases)}")
    total_subcalls = 0
    for result in candidates:
        if result.status != "succeeded":
            errors.append(f"{result.case_id}: RLM status is {result.status}")
        metadata = result.metadata
        rlm_metadata = metadata.get("rlm_metadata") or {}
        if rlm_metadata.get("environment_type") != "local":
            errors.append(f"{result.case_id}: environment is not local")
        if not rlm_metadata.get("iterations"):
            errors.append(f"{result.case_id}: no RLM iterations recorded")
        total_subcalls += int(metadata.get("subcalls", 0))
        if result.pid is not None:
            errors.append(f"{result.case_id}: terminal worker PID is {result.pid}")
        if result.original_pid is not None and pid_exists(result.original_pid):
            errors.append(f"{result.case_id}: worker PID {result.original_pid} is still alive")
    if candidates and total_subcalls == 0:
        errors.append("no real RLM subcall was recorded")
    if verify_hashes:
        for case in cases:
            if _sha256(case.context_path.read_bytes()) != case.context_sha256:
                errors.append(f"{case.id}: context hash changed")
            if _sha256(case.question_path.read_bytes()) != case.question_sha256:
                errors.append(f"{case.id}: question hash changed")
    return errors


def _metrics(results_by_arm: Mapping[str, Sequence[RawResult]]) -> dict[str, Any]:
    return {
        arm: {
            "calls": sum(result.calls or 0 for result in results),
            "input_tokens": sum(result.input_tokens or 0 for result in results),
            "output_tokens": sum(result.output_tokens or 0 for result in results),
            "wall_seconds": sum(result.wall_seconds for result in results),
            "total_cost": None,
            "failures": sum(result.status != "succeeded" for result in results),
            "subcalls": sum(int(result.metadata.get("subcalls", 0)) for result in results),
        }
        for arm, results in results_by_arm.items()
    }


def _results_by_case(results: Sequence[RawResult]) -> dict[str, RawResult]:
    return {result.case_id: result for result in results}


def _score_partial_pairs(
    cases: Sequence[CaseRecord], results_by_arm: Mapping[str, Sequence[RawResult]]
) -> dict[str, Any]:
    if cases:
        return score_arms(cases, results_by_arm)
    return {
        "arms": {arm: {"cases": [], "mean_score": 0.0, "exact_hits": 0} for arm in results_by_arm}
    }


def _arm_counts(results: Sequence[RawResult], planned_cases: int) -> dict[str, int]:
    available = len(results)
    succeeded = sum(result.status == "succeeded" for result in results)
    return {
        "available": available,
        "succeeded": succeeded,
        "failed": available - succeeded,
        "missing": planned_cases - available,
    }


def _metric_lines(metrics_by_arm: Mapping[str, Mapping[str, Any]]) -> list[str]:
    return [
        f"- {arm}: calls `{metrics['calls']}`, input tokens `{metrics['input_tokens']}`, "
        f"output tokens `{metrics['output_tokens']}`, wall seconds `{metrics['wall_seconds']}`, "
        f"failures `{metrics['failures']}`, subcalls `{metrics['subcalls']}`"
        for arm, metrics in metrics_by_arm.items()
    ]


def _arm_for_method(arms: Mapping[str, str], method: str) -> str:
    return next(arm for arm, assigned in arms.items() if assigned == method)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
