import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


@dataclass(frozen=True)
class RunPaths:
    directory: Path

    @property
    def request(self) -> Path:
        return self.directory / "request.json"

    @property
    def context(self) -> Path:
        return self.directory / "context.json"

    @property
    def state(self) -> Path:
        return self.directory / "state.json"

    @property
    def events(self) -> Path:
        return self.directory / "events.jsonl"

    @property
    def result(self) -> Path:
        return self.directory / "result.json"

    @property
    def worker_stdout(self) -> Path:
        return self.directory / "worker.stdout.log"

    @property
    def worker_stderr(self) -> Path:
        return self.directory / "worker.stderr.log"

    @property
    def cancel_requested(self) -> Path:
        return self.directory / "cancel.requested"

    @property
    def lock(self) -> Path:
        return self.directory / ".lock"


@dataclass(frozen=True)
class CodexPaths:
    home: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "home", self.home.expanduser().resolve())

    @property
    def runs(self) -> Path:
        return self.home / "runs"

    @classmethod
    def from_environment(cls, environment: Mapping[str, str] | None = None) -> "CodexPaths":
        values = environment if environment is not None else os.environ
        override = values.get("RLM_CODEX_HOME")
        if override:
            return cls(Path(override))
        if os.name == "nt":
            local_app_data = values.get("LOCALAPPDATA")
            if not local_app_data:
                raise ValueError("LOCALAPPDATA is required when RLM_CODEX_HOME is unset")
            return cls(Path(local_app_data) / "rlm-codex")
        xdg_state_home = values.get("XDG_STATE_HOME")
        base = Path(xdg_state_home) if xdg_state_home else Path.home() / ".local" / "state"
        return cls(base / "rlm-codex")

    def ensure(self) -> None:
        self.runs.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.home, 0o700)
        os.chmod(self.runs, 0o700)

    def for_run(self, run_id: str) -> RunPaths:
        if not RUN_ID_PATTERN.fullmatch(run_id):
            raise ValueError(f"Invalid run id: {run_id!r}")
        return RunPaths(self.runs / run_id)
