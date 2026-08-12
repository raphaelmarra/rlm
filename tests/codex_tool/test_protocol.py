from datetime import UTC, datetime, timedelta

import pytest

from rlm.codex_tool.protocol import (
    TERMINAL_STATUSES,
    RunState,
    RunStatus,
    StateConflictError,
    error_envelope,
    success_envelope,
)


def test_new_run_state_is_queued_with_stable_schema() -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)

    state = RunState.new("run-1", now=now)

    assert state.to_dict() == {
        "schema_version": "1",
        "id": "run-1",
        "status": "queued",
        "created_at": "2026-08-12T12:00:00Z",
        "updated_at": "2026-08-12T12:00:00Z",
        "pid": None,
        "heartbeat_at": None,
        "progress": {"iteration": 0, "subcalls_completed": 0},
        "error": None,
    }


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (RunStatus.QUEUED, RunStatus.RUNNING),
        (RunStatus.QUEUED, RunStatus.CANCELLED),
        (RunStatus.QUEUED, RunStatus.ORPHANED),
        (RunStatus.RUNNING, RunStatus.SUCCEEDED),
        (RunStatus.RUNNING, RunStatus.FAILED),
        (RunStatus.RUNNING, RunStatus.CANCELLING),
        (RunStatus.RUNNING, RunStatus.ORPHANED),
        (RunStatus.CANCELLING, RunStatus.CANCELLED),
        (RunStatus.CANCELLING, RunStatus.FAILED),
    ],
)
def test_run_state_accepts_declared_transitions(
    source: RunStatus,
    target: RunStatus,
) -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    state = RunState(
        id="run-1",
        status=source,
        created_at=now,
        updated_at=now,
    )

    changed = state.transition(target, now=now + timedelta(seconds=1))

    assert changed.status is target
    assert changed.updated_at == now + timedelta(seconds=1)


def test_run_state_rejects_invalid_transition() -> None:
    state = RunState.new("run-1")

    with pytest.raises(StateConflictError, match="queued.*succeeded"):
        state.transition(RunStatus.SUCCEEDED)


@pytest.mark.parametrize("status", TERMINAL_STATUSES)
def test_terminal_state_rejects_every_transition(status: RunStatus) -> None:
    now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    state = RunState(
        id="run-1",
        status=status,
        created_at=now,
        updated_at=now,
    )

    with pytest.raises(StateConflictError, match="terminal"):
        state.transition(RunStatus.RUNNING)


def test_run_state_round_trips_json_values() -> None:
    original = RunState.new("run-1").transition(
        RunStatus.RUNNING,
        pid=1234,
        progress={"iteration": 2, "subcalls_completed": 1},
    )

    assert RunState.from_dict(original.to_dict()) == original


def test_success_envelope_has_stable_schema() -> None:
    assert success_envelope("status", run={"id": "run-1"}) == {
        "schema_version": "1",
        "ok": True,
        "command": "status",
        "run": {"id": "run-1"},
    }


def test_error_envelope_has_stable_schema() -> None:
    assert error_envelope("result", "RUN_NOT_FOUND", "missing", False) == {
        "schema_version": "1",
        "ok": False,
        "command": "result",
        "error": {"code": "RUN_NOT_FOUND", "message": "missing", "retryable": False},
    }
