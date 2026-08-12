import json
from pathlib import Path

from oolong_codex.models import CaseRecord, RawResult
from oolong_codex.report import build_partial_report, partial_markdown


def test_partial_report_scores_only_successful_pairs_and_surfaces_attempts(tmp_path: Path) -> None:
    cases = [
        _case(tmp_path, "one", "one"),
        _case(tmp_path, "two", "two"),
    ]
    baseline = [
        _result("one", "A", "one", calls=1),
        _result("two", "A", "two", calls=1),
    ]
    rlm = [
        _result("one", "B", "one", calls=3),
        _result("two", "B", "", calls=2, status="failed", error="timed out"),
    ]
    config = _config()

    report = build_partial_report(cases, {"A": baseline, "B": rlm}, config)

    assert report["kind"] == "partial"
    assert report["coverage"]["planned_cases"] == 2
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
    assert report["quality"]["conclusive"] is False

    markdown = partial_markdown(report)

    assert "# OOLONG Codex partial benchmark" in markdown
    assert "Paired successful cases" in markdown
    assert "RLM failures" in markdown
    assert "two: timed out" in markdown


def _case(tmp_path: Path, case_id: str, answer: str) -> CaseRecord:
    case_dir = tmp_path / case_id
    case_dir.mkdir()
    context_path = case_dir / "context.txt"
    question_path = case_dir / "question.txt"
    gold_path = case_dir / "gold.json"
    context_path.write_text("context", encoding="utf-8")
    question_path.write_text("question", encoding="utf-8")
    gold_path.write_text(
        json.dumps({"answer": answer, "answer_type": "ANSWER_TYPE.STRING"}), encoding="utf-8"
    )
    return CaseRecord(
        id=case_id,
        context_path=context_path,
        question_path=question_path,
        gold_path=gold_path,
        context_sha256="context-hash",
        question_sha256="question-hash",
    )


def _result(
    case_id: str,
    arm: str,
    response: str,
    *,
    calls: int,
    status: str = "succeeded",
    error: str | None = None,
) -> RawResult:
    return RawResult(
        case_id=case_id,
        arm=arm,
        response=response,
        status=status,
        wall_seconds=1.0,
        calls=calls,
        error=error,
    )


def _config() -> object:
    from types import SimpleNamespace

    return SimpleNamespace(
        arms={"A": "baseline", "B": "rlm"},
        quality_threshold=0.1,
        bootstrap_samples=100,
        seed=42,
    )
