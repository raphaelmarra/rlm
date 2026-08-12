import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import timedelta
from pathlib import Path
from typing import Any, NoReturn, Protocol, TextIO

from rlm.codex_tool.jobs import JobManager
from rlm.codex_tool.paths import CodexPaths
from rlm.codex_tool.protocol import (
    TERMINAL_STATUSES,
    RunState,
    RunStatus,
    StateConflictError,
    error_envelope,
    success_envelope,
)
from rlm.codex_tool.runner import (
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_MAX_TIMEOUT,
    DEFAULT_MODEL,
    snapshot_context,
)
from rlm.codex_tool.store import RunStore
from rlm.codex_tool.worker import sanitize_message

EXIT_OK = 0
EXIT_INVALID_INPUT = 2
EXIT_PREFLIGHT = 3
EXIT_NOT_FOUND = 4
EXIT_CONFLICT = 5
EXIT_WORKER_FAILED = 10
DURATION_PATTERN = re.compile(r"^(\d+(?:\.\d+)?)([smhd])$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SKILL_MANIFEST_NAME = ".rlm-codex-origin.json"


class ArgumentParsingError(ValueError):
    """Raised instead of letting argparse print unstructured usage text."""


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ArgumentParsingError(message)


class JobManagerProtocol(Protocol):
    def start(self, request: Mapping[str, Any]) -> RunState: ...

    def status(self, run_id: str) -> RunState: ...

    def events(self, run_id: str) -> list[dict[str, Any]]: ...

    def result(
        self,
        run_id: str,
        *,
        wait: bool = False,
        wait_timeout: float = 900.0,
        poll_interval: float = 0.1,
    ) -> dict[str, Any]: ...

    def cancel(
        self,
        run_id: str,
        *,
        force: bool = False,
        grace_seconds: float = 30.0,
    ) -> RunState: ...

    def list_runs(self, status: RunStatus | None = None) -> list[RunState]: ...

    def prune(self, *, older_than: timedelta) -> list[str]: ...


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="rlm-codex")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("doctor")

    start = subparsers.add_parser("start")
    start.add_argument("--question", required=True)
    start.add_argument("--context-file", action="append", type=Path)
    start.add_argument("--context-text")
    start.add_argument("--model", default=DEFAULT_MODEL)
    start.add_argument("--max-iterations", type=int, default=DEFAULT_MAX_ITERATIONS)
    start.add_argument("--max-timeout", type=float, default=DEFAULT_MAX_TIMEOUT)

    status = subparsers.add_parser("status")
    status.add_argument("run_id")

    events = subparsers.add_parser("events")
    events.add_argument("run_id")
    events.add_argument("--follow", action="store_true")
    events.add_argument("--wait-timeout", type=float, default=900.0)

    result = subparsers.add_parser("result")
    result.add_argument("run_id")
    result.add_argument("--wait", action="store_true")
    result.add_argument("--wait-timeout", type=float, default=900.0)

    cancel = subparsers.add_parser("cancel")
    cancel.add_argument("run_id")
    cancel.add_argument("--force", action="store_true")
    cancel.add_argument("--grace-seconds", type=float, default=30.0)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--status", choices=[status.value for status in RunStatus])

    prune = subparsers.add_parser("prune")
    prune.add_argument("--older-than", default="7d")
    return parser


def parse_duration(value: str) -> timedelta:
    match = DURATION_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("older-than must use a positive duration such as 7d, 12h, 30m, or 60s")
    amount = float(match.group(1))
    if amount <= 0:
        raise ValueError("older-than must be greater than zero")
    seconds_per_unit = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return timedelta(seconds=amount * seconds_per_unit[match.group(2)])


def state_payload(state: RunState) -> dict[str, Any]:
    return state.to_dict()


