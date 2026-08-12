from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = "1"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ORPHANED = "orphaned"


TERMINAL_STATUSES = frozenset(
    {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.ORPHANED,
    }
)

ALLOWED_TRANSITIONS = {
    RunStatus.QUEUED: {RunStatus.RUNNING, RunStatus.CANCELLED, RunStatus.ORPHANED},
    RunStatus.RUNNING: {
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLING,
        RunStatus.ORPHANED,
    },
    RunStatus.CANCELLING: {RunStatus.CANCELLED, RunStatus.FAILED},
}

UNSET = object()


class StateConflictError(ValueError):
    """Raised when a job cannot move to the requested state."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def datetime_string(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Timestamps must include a timezone")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_datetime(value: Any, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a timestamp string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} is not a valid timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed.astimezone(UTC)


@dataclass(frozen=True)
class RunState:
    id: str
    status: RunStatus
    created_at: datetime
    updated_at: datetime
    pid: int | None = None
    heartbeat_at: datetime | None = None
    progress: dict[str, int] = field(
        default_factory=lambda: {"iteration": 0, "subcalls_completed": 0}
    )
    error: dict[str, Any] | None = None

    @classmethod
    def new(cls, run_id: str, *, now: datetime | None = None) -> "RunState":
        timestamp = now or utc_now()
        return cls(
            id=run_id,
            status=RunStatus.QUEUED,
            created_at=timestamp,
            updated_at=timestamp,
        )

    @property
    def created_at_string(self) -> str:
        return datetime_string(self.created_at)

    @property
    def updated_at_string(self) -> str:
        return datetime_string(self.updated_at)

    def transition(
        self,
        target: RunStatus,
        *,
        now: datetime | None = None,
        pid: int | None | object = UNSET,
        heartbeat_at: datetime | None | object = UNSET,
        progress: dict[str, int] | None = None,
        error: dict[str, Any] | None | object = UNSET,
    ) -> "RunState":
        if self.status in TERMINAL_STATUSES:
            raise StateConflictError(f"Run '{self.id}' is terminal in state {self.status.value}")
        if target not in ALLOWED_TRANSITIONS[self.status]:
            raise StateConflictError(
                f"Run '{self.id}' cannot transition from {self.status.value} to {target.value}"
            )

        changes: dict[str, Any] = {
            "status": target,
            "updated_at": now or utc_now(),
        }
        if pid is not UNSET:
            changes["pid"] = pid
        if heartbeat_at is not UNSET:
            changes["heartbeat_at"] = heartbeat_at
        if progress is not None:
            changes["progress"] = dict(progress)
        if error is not UNSET:
            changes["error"] = error
        return replace(self, **changes)

    def update_runtime(
        self,
        *,
        now: datetime | None = None,
        pid: int | None | object = UNSET,
        heartbeat_at: datetime | None | object = UNSET,
        progress: dict[str, int] | None = None,
    ) -> "RunState":
        if self.status in TERMINAL_STATUSES:
            raise StateConflictError(f"Run '{self.id}' is terminal in state {self.status.value}")
        changes: dict[str, Any] = {"updated_at": now or utc_now()}
        if pid is not UNSET:
            changes["pid"] = pid
        if heartbeat_at is not UNSET:
            changes["heartbeat_at"] = heartbeat_at
        if progress is not None:
            changes["progress"] = dict(progress)
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "id": self.id,
            "status": self.status.value,
            "created_at": self.created_at_string,
            "updated_at": self.updated_at_string,
            "pid": self.pid,
            "heartbeat_at": (
                datetime_string(self.heartbeat_at) if self.heartbeat_at is not None else None
            ),
            "progress": dict(self.progress),
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RunState":
        if value.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("Unsupported run state schema_version")
        run_id = value.get("id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("Run state id must be a non-empty string")
        pid = value.get("pid")
        if pid is not None and (not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0):
            raise ValueError("Run state pid must be a positive integer or null")
        progress = value.get("progress")
        if not isinstance(progress, dict) or not all(
            isinstance(item, int) and not isinstance(item, bool) and item >= 0
            for item in progress.values()
        ):
            raise ValueError("Run state progress must contain non-negative integers")
        heartbeat_value = value.get("heartbeat_at")
        return cls(
            id=run_id,
            status=RunStatus(value.get("status")),
            created_at=parse_datetime(value.get("created_at"), "created_at"),
            updated_at=parse_datetime(value.get("updated_at"), "updated_at"),
            pid=pid,
            heartbeat_at=(
                parse_datetime(heartbeat_value, "heartbeat_at")
                if heartbeat_value is not None
                else None
            ),
            progress=dict(progress),
            error=value.get("error"),
        )


def success_envelope(command: str, **payload: Any) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": True,
        "command": command,
        **payload,
    }


def error_envelope(
    command: str,
    code: str,
    message: str,
    retryable: bool,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "ok": False,
        "command": command,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
        },
    }
