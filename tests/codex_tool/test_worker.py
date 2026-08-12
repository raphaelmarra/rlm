import time
from pathlib import Path

import pytest

from rlm.codex_tool.paths import CodexPaths
from rlm.codex_tool.protocol import RunStatus
from rlm.codex_tool.store import RunStore
from rlm.codex_tool.worker import worker_main
from rlm.core.types import ModelUsageSummary, RLMChatCompletion, UsageSummary
from rlm.utils.exceptions import CancellationError


def completion(response: str = "answer") -> RLMChatCompletion:
    return RLMChatCompletion(
        root_model="gpt-5.6-terra",
        prompt={"notes.txt": "context"},
        response=response,
        usage_summary=UsageSummary(
            model_usage_summaries={
                "gpt-5.6-terra": ModelUsageSummary(2, 30, 10, None),
            }
        ),
        execution_time=1.25,
        metadata={"iterations": [{"iteration": 1}]},
    )


def seed_run(tmp_path: Path) -> tuple[RunStore, str]:
    store = RunStore(CodexPaths(tmp_path / "home"))
    state = store.create_run(
        {
            "question": "question",
            "model": "gpt-5.6-terra",
            "max_iterations": 6,
            "max_timeout": 600,
        },
        {"notes.txt": "context"},
        run_id="run-1",
    )
    return store, state.id


def test_worker_transitions_heartbeat_callbacks_and_success(tmp_path: Path) -> None:
    store, run_id = seed_run(tmp_path)

    def run_function(request, callbacks):
        callbacks.on_iteration_start(0, 1)
        time.sleep(0.04)
        callbacks.on_subcall_start(1, "gpt-5.6-terra", "preview")
        callbacks.on_subcall_complete(1, "gpt-5.6-terra", 0.01, None)
        callbacks.on_iteration_complete(0, 1, 0.04)
        return completion()

    exit_code = worker_main(
        run_id,
        store.paths.home,
        run_function=run_function,
        heartbeat_interval=0.01,
    )

    state = store.read_state(run_id)
    result = store.read_result(run_id)
    event_types = [event["type"] for event in store.read_events(run_id)]
    assert exit_code == 0
    assert state.status is RunStatus.SUCCEEDED
    assert state.pid is None
    assert state.heartbeat_at is not None
    assert state.progress == {"iteration": 1, "subcalls_completed": 1}
    assert result["response"] == "answer"
    assert result["usage_summary"]["total_cost"] is None
    assert "iteration_started" in event_types
    assert "subcall_completed" in event_types
    assert event_types[-1] == "status"


def test_worker_persists_sanitized_failure(tmp_path: Path) -> None:
    store, run_id = seed_run(tmp_path)

    def fail(request, callbacks):
        raise RuntimeError("Bearer private-token")

    exit_code = worker_main(run_id, store.paths.home, run_function=fail)

    state = store.read_state(run_id)
    result = store.read_result(run_id)
    assert exit_code == 10
    assert state.status is RunStatus.FAILED
    assert state.pid is None
    assert result["error"]["type"] == "RuntimeError"
    assert "private-token" not in result["error"]["message"]
    assert state.error == result["error"]


def test_worker_converts_cancellation_to_terminal_state(tmp_path: Path) -> None:
    store, run_id = seed_run(tmp_path)

    def cancel(request, callbacks):
        raise CancellationError(partial_answer="partial")

    exit_code = worker_main(run_id, store.paths.home, run_function=cancel)

    state = store.read_state(run_id)
    result = store.read_result(run_id)
    assert exit_code == 0
    assert state.status is RunStatus.CANCELLED
    assert state.pid is None
    assert result == {"status": "cancelled", "partial_answer": "partial"}


def test_worker_does_not_start_cancelled_run(tmp_path: Path) -> None:
    store, run_id = seed_run(tmp_path)
    store.transition(run_id, RunStatus.CANCELLED)
    calls = []

    exit_code = worker_main(
        run_id,
        store.paths.home,
        run_function=lambda request, callbacks: calls.append(request),
    )

    assert exit_code == 0
    assert calls == []
    assert store.read_state(run_id).status is RunStatus.CANCELLED


def test_worker_startup_race_preserves_cancelled_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, run_id = seed_run(tmp_path)
    original_transition = RunStore.transition
    cancellation_injected = False

    def transition_with_cancellation(self, selected_run_id, target, **kwargs):
        nonlocal cancellation_injected
        if target is RunStatus.RUNNING and not cancellation_injected:
            cancellation_injected = True
            original_transition(self, selected_run_id, RunStatus.CANCELLED, pid=None)
        return original_transition(self, selected_run_id, target, **kwargs)

    monkeypatch.setattr(RunStore, "transition", transition_with_cancellation)
    calls = []

    exit_code = worker_main(
        run_id,
        store.paths.home,
        run_function=lambda request, callbacks: calls.append(request),
    )

    assert exit_code == 0
    assert calls == []
    assert store.read_state(run_id).status is RunStatus.CANCELLED
    assert not store.paths.for_run(run_id).result.exists()