def dispatch(
    arguments: argparse.Namespace,
    manager: JobManagerProtocol,
    doctor_runner: Callable[[], list[dict[str, Any]]],
) -> tuple[dict[str, Any], int]:
    command = arguments.command
    if command == "doctor":
        checks = doctor_runner()
        failures = [check for check in checks if not check["ok"]]
        if failures:
            payload = error_envelope(
                command,
                "PREFLIGHT_FAILED",
                f"{len(failures)} preflight check(s) failed",
                True,
            )
            payload["checks"] = checks
            return payload, EXIT_PREFLIGHT
        return success_envelope(command, checks=checks), EXIT_OK

    if command == "start":
        try:
            snapshot = snapshot_context(
                context_files=arguments.context_file,
                context_text=arguments.context_text,
            )
        except OSError as error:
            raise ValueError(f"Could not snapshot context: {error}") from error
        state = manager.start(
            {
                "question": arguments.question,
                "model": arguments.model,
                "max_iterations": arguments.max_iterations,
                "max_timeout": arguments.max_timeout,
                "context": snapshot.content,
                "context_manifest": snapshot.manifest,
            }
        )
        return success_envelope(command, run=state_payload(state)), EXIT_OK

    if command == "status":
        state = manager.status(arguments.run_id)
        return success_envelope(command, run=state_payload(state)), EXIT_OK

    if command == "events":
        events = manager.events(arguments.run_id)
        return success_envelope(command, events=events), EXIT_OK

    if command == "result":
        result = manager.result(
            arguments.run_id,
            wait=arguments.wait,
            wait_timeout=arguments.wait_timeout,
        )
        if result.get("status") in {RunStatus.FAILED.value, RunStatus.ORPHANED.value}:
            payload = error_envelope(
                command,
                "WORKER_FAILED",
                result.get("error", {}).get("message", "Worker failed"),
                False,
            )
            payload["result"] = result
            return payload, EXIT_WORKER_FAILED
        return success_envelope(command, result=result), EXIT_OK

    if command == "cancel":
        if arguments.grace_seconds < 0:
            raise ValueError("grace-seconds must not be negative")
        state = manager.cancel(
            arguments.run_id,
            force=arguments.force,
            grace_seconds=arguments.grace_seconds,
        )
        return success_envelope(command, run=state_payload(state)), EXIT_OK

    if command == "list":
        selected_status = RunStatus(arguments.status) if arguments.status else None
        states = manager.list_runs(selected_status)
        return success_envelope(
            command,
            runs=[state_payload(state) for state in states],
        ), EXIT_OK

    if command == "prune":
        removed = manager.prune(older_than=parse_duration(arguments.older_than))
        return success_envelope(command, removed_run_ids=removed), EXIT_OK

    raise ValueError(f"Unsupported command: {command}")


def follow_events(
    manager: JobManagerProtocol,
    run_id: str,
    *,
    wait_timeout: float,
    stdout: TextIO,
    sleeper: Callable[[float], None],
) -> int:
    if wait_timeout <= 0:
        raise ValueError("wait-timeout must be greater than zero")
    deadline = time.monotonic() + wait_timeout
    emitted = 0
    while True:
        events = manager.events(run_id)
        for event in events[emitted:]:
            stdout.write(json.dumps(event, ensure_ascii=False) + "\n")
            stdout.flush()
        emitted = len(events)
        state = manager.status(run_id)
        if state.status in TERMINAL_STATUSES:
            return EXIT_OK
        if time.monotonic() >= deadline:
            raise StateConflictError(f"Timed out following events for run '{run_id}'")
        sleeper(0.25)


def diagnostic(name: str, ok: bool, message: str) -> dict[str, Any]:
    return {"name": name, "ok": ok, "message": sanitize_message(message)}


