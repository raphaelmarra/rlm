from pathlib import Path
from types import SimpleNamespace

from oolong_codex.report import build_report, verify_e2e


def test_report_separates_e2e_pass_from_quality_verdict() -> None:
    scores = {
        "arms": {
            "A": {"cases": [{"case_id": "one", "score": 0.5}]},
            "B": {"cases": [{"case_id": "one", "score": 0.54}]},
        }
    }
    config = SimpleNamespace(
        arms={"A": "baseline", "B": "rlm"},
        quality_threshold=0.10,
        bootstrap_samples=100,
        seed=42,
    )

    report = build_report(scores, config)

    assert report["e2e"]["verdict"] == "passed"
    assert report["quality"]["verdict"] == "not_demonstrated"
    assert report["quality"]["mean_delta"] == 0.04


def test_verify_rejects_live_worker_even_after_success(tmp_path: Path) -> None:
    context = tmp_path / "context.txt"
    question = tmp_path / "question.txt"
    context.write_text("x", encoding="utf-8")
    question.write_text("q", encoding="utf-8")
    case = SimpleNamespace(
        id="case-1",
        context_path=context,
        question_path=question,
        context_sha256="unused",
        question_sha256="unused",
    )
    candidate = SimpleNamespace(
        case_id="case-1",
        status="succeeded",
        pid=None,
        original_pid=991,
        metadata={
            "original_pid_alive": False,
            "subcalls": 1,
            "rlm_metadata": {"environment_type": "local", "iterations": [{}]},
        },
    )

    errors = verify_e2e(
        {"B": [candidate]},
        [case],
        rlm_arm="B",
        pid_exists=lambda pid: True,
        verify_hashes=False,
    )

    assert errors == ["case-1: worker PID 991 is still alive"]
