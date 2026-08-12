import io
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from rlm.codex_tool.cli import main, run_doctor
from rlm.codex_tool.paths import CodexPaths
from rlm.codex_tool.protocol import RunState, RunStatus, StateConflictError
from rlm.codex_tool.store import RunStore


class FakeManager:
    def __init__(self) -> None:
        now = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
        self.state = RunState.new("run-1", now=now)
        self.calls: list[tuple[str, Any]] = []
        self.result_value: dict[str, Any] = {"status": "succeeded", "response": "answer"}

    def start(self, request):
        self.calls.append(("start", request))
        return self.state

    def status(self, run_id):
        self.calls.append(("status", run_id))
        return self.state

    def events(self, run_id):
        self.calls.append(("events", run_id))
        return [{"sequence": 1, "type": "status", "status": self.state.status.value}]

    def result(self, run_id, **kwargs):
        self.calls.append(("result", (run_id, kwargs)))
        return self.result_value

    def cancel(self, run_id, **kwargs):
        self.calls.append(("cancel", (run_id, kwargs)))
        self.state = self.state.transition(RunStatus.CANCELLED, pid=None)
        return self.state

    def list_runs(self, status=None):
        self.calls.append(("list", status))
        return [self.state]

    def prune(self, **kwargs):
        self.calls.append(("prune", kwargs))
        return ["old-run"]


def invoke(arguments: list[str], manager=None, doctor_runner=None):
    stdout = io.StringIO()
    exit_code = main(
        arguments,
        stdout=stdout,
        manager=manager,
        doctor_runner=doctor_runner,
    )
    return SimpleNamespace(
        returncode=exit_code,
        stdout=stdout.getvalue(),
        payload=json.loads(stdout.getvalue()),
    )


def test_doctor_reports_preflight_error_as_one_json_object() -> None:
    result = invoke(
        ["doctor"],
        doctor_runner=lambda: [
            {"name": "docker", "ok": False, "message": "Docker command not found"}
        ],
    )

    assert result.returncode == 3
    assert result.payload["ok"] is False
    assert result.payload["error"]["code"] == "PREFLIGHT_FAILED"
    assert result.payload["checks"][0]["name"] == "docker"
    assert result.stdout.count("\n") == 1


def test_doctor_success() -> None:
    result = invoke(
        ["doctor"],
        doctor_runner=lambda: [{"name": "account", "ok": True, "message": "chatgpt"}],
    )

    assert result.returncode == 0
    assert result.payload["ok"] is True
    assert result.payload["checks"][0]["ok"] is True


def test_doctor_reports_trusted_local_execution_without_docker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    checks = run_doctor(CodexPaths(tmp_path / "state"))
    by_name = {check["name"]: check for check in checks}

    assert by_name["execution_mode"] == {
        "name": "execution_mode",
        "ok": True,
        "message": "local trusted execution; not sandboxed",
    }
    assert not {"docker_command", "docker_daemon", "docker_image", "wsl"} & by_name.keys()


def test_start_snapshots_context_and_returns_run(tmp_path: Path) -> None:
    context = tmp_path / "notes.txt"
    context.write_text("context", encoding="utf-8")
    manager = FakeManager()

    result = invoke(
        [
            "start",
            "--question",
            "question",
            "--context-file",
            str(context),
            "--max-iterations",
            "4",
            "--max-timeout",
            "120",
        ],
        manager=manager,
    )

    assert result.returncode == 0
    assert result.payload["run"]["id"] == "run-1"
    request = manager.calls[0][1]
    assert request["context"] == {"notes.txt": "context"}
    assert request["context_manifest"][0]["sha256"]
    assert request["max_iterations"] == 4


def test_start_rejects_context_mode_conflict() -> None:
    result = invoke(
        [
            "start",
            "--question",
            "question",
            "--context-file",
            "notes.txt",
            "--context-text",
            "inline",
        ],
        manager=FakeManager(),
    )

    assert result.returncode == 2
    assert result.payload["error"]["code"] == "INVALID_INPUT"


@pytest.mark.parametrize(
    ("arguments", "command"),
    [
        (["status", "run-1"], "status"),
        (["events", "run-1"], "events"),
        (["result", "run-1", "--wait", "--wait-timeout", "10"], "result"),
        (["cancel", "run-1", "--force", "--grace-seconds", "0"], "cancel"),
        (["list", "--status", "queued"], "list"),
        (["prune", "--older-than", "7d"], "prune"),
    ],
)
def test_commands_emit_one_json_object(arguments: list[str], command: str) -> None:
    result = invoke(arguments, manager=FakeManager())

    assert result.returncode == 0
    assert result.payload["ok"] is True
    assert result.payload["command"] == command
    assert result.stdout.count("\n") == 1


