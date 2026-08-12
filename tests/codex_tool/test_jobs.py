import os
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

import rlm.codex_tool.jobs as jobs_module
from rlm.codex_tool.jobs import JobManager
from rlm.codex_tool.paths import CodexPaths
from rlm.codex_tool.protocol import RunStatus, StateConflictError
from rlm.codex_tool.store import RunStore


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


class FakeProcess:
    pid = 4321


class FakePopen:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []

    def __call__(self, command: list[str], **kwargs: Any) -> FakeProcess:
        self.calls.append((command, kwargs))
        return FakeProcess()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def store(tmp_path: Path, clock: Clock) -> RunStore:
    return RunStore(CodexPaths(tmp_path / "home"), clock=clock)


def valid_request() -> dict[str, Any]:
    return {
        "question": "question",
        "model": "gpt-5.6-terra",
        "max_iterations": 6,
        "max_timeout": 600,
        "context": {"notes.txt": "context"},
        "context_manifest": [{"name": "notes.txt", "sha256": "0" * 64}],
    }


def test_start_returns_queued_run_and_worker_pid(store: RunStore, clock: Clock) -> None:
    popen = FakePopen()
    manager = JobManager(store, popen_factory=popen, clock=clock)

    run = manager.start(valid_request())

    assert run.status is RunStatus.QUEUED
    assert run.pid == 4321
    assert store.read_request(run.id)["question"] == "question"
    assert "context" not in store.read_request(run.id)
    assert store.read_context(run.id) == {"notes.txt": "context"}
    command, kwargs = popen.calls[0]
    assert command[:3] == [sys.executable, "-m", "rlm.codex_tool.worker"]
    assert str(store.paths.home) in command
    assert kwargs["stdin"] is subprocess.DEVNULL
    if os.name == "nt":
        assert kwargs["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        assert kwargs["start_new_session"] is True


def test_start_rejects_api_key_before_creating_run_or_worker(
    store: RunStore,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    popen = FakePopen()
    manager = JobManager(store, popen_factory=popen, clock=clock)

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        manager.start(valid_request())

    assert popen.calls == []
    assert not store.paths.runs.exists()


def test_start_tolerates_worker_finishing_before_pid_snapshot(
    store: RunStore,
    clock: Clock,
) -> None:
    class FinishingPopen:
        def __call__(self, command: list[str], **kwargs: Any) -> FakeProcess:
            run_id = command[3]
            store.transition(run_id, RunStatus.RUNNING, pid=4321, heartbeat_at=clock.now)
            store.write_result(run_id, {"status": "succeeded", "response": "fast"})
            store.transition(run_id, RunStatus.SUCCEEDED, pid=None)
            return FakeProcess()

    manager = JobManager(store, popen_factory=FinishingPopen(), clock=clock)

    state = manager.start(valid_request())

    assert state.status is RunStatus.SUCCEEDED
    assert state.pid is None


def test_status_marks_expired_dead_pid_orphaned(store: RunStore, clock: Clock) -> None:
    state = store.create_run(
        {"question": "question"},
        {"notes.txt": "context"},
        run_id="run-1",
    )
    store.transition(
        state.id,
        RunStatus.RUNNING,
        pid=999999,
        heartbeat_at=clock.now,
    )
    clock.now += timedelta(seconds=16)
    manager = JobManager(store, process_checker=lambda pid: False, clock=clock)

    observed = manager.status(state.id)

    assert observed.status is RunStatus.ORPHANED
    assert observed.pid is None


def test_status_keeps_live_or_fresh_worker_running(store: RunStore, clock: Clock) -> None:
    state = store.create_run(
        {"question": "question"},
        {"notes.txt": "context"},
        run_id="run-1",
    )
    store.transition(
        state.id,
        RunStatus.RUNNING,
        pid=1234,
        heartbeat_at=clock.now,
    )
    clock.now += timedelta(seconds=20)
    manager = JobManager(store, process_checker=lambda pid: True, clock=clock)

    assert manager.status(state.id).status is RunStatus.RUNNING


def test_cancel_running_records_intent_and_signals_worker(
    store: RunStore,
    clock: Clock,
) -> None:
    state = store.create_run(
        {"question": "question"},
        {"notes.txt": "context"},
        run_id="run-1",
    )
    store.transition(state.id, RunStatus.RUNNING, pid=1234, heartbeat_at=clock.now)
    signalled: list[int] = []
    manager = JobManager(store, signal_sender=signalled.append, clock=clock)

    cancelled = manager.cancel(state.id)

    assert cancelled.status is RunStatus.CANCELLING
    assert signalled == [1234]
    assert store.paths.for_run(state.id).cancel_requested.exists()


def test_cancel_queued_transitions_directly_to_cancelled(
    store: RunStore,
    clock: Clock,
) -> None:
    state = store.create_run(
        {"question": "question"},
        {"notes.txt": "context"},
        run_id="run-1",
    )
    store.update_runtime(state.id, pid=1234)
    signalled: list[int] = []
    manager = JobManager(store, signal_sender=signalled.append, clock=clock)

    cancelled = manager.cancel(state.id)

    assert cancelled.status is RunStatus.CANCELLED
    assert cancelled.pid is None
    assert signalled == [1234]


def test_force_cancel_terminates_only_the_local_process_tree(
    store: RunStore,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = store.create_run(
        {"question": "question"},
        {"notes.txt": "context"},
        run_id="run-1",
    )
    store.transition(state.id, RunStatus.RUNNING, pid=1234, heartbeat_at=clock.now)
    forced: list[int] = []
    external_calls: list[list[str]] = []

    def record_external_call(command: list[str], **kwargs: Any) -> Any:
        external_calls.append(command)
        return type("Result", (), {"stdout": ""})()

    monkeypatch.setattr(shutil, "which", lambda command: "docker")
    monkeypatch.setattr(jobs_module.subprocess, "run", record_external_call)
    manager = JobManager(
        store,
        signal_sender=lambda pid: None,
        force_terminator=forced.append,
        process_checker=lambda pid: True,
        sleeper=lambda seconds: None,
        clock=clock,
    )

    state = manager.cancel(state.id, force=True, grace_seconds=0)

    assert forced == [1234]
    assert external_calls == []
    assert state.status is RunStatus.CANCELLED
    assert state.pid is None


def test_result_requires_terminal_state_without_wait(store: RunStore, clock: Clock) -> None:
    state = store.create_run(
        {"question": "question"},
        {"notes.txt": "context"},
        run_id="run-1",
    )
    manager = JobManager(store, clock=clock)

    with pytest.raises(StateConflictError, match="still queued"):
        manager.result(state.id)


def test_list_runs_is_newest_first_and_filterable(store: RunStore, clock: Clock) -> None:
    first = store.create_run({"question": "one"}, {"x": "1"}, run_id="run-1")
    clock.now += timedelta(seconds=1)
    second = store.create_run({"question": "two"}, {"x": "2"}, run_id="run-2")
    store.transition(first.id, RunStatus.CANCELLED)
    manager = JobManager(store, clock=clock)

    assert [state.id for state in manager.list_runs()] == [second.id, first.id]
    assert [state.id for state in manager.list_runs(RunStatus.CANCELLED)] == [first.id]


def test_prune_removes_only_old_terminal_runs(store: RunStore, clock: Clock) -> None:
    old = store.create_run({"question": "old"}, {"x": "1"}, run_id="old-run")
    store.transition(old.id, RunStatus.CANCELLED)
    active = store.create_run({"question": "active"}, {"x": "2"}, run_id="active-run")
    clock.now += timedelta(days=8)
    manager = JobManager(store, clock=clock)

    removed = manager.prune(older_than=timedelta(days=7))

    assert removed == [old.id]
    assert not store.paths.for_run(old.id).directory.exists()
    assert store.paths.for_run(active.id).directory.exists()
