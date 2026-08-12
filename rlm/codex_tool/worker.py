import argparse
import os
import re
import signal
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import Any

from rlm.codex_tool.paths import CodexPaths
from rlm.codex_tool.protocol import TERMINAL_STATUSES, RunStatus, StateConflictError, utc_now
from rlm.codex_tool.runner import Callbacks, run_rlm
from rlm.codex_tool.store import RunStore
from rlm.core.types import RLMChatCompletion
from rlm.utils.exceptions import CancellationError

WORKER_FAILURE_EXIT_CODE = 10
TOKEN_PATTERN = re.compile(r"(?i)(Bearer\s+)[^\s]+|(sk-[A-Za-z0-9_-]+)")
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def sanitize_message(message: str) -> str:
    redacted = TOKEN_PATTERN.sub(lambda match: f"{match.group(1) or ''}[REDACTED]", message)
    return EMAIL_PATTERN.sub("[REDACTED_EMAIL]", redacted)


def serialize_completion(completion: RLMChatCompletion) -> dict[str, Any]:
    usage = completion.usage_summary.to_dict()
    usage["total_cost"] = completion.usage_summary.total_cost
    return {
        "status": "succeeded",
        "root_model": completion.root_model,
        "response": completion.response,
        "usage_summary": usage,
        "execution_time": completion.execution_time,
        "metadata": completion.metadata,
    }


def install_signal_handlers() -> list[tuple[signal.Signals, Any]]:
    installed: list[tuple[signal.Signals, Any]] = []

    def request_cancellation(signum: int, frame: FrameType | None) -> None:
        raise KeyboardInterrupt

    handled = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGBREAK"):
        handled.append(signal.SIGBREAK)
    for selected_signal in handled:
        previous = signal.getsignal(selected_signal)
        signal.signal(selected_signal, request_cancellation)
        installed.append((selected_signal, previous))
    return installed


def restore_signal_handlers(installed: list[tuple[signal.Signals, Any]]) -> None:
    for selected_signal, previous in installed:
        signal.signal(selected_signal, previous)


def build_callbacks(store: RunStore, run_id: str) -> Callbacks:
    def iteration_start(depth: int, iteration: int) -> None:
        state = store.read_state(run_id)
        progress = dict(state.progress)
        progress["iteration"] = max(progress["iteration"], iteration)
        store.update_runtime(run_id, progress=progress)
        store.append_event(
            run_id,
            {"type": "iteration_started", "depth": depth, "iteration": iteration},
        )

    def iteration_complete(depth: int, iteration: int, elapsed: float) -> None:
        store.append_event(
            run_id,
            {
                "type": "iteration_completed",
                "depth": depth,
                "iteration": iteration,
                "elapsed_seconds": elapsed,
            },
        )

    def subcall_start(depth: int, model: str, prompt_preview: str) -> None:
        store.append_event(
            run_id,
            {
                "type": "subcall_started",
                "depth": depth,
                "model": model,
                "prompt_preview": sanitize_message(prompt_preview),
            },
        )

    def subcall_complete(
        depth: int,
        model: str,
        elapsed: float,
        error: str | None,
    ) -> None:
        state = store.read_state(run_id)
        progress = dict(state.progress)
        progress["subcalls_completed"] += 1
        store.update_runtime(run_id, progress=progress)
        store.append_event(
            run_id,
            {
                "type": "subcall_completed",
                "depth": depth,
                "model": model,
                "elapsed_seconds": elapsed,
                "error": sanitize_message(error) if error else None,
            },
        )

    return Callbacks(
        on_iteration_start=iteration_start,
        on_iteration_complete=iteration_complete,
        on_subcall_start=subcall_start,
        on_subcall_complete=subcall_complete,
    )


def heartbeat_loop(
    store: RunStore,
    run_id: str,
    stop: threading.Event,
    interval: float,
    clock: Callable[[], datetime],
) -> None:
    while not stop.wait(interval):
        try:
            store.update_runtime(run_id, heartbeat_at=clock())
        except StateConflictError:
            return


def cancellation_result(error: BaseException) -> dict[str, Any]:
    partial_answer = getattr(error, "partial_answer", None)
    return {"status": "cancelled", "partial_answer": partial_answer}


def finish_cancelled(store: RunStore, run_id: str, error: BaseException) -> None:
    state = store.read_state(run_id)
    if state.status is RunStatus.RUNNING:
        state = store.transition(run_id, RunStatus.CANCELLING)
    store.write_result(run_id, cancellation_result(error))
    if state.status is RunStatus.CANCELLING:
        store.transition(run_id, RunStatus.CANCELLED, pid=None, heartbeat_at=store.clock())


def worker_main(
    run_id: str,
    home: str | Path,
    *,
    run_function: Callable[[Mapping[str, Any], Callbacks], RLMChatCompletion] = run_rlm,
    heartbeat_interval: float = 2.0,
    clock: Callable[[], datetime] = utc_now,
) -> int:
    store = RunStore(CodexPaths(Path(home)), clock=clock)
    state = store.read_state(run_id)
    if state.status in TERMINAL_STATUSES:
        return 0

    request = store.read_request(run_id)
    context = store.read_context(run_id)
    request_with_context = {**request, "context": context, "run_id": run_id}
    installed_handlers = install_signal_handlers()
    heartbeat_stop = threading.Event()
    heartbeat_thread: threading.Thread | None = None

    def stop_heartbeat() -> None:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=max(heartbeat_interval * 2, 1.0))

    try:
        try:
            store.transition(
                run_id,
                RunStatus.RUNNING,
                pid=os.getpid(),
                heartbeat_at=clock(),
            )
        except StateConflictError:
            if store.read_state(run_id).status in TERMINAL_STATUSES:
                return 0
            raise
        heartbeat_thread = threading.Thread(
            target=heartbeat_loop,
            args=(store, run_id, heartbeat_stop, heartbeat_interval, clock),
            name=f"rlm-codex-heartbeat-{run_id}",
            daemon=True,
        )
        heartbeat_thread.start()
        completion = run_function(request_with_context, build_callbacks(store, run_id))
        if store.paths.for_run(run_id).cancel_requested.exists():
            raise CancellationError(message="Cancellation requested")
        stop_heartbeat()
        store.write_result(run_id, serialize_completion(completion))
        store.transition(
            run_id,
            RunStatus.SUCCEEDED,
            pid=None,
            heartbeat_at=clock(),
        )
        return 0
    except (CancellationError, KeyboardInterrupt) as error:
        stop_heartbeat()
        finish_cancelled(store, run_id, error)
        return 0
    except Exception as error:
        stop_heartbeat()
        sanitized_error = {
            "type": type(error).__name__,
            "message": sanitize_message(str(error)),
        }
        store.write_result(run_id, {"status": "failed", "error": sanitized_error})
        current = store.read_state(run_id)
        if current.status not in TERMINAL_STATUSES:
            store.transition(
                run_id,
                RunStatus.FAILED,
                pid=None,
                heartbeat_at=clock(),
                error=sanitized_error,
            )
        return WORKER_FAILURE_EXIT_CODE
    finally:
        stop_heartbeat()
        restore_signal_handlers(installed_handlers)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m rlm.codex_tool.worker")
    parser.add_argument("run_id")
    parser.add_argument("--home", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    return worker_main(arguments.run_id, arguments.home)


if __name__ == "__main__":
    raise SystemExit(main())
