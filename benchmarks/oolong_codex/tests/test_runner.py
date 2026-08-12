from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from oolong_codex.config import BenchmarkPaths
from oolong_codex.runner import run_baseline_case, run_rlm_case
from oolong_codex.storage import write_json_atomic


def make_case(tmp_path: Path) -> SimpleNamespace:
    context_path = tmp_path / "context.txt"
    question_path = tmp_path / "question.txt"
    gold_path = tmp_path / "gold.json"
    context_path.write_text("public corpus", encoding="utf-8")
    question_path.write_text("Answer the count.\nQuestion: how many?", encoding="utf-8")
    gold_path.write_text(json.dumps({"answer": "gold-secret"}), encoding="utf-8")
    return SimpleNamespace(
        id="case-1",
        context_path=context_path,
        question_path=question_path,
        gold_path=gold_path,
        context_sha256="context-hash",
        question_sha256="question-hash",
    )


def make_config() -> SimpleNamespace:
    return SimpleNamespace(
        model_name="gpt-5.6-terra",
        reasoning_effort="medium",
        max_depth=1,
        max_iterations=12,
        max_timeout=1800,
        arms={"A": "baseline", "B": "rlm"},
    )


class RecordingClient:
    prompt = ""
    kwargs: dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        type(self).kwargs = kwargs

    def completion(self, prompt: str) -> str:
        type(self).prompt = prompt
        return "Answer: 7"

    def get_last_usage(self) -> SimpleNamespace:
        return SimpleNamespace(
            total_calls=1,
            total_input_tokens=101,
            total_output_tokens=4,
            total_cost=None,
        )


class RecordingInvoker:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, arguments: list[str], **kwargs: Any) -> dict[str, Any]:
        self.calls.append((arguments, kwargs))
        command = arguments[0]
        if command == "start":
            return {
                "schema_version": 1,
                "ok": True,
                "command": "start",
                "run": {"id": "run-7", "pid": 991, "status": "queued"},
            }
        if command == "result":
            return {
                "schema_version": 1,
                "ok": True,
                "command": "result",
                "result": {
                    "status": "succeeded",
                    "response": "Answer: 7",
                    "usage_summary": {
                        "model_usage_summaries": {
                            "gpt-5.6-terra": {
                                "total_calls": 3,
                                "total_input_tokens": 303,
                                "total_output_tokens": 12,
                            }
                        },
                        "total_cost": None,
                    },
                    "metadata": {
                        "iterations": [{"code_blocks": [{"result": {"rlm_calls": ["child"]}}]}]
                    },
                },
            }
        assert command == "status"
        return {
            "schema_version": 1,
            "ok": True,
            "command": "status",
            "run": {"id": "run-7", "pid": None, "status": "succeeded"},
        }


class TimeoutInvoker(RecordingInvoker):
    def __call__(self, arguments: list[str], **kwargs: Any) -> dict[str, Any]:
        self.calls.append((arguments, kwargs))
        if arguments[0] == "result":
            return {
                "schema_version": 1,
                "ok": False,
                "command": "result",
                "error": {"code": "STATE_CONFLICT", "message": "timed out"},
            }
        assert arguments[0] == "status"
        return {
            "schema_version": 1,
            "ok": True,
            "command": "status",
            "run": {"id": "run-7", "pid": 991, "status": "running"},
        }


def test_baseline_uses_context_without_gold_and_records_usage(tmp_path: Path) -> None:
    case = make_case(tmp_path)

    result = run_baseline_case(case, make_config(), client_factory=RecordingClient)

    assert result.response == "Answer: 7"
    assert "gold-secret" not in RecordingClient.prompt
    assert "public corpus" in RecordingClient.prompt
    assert result.input_tokens == 101
    assert result.output_tokens == 4
    assert result.total_cost is None
    assert RecordingClient.kwargs == {
        "model_name": "gpt-5.6-terra",
        "reasoning_effort": "medium",
        "timeout": 1800,
    }


def test_rlm_resume_reuses_saved_run_id_without_second_start(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    paths = BenchmarkPaths(tmp_path / "artifacts")
    write_json_atomic(paths.attempt_path("B", case.id), {"run_id": "run-7", "pid": 991})
    invoker = RecordingInvoker()

    result = run_rlm_case(case, make_config(), paths, cli_invoker=invoker)

    assert [call[0][0] for call in invoker.calls] == ["result", "status"]
    assert result.run_id == "run-7"
    assert result.original_pid == 991
    assert result.calls == 3
    assert result.metadata["subcalls"] == 1


def test_rlm_start_persists_attempt_before_waiting(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    paths = BenchmarkPaths(tmp_path / "artifacts")
    invoker = RecordingInvoker()

    result = run_rlm_case(
        case,
        make_config(),
        paths,
        cli_invoker=invoker,
        pid_exists=lambda pid: False,
    )

    attempt = json.loads(paths.attempt_path("B", case.id).read_text(encoding="utf-8"))
    assert attempt["run_id"] == "run-7"
    assert attempt["pid"] == 991
    assert [call[0][0] for call in invoker.calls] == ["start", "result", "status"]
    assert "OPENAI_API_KEY" not in invoker.calls[0][1]["env"]
    assert result.metadata["original_pid_alive"] is False


def test_rlm_timeout_keeps_attempt_resumable_without_terminal_raw(tmp_path: Path) -> None:
    case = make_case(tmp_path)
    paths = BenchmarkPaths(tmp_path / "artifacts")
    write_json_atomic(paths.attempt_path("B", case.id), {"run_id": "run-7", "pid": 991})

    try:
        run_rlm_case(case, make_config(), paths, cli_invoker=TimeoutInvoker())
    except RuntimeError as error:
        assert "resume run run-7" in str(error)
    else:
        raise AssertionError("expected non-terminal timeout to remain resumable")
