import hashlib
import json
import os
import subprocess
from pathlib import Path

from rlm.codex_tool.cli import verify_skill_install

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = PROJECT_ROOT / ".agents" / "skills" / "usar-rlm" / "SKILL.md"
MANIFEST_NAME = ".rlm-codex-origin.json"
INSTALLER_PATH = PROJECT_ROOT / "scripts" / "install_codex_tool.ps1"


def test_skill_declares_portable_rlm_codex_workflow() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert text.startswith("---\nname: usar-rlm\n")
    for command in ("doctor", "start", "status", "events", "result"):
        assert f"rlm-codex {command}" in text
    assert "C:\\Users\\" not in text


def test_skill_explains_how_to_locate_durable_run_evidence() -> None:
    text = SKILL_PATH.read_text(encoding="utf-8")

    assert "state_directory" in text
    assert "runs/<run-id>" in text


def write_origin_manifest(skill_directory: Path) -> None:
    files = {
        "SKILL.md": hashlib.sha256((skill_directory / "SKILL.md").read_bytes()).hexdigest(),
        "references/protocol.md": hashlib.sha256(
            (skill_directory / "references" / "protocol.md").read_bytes()
        ).hexdigest(),
    }
    manifest = {
        "schema_version": "1",
        "source_commit": "a" * 40,
        "files": files,
    }
    (skill_directory / MANIFEST_NAME).write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )


def test_skill_diagnostic_detects_installed_file_drift(tmp_path: Path) -> None:
    installed = tmp_path / "installed"
    (installed / "references").mkdir(parents=True)
    (installed / "SKILL.md").write_text("skill-v1", encoding="utf-8")
    (installed / "references" / "protocol.md").write_text(
        "protocol-v1",
        encoding="utf-8",
    )
    write_origin_manifest(installed)

    assert verify_skill_install(installed)["ok"] is True

    (installed / "SKILL.md").write_text("skill-tampered", encoding="utf-8")

    diagnostic = verify_skill_install(installed)
    assert diagnostic["ok"] is False
    assert "drift" in diagnostic["message"].lower()


def test_skill_diagnostic_detects_source_drift(tmp_path: Path) -> None:
    installed = tmp_path / "installed"
    source = tmp_path / "source"
    for skill_directory in (installed, source):
        (skill_directory / "references").mkdir(parents=True)
        (skill_directory / "SKILL.md").write_text("skill-v1", encoding="utf-8")
        (skill_directory / "references" / "protocol.md").write_text(
            "protocol-v1",
            encoding="utf-8",
        )
    write_origin_manifest(installed)

    assert verify_skill_install(installed, source_directory=source)["ok"] is True

    (source / "references" / "protocol.md").write_text("protocol-v2", encoding="utf-8")

    diagnostic = verify_skill_install(installed, source_directory=source)
    assert diagnostic["ok"] is False
    assert "source" in diagnostic["message"].lower()


def run_skill_installer(
    skill_root: Path,
    *arguments: str,
    install_tool: bool = False,
    skip_verification: bool = True,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    installer_arguments = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(INSTALLER_PATH),
        "-SkillRoot",
        str(skill_root),
    ]
    if skip_verification:
        installer_arguments.append("-SkipVerification")
    if not install_tool:
        installer_arguments.append("-SkipToolInstall")
    installer_arguments.extend(arguments)
    return subprocess.run(
        installer_arguments,
        check=False,
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        env=environment,
    )


def test_installer_copies_skill_with_origin_manifest_idempotently(tmp_path: Path) -> None:
    skill_root = tmp_path / "skills"

    first = run_skill_installer(skill_root)
    assert first.returncode == 0, first.stderr

    installed = skill_root / "usar-rlm"
    manifest = json.loads((installed / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1"
    assert len(manifest["source_commit"]) == 40
    assert set(manifest["files"]) == {
        "SKILL.md",
        "agents/openai.yaml",
        "references/protocol.md",
    }
    assert verify_skill_install(installed, source_directory=SKILL_PATH.parent)["ok"] is True
    first_snapshot = {
        path.relative_to(installed).as_posix(): path.read_bytes()
        for path in installed.rglob("*")
        if path.is_file()
    }

    second = run_skill_installer(skill_root)
    assert second.returncode == 0, second.stderr
    second_snapshot = {
        path.relative_to(installed).as_posix(): path.read_bytes()
        for path in installed.rglob("*")
        if path.is_file()
    }
    assert second_snapshot == first_snapshot


def test_installer_whatif_does_not_create_skill_directory(tmp_path: Path) -> None:
    skill_root = tmp_path / "skills"

    result = run_skill_installer(skill_root, "-WhatIf")

    assert result.returncode == 0, result.stderr
    assert not skill_root.exists()


def test_installer_preserves_repository_development_groups(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uv_log = tmp_path / "uv.log"
    (fake_bin / "uv.cmd").write_text(
        '@echo %*>>"%FAKE_UV_LOG%"\n@exit /b 0\n',
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["FAKE_UV_LOG"] = str(uv_log)
    environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]

    result = run_skill_installer(
        tmp_path / "skills",
        install_tool=True,
        environment=environment,
    )

    assert result.returncode == 0, result.stderr
    invocations = uv_log.read_text(encoding="utf-8").splitlines()
    assert invocations[0] == "sync --extra codex --group dev --group test"


def test_installer_verifies_local_doctor_without_invoking_wsl(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    wsl_log = tmp_path / "wsl.log"
    (fake_bin / "uv.cmd").write_text(
        '@echo off\n@if "%1 %2 %3"=="tool dir --bin" echo %FAKE_BIN%\n@exit /b 0\n',
        encoding="utf-8",
    )
    (fake_bin / "rlm-codex.cmd").write_text(
        '@echo {"schema_version":"1","ok":true,"command":"doctor",'
        '"checks":[{"name":"execution_mode","ok":true,'
        '"message":"local trusted execution; not sandboxed"}]}\n'
        "@exit /b 0\n",
        encoding="utf-8",
    )
    (fake_bin / "wsl.cmd").write_text(
        '@echo called>>"%FAKE_WSL_LOG%"\n@exit /b 0\n',
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["FAKE_BIN"] = str(fake_bin)
    environment["FAKE_WSL_LOG"] = str(wsl_log)
    environment["PATH"] = str(fake_bin) + os.pathsep + environment["PATH"]

    result = run_skill_installer(
        tmp_path / "skills",
        skip_verification=False,
        environment=environment,
    )

    assert result.returncode == 0, result.stderr
    assert not wsl_log.exists()