def legacy_windows_stdout() -> tuple[io.BytesIO, io.TextIOWrapper]:
    buffer = io.BytesIO()
    return buffer, io.TextIOWrapper(buffer, encoding="cp1252")


def test_json_output_is_safe_for_legacy_windows_console_encoding() -> None:
    manager = FakeManager()
    manager.result_value["response"] = "approximately ≈"
    buffer, stdout = legacy_windows_stdout()

    exit_code = main(["result", "run-1"], stdout=stdout, manager=manager)
    stdout.flush()

    assert exit_code == 0
    assert json.loads(buffer.getvalue().decode("cp1252"))["result"]["response"] == (
        "approximately ≈"
    )


def test_jsonl_output_is_safe_for_legacy_windows_console_encoding() -> None:
    class TerminalManager(FakeManager):
        def events(self, run_id):
            return [{"sequence": 1, "message": "approximately ≈"}]

    manager = TerminalManager()
    manager.state = manager.state.transition(RunStatus.CANCELLED, pid=None)
    buffer, stdout = legacy_windows_stdout()

    exit_code = main(
        ["events", "run-1", "--follow"],
        stdout=stdout,
        manager=manager,
    )
    stdout.flush()

    assert exit_code == 0
    assert json.loads(buffer.getvalue().decode("cp1252"))["message"] == "approximately ≈"


def test_result_maps_failed_worker_to_exit_ten() -> None:
    manager = FakeManager()
    manager.state = manager.state.transition(RunStatus.RUNNING).transition(RunStatus.FAILED)
    manager.result_value = {"status": "failed", "error": {"message": "boom"}}

    result = invoke(["result", "run-1"], manager=manager)

    assert result.returncode == 10
    assert result.payload["ok"] is False
    assert result.payload["error"]["code"] == "WORKER_FAILED"
    assert result.payload["result"]["status"] == "failed"


def test_state_conflict_maps_to_exit_five() -> None:
    class ConflictManager(FakeManager):
        def result(self, run_id, **kwargs):
            raise StateConflictError("still running")

    result = invoke(["result", "run-1"], manager=ConflictManager())

    assert result.returncode == 5
    assert result.payload["error"]["code"] == "STATE_CONFLICT"


def test_unknown_run_maps_to_exit_four(tmp_path: Path) -> None:
    class MissingManager(FakeManager):
        def status(self, run_id):
            raise FileNotFoundError("missing")

    result = invoke(["status", "missing"], manager=MissingManager())

    assert result.returncode == 4
    assert result.payload["error"]["code"] == "RUN_NOT_FOUND"


def test_invalid_arguments_are_json_not_argparse_usage() -> None:
    result = invoke(["start"], manager=FakeManager())

    assert result.returncode == 2
    assert result.payload["error"]["code"] == "INVALID_ARGUMENTS"


def test_events_follow_emits_json_lines_until_terminal() -> None:
    class FollowManager(FakeManager):
        def __init__(self) -> None:
            super().__init__()
            self.event_calls = 0

        def events(self, run_id):
            self.event_calls += 1
            if self.event_calls == 1:
                return [{"sequence": 1, "type": "status", "status": "running"}]
            self.state = self.state.transition(RunStatus.RUNNING).transition(RunStatus.SUCCEEDED)
            return [
                {"sequence": 1, "type": "status", "status": "running"},
                {"sequence": 2, "type": "status", "status": "succeeded"},
            ]

    manager = FollowManager()
    stdout = io.StringIO()

    exit_code = main(
        ["events", "run-1", "--follow", "--wait-timeout", "1"],
        stdout=stdout,
        manager=manager,
        sleeper=lambda seconds: None,
    )

    lines = [json.loads(line) for line in stdout.getvalue().splitlines()]
    assert exit_code == 0
    assert [line["sequence"] for line in lines] == [1, 2]


def test_module_cli_status_works_in_subprocess(tmp_path: Path) -> None:
    home = tmp_path / "home"
    store = RunStore(CodexPaths(home))
    store.create_run({"question": "question"}, {"inline.txt": "context"}, run_id="run-1")
    environment = os.environ.copy()
    environment["RLM_CODEX_HOME"] = str(home)

    result = subprocess.run(
        [sys.executable, "-m", "rlm.codex_tool.cli", "status", "run-1"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["run"]["id"] == "run-1"
    assert result.stdout.count("\n") == 1
