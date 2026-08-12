import importlib
import json
import os
import shutil
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from rlm.codex_tool.paths import CodexPaths, RunPaths
from rlm.codex_tool.protocol import UNSET, RunState, RunStatus, datetime_string


class RunNotFoundError(FileNotFoundError):
    """Raised when no durable job exists for a run id."""


class StoreCorruptionError(ValueError):
    """Raised when a durable artifact is not valid JSON or has an invalid schema."""


def atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8") as handle:
            os.chmod(temporary, 0o600)
            json.dump(value, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def exclusive_file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        os.chmod(path, 0o600)
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            fcntl = cast(Any, importlib.import_module("fcntl"))
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class RunStore:
    def __init__(self, paths: CodexPaths) -> None:
        self.paths = paths

    def create_run(
        self,
        request: Mapping[str, Any],
        context: Mapping[str, Any],
        *,
        run_id: str | None = None,
    ) -> RunState:
        self.paths.ensure()
        selected_id = run_id or self.new_run_id()
        run = self.paths.for_run(selected_id)
        run.directory.mkdir(mode=0o700)
        os.chmod(run.directory, 0o700)
        try:
            with exclusive_file_lock(run.lock):
                state = RunState.new(selected_id)
                atomic_write_json(run.request, request)
                atomic_write_json(run.context, context)
                atomic_write_json(run.state, state.to_dict())
                self.append_event_locked(
                    run,
                    {
                        "schema_version": "1",
                        "sequence": 1,
                        "run_id": selected_id,
                        "type": "status",
                        "status": state.status.value,
                        "created_at": state.created_at_string,
                    },
                )
                return state
        except Exception:
            shutil.rmtree(run.directory)
            raise

    def new_run_id(self) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return f"{timestamp}-{uuid.uuid4().hex[:8]}"

    def require_run(self, run_id: str) -> RunPaths:
        run = self.paths.for_run(run_id)
        if not run.directory.is_dir():
            raise RunNotFoundError(f"Run '{run_id}' was not found")
        return run

    def read_json(self, path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StoreCorruptionError(f"Could not read valid JSON from {path.name}") from error
        if not isinstance(value, dict):
            raise StoreCorruptionError(f"Expected a JSON object in {path.name}")
        return value

    def read_state(self, run_id: str) -> RunState:
        run = self.require_run(run_id)
        try:
            return RunState.from_dict(self.read_json(run.state))
        except (TypeError, ValueError) as error:
            if isinstance(error, StoreCorruptionError):
                raise
            raise StoreCorruptionError(f"Invalid run state in {run.state.name}") from error

    def transition(
        self,
        run_id: str,
        target: RunStatus,
        *,
        pid: int | None | object = UNSET,
        progress: dict[str, int] | None = None,
        error: dict[str, Any] | None = None,
    ) -> RunState:
        run = self.require_run(run_id)
        with exclusive_file_lock(run.lock):
            state = self.read_state(run_id)
            transition_kwargs: dict[str, Any] = {"progress": progress}
            if pid is not UNSET:
                transition_kwargs["pid"] = pid
            if error is not None:
                transition_kwargs["error"] = error
            changed = state.transition(target, **transition_kwargs)
            atomic_write_json(run.state, changed.to_dict())
            self.append_event_locked(
                run,
                {
                    "schema_version": "1",
                    "sequence": self.next_event_sequence(run),
                    "run_id": run_id,
                    "type": "status",
                    "status": changed.status.value,
                    "created_at": changed.updated_at_string,
                },
            )
            return changed

    def append_event(self, run_id: str, event: Mapping[str, Any]) -> dict[str, Any]:
        run = self.require_run(run_id)
        with exclusive_file_lock(run.lock):
            complete_event = {
                "schema_version": "1",
                "sequence": self.next_event_sequence(run),
                "run_id": run_id,
                "created_at": datetime_string(datetime.now(UTC)),
                **event,
            }
            self.append_event_locked(run, complete_event)
            return complete_event

    def append_event_locked(self, run: RunPaths, event: Mapping[str, Any]) -> None:
        with run.events.open("a", encoding="utf-8", newline="\n") as handle:
            os.chmod(run.events, 0o600)
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def next_event_sequence(self, run: RunPaths) -> int:
        return len(self.read_events_from_path(run.events)) + 1

    def read_events_from_path(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        try:
            for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise StoreCorruptionError(
                        f"Expected a JSON object in {path.name} line {line_number}"
                    )
                events.append(value)
        except (OSError, json.JSONDecodeError) as error:
            raise StoreCorruptionError(
                f"Could not read valid JSON Lines from {path.name}"
            ) from error
        return events

    def read_events(self, run_id: str) -> list[dict[str, Any]]:
        return self.read_events_from_path(self.require_run(run_id).events)

    def write_result(self, run_id: str, result: Mapping[str, Any]) -> None:
        run = self.require_run(run_id)
        with exclusive_file_lock(run.lock):
            atomic_write_json(run.result, result)

    def read_result(self, run_id: str) -> dict[str, Any]:
        return self.read_json(self.require_run(run_id).result)

    def read_request(self, run_id: str) -> dict[str, Any]:
        return self.read_json(self.require_run(run_id).request)

    def read_context(self, run_id: str) -> dict[str, Any]:
        return self.read_json(self.require_run(run_id).context)
