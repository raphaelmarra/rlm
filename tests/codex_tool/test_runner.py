from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import rlm.codex_tool.runner as runner_module
from rlm.codex_tool.runner import Callbacks, run_rlm, snapshot_context, validate_request


def valid_request(**overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "question": "Find the answer",
        "model": "gpt-5.6-terra",
        "max_iterations": 6,
        "max_timeout": 600,
        "context": {"notes.txt": "alpha beta"},
    }
    request.update(overrides)
    return request


@pytest.mark.parametrize("iterations", [0, 21, True])
def test_request_rejects_iteration_limit(iterations: Any) -> None:
    with pytest.raises(ValueError, match="max_iterations"):
        validate_request(valid_request(max_iterations=iterations))


@pytest.mark.parametrize("timeout", [29, 3601, True])
def test_request_rejects_timeout_limit(timeout: Any) -> None:
    with pytest.raises(ValueError, match="max_timeout"):
        validate_request(valid_request(max_timeout=timeout))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("question", ""),
        ("model", ""),
        ("context", {}),
        ("context", {"notes.txt": 1}),
    ],
)
def test_request_rejects_invalid_required_fields(field: str, value: Any) -> None:
    with pytest.raises(ValueError, match=field):
        validate_request(valid_request(**{field: value}))


class FakeRLM:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.completion_calls: list[tuple[dict[str, str], str | None]] = []
        self.closed = False

    def __enter__(self) -> "FakeRLM":
        return self

    def __exit__(self, *args: Any) -> None:
        self.closed = True

    def completion(
        self,
        context: dict[str, str],
        root_prompt: str | None = None,
    ) -> Any:
        self.completion_calls.append((context, root_prompt))
        return SimpleNamespace(response="answer")


def test_runner_always_builds_docker_rlm() -> None:
    instances: list[FakeRLM] = []

    def factory(**kwargs: Any) -> FakeRLM:
        instance = FakeRLM(**kwargs)
        instances.append(instance)
        return instance

    result = run_rlm(valid_request(), callbacks=Callbacks(), rlm_factory=factory)

    instance = instances[0]
    assert result.response == "answer"
    assert instance.kwargs["backend"] == "codex"
    assert instance.kwargs["environment"] == "docker"
    assert instance.kwargs["max_depth"] == 1
    assert instance.kwargs["max_concurrent_subcalls"] == 1
    assert instance.kwargs["environment_kwargs"] == {"run_id": None}
    assert instance.kwargs["backend_kwargs"] == {
        "model_name": "gpt-5.6-terra",
        "reasoning_effort": "medium",
    }
    assert instance.completion_calls == [({"notes.txt": "alpha beta"}, "Find the answer")]
    assert instance.closed is True


def test_runner_passes_run_id_to_docker_environment() -> None:
    instances: list[FakeRLM] = []

    def factory(**kwargs: Any) -> FakeRLM:
        instance = FakeRLM(**kwargs)
        instances.append(instance)
        return instance

    run_rlm(
        valid_request(run_id="run-1"),
        callbacks=Callbacks(),
        rlm_factory=factory,
    )

    assert instances[0].kwargs["environment_kwargs"] == {"run_id": "run-1"}


def test_snapshot_context_records_hashes_and_exact_content(tmp_path: Path) -> None:
    first = tmp_path / "alpha.txt"
    second = tmp_path / "beta.json"
    first.write_text("olá", encoding="utf-8")
    second.write_text('{"value": 7}', encoding="utf-8")

    snapshot = snapshot_context(context_files=[first, second])

    assert snapshot.content == {"alpha.txt": "olá", "beta.json": '{"value": 7}'}
    assert [item["name"] for item in snapshot.manifest] == ["alpha.txt", "beta.json"]
    assert all(len(item["sha256"]) == 64 for item in snapshot.manifest)
    assert snapshot.total_bytes == len("olá".encode()) + len(b'{"value": 7}')


def test_snapshot_context_accepts_inline_text() -> None:
    snapshot = snapshot_context(context_text="short context")

    assert snapshot.content == {"inline.txt": "short context"}
    assert snapshot.manifest[0]["source"] == "inline"


@pytest.mark.parametrize(
    ("files", "text"),
    [([], None), (None, None), ([], "text"), ([Path("a")], "text")],
)
def test_snapshot_context_requires_exactly_one_input_mode(
    files: list[Path] | None,
    text: str | None,
) -> None:
    with pytest.raises(ValueError, match="exactly one"):
        snapshot_context(context_files=files, context_text=text)


def test_snapshot_context_rejects_duplicate_names(tmp_path: Path) -> None:
    first = tmp_path / "one" / "same.txt"
    second = tmp_path / "two" / "same.txt"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate context name"):
        snapshot_context(context_files=[first, second])


def test_snapshot_context_rejects_binary_file(tmp_path: Path) -> None:
    binary = tmp_path / "binary.dat"
    binary.write_bytes(b"text\x00more")

    with pytest.raises(ValueError, match="binary"):
        snapshot_context(context_files=[binary])


def test_snapshot_context_enforces_total_size(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runner_module, "MAX_CONTEXT_BYTES", 3)
    context_file = tmp_path / "large.txt"
    context_file.write_text("four", encoding="utf-8")

    with pytest.raises(ValueError, match="50 MiB"):
        snapshot_context(context_files=[context_file])
