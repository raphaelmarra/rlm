from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import rlm.environments.docker_repl as docker_module
from rlm.codex_tool.jobs import cleanup_docker_resources
from rlm.environments.docker_repl import DockerREPL


class FakeSubprocess:
    def __init__(self, *, fail_run: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.fail_run = fail_run

    def __call__(self, command: list[str], **kwargs: Any) -> Any:
        self.calls.append(command)
        if command[:3] == ["docker", "network", "create"]:
            return SimpleNamespace(returncode=0, stdout="network-id\n", stderr="")
        if command[:2] == ["docker", "run"]:
            if self.fail_run:
                return SimpleNamespace(returncode=1, stdout="", stderr="run failed")
            return SimpleNamespace(returncode=0, stdout="container-id\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def command_starting_with(self, *prefix: str) -> list[str]:
        return next(command for command in self.calls if command[: len(prefix)] == list(prefix))


@pytest.fixture
def docker_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    workspace = tmp_path / "workspace"
    monkeypatch.setenv("RLM_DOCKER_WORKSPACE_DIR", str(workspace))
    return workspace


def test_docker_run_applies_rlm_codex_isolation(
    docker_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSubprocess()
    monkeypatch.setattr(docker_module.subprocess, "run", fake)

    repl = DockerREPL(run_id="run-1")
    try:
        network_command = fake.command_starting_with("docker", "network", "create")
        run_command = fake.command_starting_with("docker", "run")
        assert "--internal" in network_command
        label_index = network_command.index("--label")
        assert ["--label", "io.rlm-codex.run-id=run-1"] == network_command[
            label_index : label_index + 2
        ]
        assert "--label" in run_command
        assert "io.rlm-codex.run-id=run-1" in run_command
        assert "--cap-drop=ALL" in run_command
        assert ["--security-opt", "no-new-privileges=true"] == run_command[
            run_command.index("--security-opt") : run_command.index("--security-opt") + 2
        ]
        assert ["--pids-limit", "128"] == run_command[
            run_command.index("--pids-limit") : run_command.index("--pids-limit") + 2
        ]
        assert ["--memory", "512m"] == run_command[
            run_command.index("--memory") : run_command.index("--memory") + 2
        ]
        assert ["--cpus", "1.0"] == run_command[
            run_command.index("--cpus") : run_command.index("--cpus") + 2
        ]
        assert ["--network", repl.network_name] == run_command[
            run_command.index("--network") : run_command.index("--network") + 2
        ]
        mount_index = run_command.index("-v")
        assert run_command[mount_index + 1] == f"{repl.temp_dir}:/workspace"
        network_name = repl.network_name
    finally:
        repl.cleanup()

    assert ["docker", "network", "rm", network_name] in fake.calls


def test_generated_code_executes_as_non_root_user(
    docker_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSubprocess()
    monkeypatch.setattr(docker_module.subprocess, "run", fake)
    repl = DockerREPL(run_id="run-1", execution_user="12345:12345")

    try:
        repl.execute_code("print('safe')")
    finally:
        repl.cleanup()

    exec_commands = [command for command in fake.calls if command[:2] == ["docker", "exec"]]
    code_command = next(command for command in exec_commands if "/workspace/_exec.py" in command)
    assert code_command[2:4] == ["--user", "12345:12345"]


def test_partial_container_failure_removes_network_and_workspace(
    docker_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSubprocess(fail_run=True)
    monkeypatch.setattr(docker_module.subprocess, "run", fake)

    with pytest.raises(RuntimeError, match="Failed to start container"):
        DockerREPL(run_id="run-1")

    network_create = fake.command_starting_with("docker", "network", "create")
    network_name = network_create[-1]
    assert ["docker", "network", "rm", network_name] in fake.calls
    assert list(docker_workspace.glob("docker_repl_*")) == []


def test_invalid_run_id_fails_before_docker(
    docker_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSubprocess()
    monkeypatch.setattr(docker_module.subprocess, "run", fake)

    with pytest.raises(ValueError, match="run id"):
        DockerREPL(run_id="../escape")

    assert fake.calls == []


def test_resource_limits_are_validated_before_docker(
    docker_workspace: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeSubprocess()
    monkeypatch.setattr(docker_module.subprocess, "run", fake)

    with pytest.raises(ValueError, match="pids_limit"):
        DockerREPL(run_id="run-1", pids_limit=0)

    assert fake.calls == []


def test_forced_cleanup_removes_resources_by_run_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> Any:
        calls.append(command)
        if command[:3] == ["docker", "container", "ls"]:
            return SimpleNamespace(returncode=0, stdout="container-a\ncontainer-b\n", stderr="")
        if command[:3] == ["docker", "network", "ls"]:
            return SimpleNamespace(returncode=0, stdout="network-a\n", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("rlm.codex_tool.jobs.shutil.which", lambda command: "docker")
    monkeypatch.setattr("rlm.codex_tool.jobs.subprocess.run", run)

    cleanup_docker_resources("run-1")

    label = "label=io.rlm-codex.run-id=run-1"
    assert ["docker", "container", "ls", "-aq", "--filter", label] in calls
    assert ["docker", "container", "rm", "-f", "container-a", "container-b"] in calls
    assert ["docker", "network", "ls", "-q", "--filter", label] in calls
    assert ["docker", "network", "rm", "network-a"] in calls
