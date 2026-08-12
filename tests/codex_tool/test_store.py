import json
import os
import stat
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from rlm.codex_tool.paths import CodexPaths
from rlm.codex_tool.protocol import RunStatus, StateConflictError
from rlm.codex_tool.store import RunNotFoundError, RunStore, StoreCorruptionError


@pytest.fixture
def paths(tmp_path: Path) -> CodexPaths:
    return CodexPaths(tmp_path / "rlm-codex")


@pytest.fixture
def store(paths: CodexPaths) -> RunStore:
    return RunStore(paths)


def test_paths_use_environment_override(tmp_path: Path) -> None:
    home = tmp_path / "custom-home"

    paths = CodexPaths.from_environment({"RLM_CODEX_HOME": str(home)})

    assert paths.home == home.resolve()
    assert paths.runs == home.resolve() / "runs"


def test_paths_reject_run_id_traversal(paths: CodexPaths) -> None:
    with pytest.raises(ValueError, match="run id"):
        paths.for_run("../outside")


def test_create_run_writes_snapshots_state_and_initial_event(
    store: RunStore,
    paths: CodexPaths,
) -> None:
    state = store.create_run(
        request={"question": "what?", "model": "gpt-5.6-terra"},
        context={"notes.txt": "context"},
        run_id="run-1",
    )
    run = paths.for_run("run-1")

    assert state.status is RunStatus.QUEUED
    assert json.loads(run.request.read_text(encoding="utf-8"))["question"] == "what?"
    assert json.loads(run.context.read_text(encoding="utf-8")) == {"notes.txt": "context"}
    assert store.read_state("run-1") == state
    assert store.read_events("run-1") == [
        {
            "schema_version": "1",
            "sequence": 1,
            "run_id": "run-1",
            "type": "status",
            "status": "queued",
            "created_at": state.created_at_string,
        }
    ]


def test_atomic_writes_leave_no_temporary_files(store: RunStore, paths: CodexPaths) -> None:
    store.create_run({"question": "what?"}, {"inline": "context"}, run_id="run-1")
    store.transition("run-1", RunStatus.RUNNING, pid=1234)
    store.write_result("run-1", {"response": "answer"})

    run = paths.for_run("run-1")
    assert json.loads(run.state.read_text(encoding="utf-8"))["status"] == "running"
    assert json.loads(run.result.read_text(encoding="utf-8")) == {"response": "answer"}
    assert list(run.directory.glob("*.tmp")) == []
    assert list(run.directory.glob(".*.tmp")) == []


def test_transition_persists_state_and_event(store: RunStore) -> None:
    store.create_run({"question": "what?"}, {"inline": "context"}, run_id="run-1")

    state = store.transition(
        "run-1",
        RunStatus.RUNNING,
        pid=4321,
        progress={"iteration": 1, "subcalls_completed": 0},
    )

    assert store.read_state("run-1") == state
    assert state.pid == 4321
    assert store.read_events("run-1")[-1]["status"] == "running"
    assert store.read_events("run-1")[-1]["sequence"] == 2


def test_terminal_transition_can_clear_worker_pid(store: RunStore) -> None:
    store.create_run({"question": "what?"}, {"inline": "context"}, run_id="run-1")
    store.transition("run-1", RunStatus.RUNNING, pid=4321)

    state = store.transition("run-1", RunStatus.SUCCEEDED, pid=None)

    assert state.pid is None


def test_concurrent_transition_has_one_winner(store: RunStore) -> None:
    store.create_run({"question": "what?"}, {"inline": "context"}, run_id="run-1")

    def transition() -> str:
        try:
            return store.transition("run-1", RunStatus.RUNNING).status.value
        except StateConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: transition(), range(2)))

    assert sorted(results) == ["conflict", "running"]
    assert [event["status"] for event in store.read_events("run-1")] == [
        "queued",
        "running",
    ]


def test_read_state_reports_corruption(store: RunStore, paths: CodexPaths) -> None:
    store.create_run({"question": "what?"}, {"inline": "context"}, run_id="run-1")
    paths.for_run("run-1").state.write_text("{broken", encoding="utf-8")

    with pytest.raises(StoreCorruptionError, match="state.json"):
        store.read_state("run-1")


def test_missing_run_is_distinct_from_corruption(store: RunStore) -> None:
    with pytest.raises(RunNotFoundError, match="missing"):
        store.read_state("missing")


def test_write_and_read_result(store: RunStore) -> None:
    store.create_run({"question": "what?"}, {"inline": "context"}, run_id="run-1")

    store.write_result("run-1", {"response": "answer", "usage": {"calls": 2}})

    assert store.read_result("run-1") == {"response": "answer", "usage": {"calls": 2}}


@pytest.mark.skipif(os.name == "nt", reason="Windows does not enforce POSIX mode bits")
def test_snapshots_are_user_only(store: RunStore, paths: CodexPaths) -> None:
    store.create_run({"question": "what?"}, {"inline": "context"}, run_id="run-1")
    run = paths.for_run("run-1")

    assert stat.S_IMODE(run.directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(run.request.stat().st_mode) == 0o600
    assert stat.S_IMODE(run.context.stat().st_mode) == 0o600
