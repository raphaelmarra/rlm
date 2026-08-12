import os
import shutil
import signal
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any, cast

from rlm.codex_tool.protocol import TERMINAL_STATUSES, RunState, RunStatus, StateConflictError
from rlm.codex_tool.runner import validate_request
from rlm.codex_tool.store import RunStore

HEARTBEAT_EXPIRY_SECONDS = 15.0


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, SystemError):
        return False
    return True


def signal_process_group(pid: int) -> None:
    if os.name == "nt":
        os.kill(pid, signal.CTRL_BREAK_EVENT)
    else:
        posix_os = cast(Any, os)
        posix_os.killpg(pid, signal.SIGTERM)


def force_terminate_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        posix_os = cast(Any, os)
        posix_signal = cast(Any, signal)
        posix_os.killpg(pid, posix_signal.SIGKILL)


class JobManager:
    def __init__(
        self,
        store: RunStore,
        *,
        popen_factory: Callable[..., Any] = subprocess.Popen,
        process_checker: Callable[[int], bool] = process_exists,
        signal_sender: Callable[[int], None] = signal_process_group,
        force_terminator: Callable[[int], None] = force_terminate_process_tree,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.popen_factory = popen_factory
        self.process_checker = process_checker
        self.signal_sender = signal_sender
        self.force_terminator = force_terminator
        self.sleeper = sleeper
        self.clock = clock or store.clock

    def start(self, request: Mapping[str, Any]) -> RunState:
        validated = validate_request(request)
        durable_request: dict[str, Any] = {
            "question": validated.question,
            "model": validated.model,
            "max_iterations": validated.max_iterations,
            "max_timeout": validated.max_timeout,
        }
        if "context_manifest" in request:
            durable_request["context_manifest"] = request["context_manifest"]
        state = self.store.create_run(durable_request, validated.context)
        run = self.store.paths.for_run(state.id)
        command = [
            sys.executable,
            "-m",
            "rlm.codex_tool.worker",
            state.id,
            "--home",
            str(self.store.paths.home),
        ]
        stdout_handle = run.worker_stdout.open("ab", buffering=0)
        stderr_handle = run.worker_stderr.open("ab", buffering=0)
        os.chmod(run.worker_stdout, 0o600)
        os.chmod(run.worker_stderr, 0o600)
        popen_kwargs: dict[str, Any] = {
            "stdin": subprocess.DEVNULL,
            "stdout": stdout_handle,
            "stderr": stderr_handle,
            "close_fds": True,
        }
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        try:
            process = self.popen_factory(command, **popen_kwargs)
        except Exception as error:
            failure = {"type": type(error).__name__, "message": str(error)}
            self.store.write_result(state.id, {"status": "orphaned", "error": failure})
            self.store.transition(
                state.id,
                RunStatus.ORPHANED,
                pid=None,
                error=failure,
            )
            raise
        finally:
            stdout_handle.close()
            stderr_handle.close()
        try:
            return self.store.update_runtime(state.id, pid=process.pid)
        except StateConflictError:
            observed = self.store.read_state(state.id)
            if observed.status in TERMINAL_STATUSES:
                return observed
            raise

    def status(self, run_id: str) -> RunState:
        state = self.store.read_state(run_id)
        if state.status in TERMINAL_STATUSES:
            return state
        last_seen = state.heartbeat_at or state.updated_at
        heartbeat_expired = (self.clock() - last_seen).total_seconds() > HEARTBEAT_EXPIRY_SECONDS
        worker_dead = heartbeat_expired and (
            state.pid is None or not self.process_checker(state.pid)
        )
        if heartbeat_expired and worker_dead:
            failure = {"type": "WorkerOrphaned", "message": "Worker heartbeat expired"}
            terminal = (
                RunStatus.FAILED if state.status is RunStatus.CANCELLING else RunStatus.ORPHANED
            )
            self.store.write_result(
                run_id,
                {"status": terminal.value, "error": failure},
            )
            return self.store.transition(
                run_id,
                terminal,
                pid=None,
                error=failure,
            )
        return state

    def events(self, run_id: str) -> list[dict[str, Any]]:
        self.status(run_id)
        return self.store.read_events(run_id)

    def result(
        self,
        run_id: str,
        *,
        wait: bool = False,
        wait_timeout: float = 900.0,
        poll_interval: float = 0.1,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + wait_timeout
        while True:
            state = self.status(run_id)
            if state.status in TERMINAL_STATUSES:
                return self.store.read_result(run_id)
            if not wait:
                raise StateConflictError(
                    f"Run '{run_id}' is still {state.status.value}; pass wait=True"
                )
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for run '{run_id}'")
            self.sleeper(poll_interval)

    def request_cancellation(self, run_id: str) -> None:
        run = self.store.require_run(run_id)
        try:
            with run.cancel_requested.open("x", encoding="utf-8") as handle:
                os.chmod(run.cancel_requested, 0o600)
                handle.write("cancel\n")
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            return

    def cancel(
        self,
        run_id: str,
        *,
        force: bool = False,
        grace_seconds: float = 30.0,
    ) -> RunState:
        state = self.status(run_id)
        if state.status in TERMINAL_STATUSES:
            raise StateConflictError(
                f"Run '{run_id}' is already terminal in state {state.status.value}"
            )
        self.request_cancellation(run_id)
        worker_pid = state.pid
        if state.status is RunStatus.QUEUED:
            state = self.store.transition(run_id, RunStatus.CANCELLED, pid=None)
            self.store.write_result(
                run_id,
                {"status": "cancelled", "partial_answer": None},
            )
        elif state.status is RunStatus.RUNNING:
            state = self.store.transition(run_id, RunStatus.CANCELLING)

        if worker_pid is not None:
            self.signal_sender(worker_pid)
        if not force or worker_pid is None:
            return state

        self.sleeper(grace_seconds)
        refreshed = self.store.read_state(run_id)
        if self.process_checker(worker_pid):
            self.force_terminator(worker_pid)
        if refreshed.status is RunStatus.CANCELLING:
            self.store.write_result(
                run_id,
                {"status": "cancelled", "partial_answer": None, "forced": True},
            )
            refreshed = self.store.transition(run_id, RunStatus.CANCELLED, pid=None)
        return refreshed

    def list_runs(self, status: RunStatus | None = None) -> list[RunState]:
        self.store.paths.ensure()
        states = [
            self.status(path.name) for path in self.store.paths.runs.iterdir() if path.is_dir()
        ]
        if status is not None:
            states = [state for state in states if state.status is status]
        return sorted(states, key=lambda state: state.created_at, reverse=True)

    def prune(self, *, older_than: timedelta) -> list[str]:
        if older_than.total_seconds() < 0:
            raise ValueError("older_than must not be negative")
        cutoff = self.clock() - older_than
        removed: list[str] = []
        for state in self.list_runs():
            if state.status not in TERMINAL_STATUSES or state.updated_at > cutoff:
                continue
            run = self.store.paths.for_run(state.id)
            if run.directory.resolve().parent != self.store.paths.runs.resolve():
                raise ValueError(f"Refusing to prune unsafe run path: {run.directory}")
            shutil.rmtree(run.directory)
            removed.append(state.id)
        return removed