def skill_file_hashes(skill_directory: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for path in sorted(skill_directory.rglob("*")):
        if not path.is_file() or path.name == SKILL_MANIFEST_NAME:
            continue
        if path.is_symlink():
            raise ValueError("Skill installation must not contain symbolic links")
        relative_path = path.relative_to(skill_directory).as_posix()
        hashes[relative_path] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def verify_skill_install(
    skill_directory: Path,
    *,
    source_directory: Path | None = None,
) -> dict[str, Any]:
    if not (skill_directory / "SKILL.md").is_file():
        return diagnostic("skill", False, "usar-rlm skill is not installed")
    manifest_path = skill_directory / SKILL_MANIFEST_NAME
    if not manifest_path.is_file():
        return diagnostic("skill", False, "usar-rlm origin manifest is missing")

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or manifest.get("schema_version") != "1":
            raise ValueError("unsupported schema_version")
        source_commit = manifest.get("source_commit")
        if not isinstance(source_commit, str) or not COMMIT_PATTERN.fullmatch(source_commit):
            raise ValueError("invalid source_commit")
        expected_hashes = manifest.get("files")
        if not isinstance(expected_hashes, dict) or not expected_hashes:
            raise ValueError("files must be a non-empty object")
        if not all(
            isinstance(path, str)
            and path
            and not Path(path).is_absolute()
            and ".." not in Path(path).parts
            and isinstance(file_hash, str)
            and SHA256_PATTERN.fullmatch(file_hash)
            for path, file_hash in expected_hashes.items()
        ):
            raise ValueError("files contains an invalid path or SHA-256")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return diagnostic("skill", False, f"usar-rlm origin manifest is invalid: {error}")

    try:
        if skill_file_hashes(skill_directory) != expected_hashes:
            return diagnostic("skill", False, "usar-rlm installation drift detected")
        if (
            source_directory is not None
            and source_directory.is_dir()
            and skill_file_hashes(source_directory) != expected_hashes
        ):
            return diagnostic("skill", False, "usar-rlm source drift detected; reinstall the skill")
    except (OSError, ValueError) as error:
        return diagnostic("skill", False, f"usar-rlm could not be verified: {error}")

    return diagnostic("skill", True, f"usar-rlm skill matches origin {source_commit[:12]}")


def run_doctor(paths: CodexPaths | None = None) -> list[dict[str, Any]]:
    selected_paths = paths or CodexPaths.from_environment()
    checks: list[dict[str, Any]] = []
    checks.append(
        diagnostic(
            "python",
            sys.version_info >= (3, 11),
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        )
    )
    try:
        package_version = importlib.metadata.version("rlms")
        checks.append(diagnostic("package", True, f"rlms {package_version}"))
    except importlib.metadata.PackageNotFoundError:
        checks.append(diagnostic("package", False, "rlms package is not installed"))

    codex_factory: Any | None = None
    try:
        from openai_codex import Codex

        codex_factory = Codex
    except ImportError:
        pass
    sdk_available = codex_factory is not None
    checks.append(
        diagnostic(
            "codex_sdk",
            sdk_available,
            "openai-codex is installed" if sdk_available else "install the codex extra",
        )
    )

    api_key_absent = not bool(os.getenv("OPENAI_API_KEY"))
    checks.append(
        diagnostic(
            "api_key",
            api_key_absent,
            "OPENAI_API_KEY is unset" if api_key_absent else "OPENAI_API_KEY must be unset",
        )
    )
    if codex_factory is not None and api_key_absent:
        try:
            with codex_factory() as codex:
                account_response = codex.account()
            account = getattr(account_response, "account", None)
            account_root = getattr(account, "root", None)
            account_type = getattr(account_root, "type", None)
            checks.append(
                diagnostic(
                    "chatgpt_account",
                    account_type == "chatgpt",
                    "Codex account type is chatgpt"
                    if account_type == "chatgpt"
                    else "Codex account is not authenticated with ChatGPT",
                )
            )
        except Exception as error:
            checks.append(diagnostic("chatgpt_account", False, str(error)))
    else:
        checks.append(
            diagnostic("chatgpt_account", False, "account check skipped until SDK/key is fixed")
        )

    docker_command = shutil.which("docker")
    checks.append(
        diagnostic(
            "docker_command",
            docker_command is not None,
            docker_command or "Docker command not found",
        )
    )
    if docker_command:
        daemon = subprocess.run(
            [docker_command, "version", "--format", "{{.Server.Version}}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        daemon_ok = daemon.returncode == 0 and bool(daemon.stdout.strip())
        checks.append(
            diagnostic(
                "docker_daemon",
                daemon_ok,
                f"Docker server {daemon.stdout.strip()}"
                if daemon_ok
                else daemon.stderr.strip() or "Docker daemon unavailable",
            )
        )
        image = subprocess.run(
            [docker_command, "image", "inspect", "python:3.11-slim"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        checks.append(
            diagnostic(
                "docker_image",
                image.returncode == 0,
                "python:3.11-slim is available"
                if image.returncode == 0
                else "python:3.11-slim is not available locally",
            )
        )
    else:
        checks.append(diagnostic("docker_daemon", False, "Docker command is unavailable"))
        checks.append(diagnostic("docker_image", False, "Docker command is unavailable"))

    try:
        selected_paths.ensure()
        with tempfile.NamedTemporaryFile(dir=selected_paths.home, delete=True):
            pass
        checks.append(diagnostic("state_directory", True, str(selected_paths.home)))
    except OSError as error:
        checks.append(diagnostic("state_directory", False, str(error)))

    skill_directory = Path.home() / ".agents" / "skills" / "usar-rlm"
    source_directory = Path(__file__).resolve().parents[2] / ".agents" / "skills" / "usar-rlm"
    checks.append(
        verify_skill_install(
            skill_directory,
            source_directory=source_directory if source_directory.is_dir() else None,
        )
    )
    return checks


def error_result(command: str, error: BaseException) -> tuple[dict[str, Any], int]:
    if isinstance(error, ArgumentParsingError):
        return (
            error_envelope(command, "INVALID_ARGUMENTS", str(error), False),
            EXIT_INVALID_INPUT,
        )
    if isinstance(error, FileNotFoundError):
        return error_envelope(command, "RUN_NOT_FOUND", str(error), False), EXIT_NOT_FOUND
    if isinstance(error, (StateConflictError, TimeoutError)):
        return error_envelope(command, "STATE_CONFLICT", str(error), True), EXIT_CONFLICT
    if isinstance(error, (ValueError, OSError)):
        return error_envelope(command, "INVALID_INPUT", str(error), False), EXIT_INVALID_INPUT
    return (
        error_envelope(command, "INTERNAL_ERROR", sanitize_message(str(error)), False),
        EXIT_WORKER_FAILED,
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    manager: JobManagerProtocol | None = None,
    doctor_runner: Callable[[], list[dict[str, Any]]] | None = None,
    sleeper: Callable[[float], None] = time.sleep,
) -> int:
    output = stdout or sys.stdout
    arguments_list = list(argv) if argv is not None else sys.argv[1:]
    command = arguments_list[0] if arguments_list else "unknown"
    try:
        arguments = build_parser().parse_args(arguments_list)
        paths = CodexPaths.from_environment()
        selected_manager = manager or JobManager(RunStore(paths))
        selected_doctor = doctor_runner or (lambda: run_doctor(paths))
        if arguments.command == "events" and arguments.follow:
            return follow_events(
                selected_manager,
                arguments.run_id,
                wait_timeout=arguments.wait_timeout,
                stdout=output,
                sleeper=sleeper,
            )
        payload, exit_code = dispatch(arguments, selected_manager, selected_doctor)
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        payload, exit_code = error_result(command, error)
    output.write(json.dumps(payload, ensure_ascii=False) + "\n")
    output.flush()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
