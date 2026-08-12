import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath, PureWindowsPath
from typing import Any

from rlm import RLM
from rlm.core.types import RLMChatCompletion
from rlm.logger import RLMLogger

DEFAULT_MODEL = "gpt-5.6-terra"
DEFAULT_MAX_ITERATIONS = 6
DEFAULT_MAX_TIMEOUT = 600.0
MIN_MAX_ITERATIONS = 1
MAX_MAX_ITERATIONS = 20
MIN_MAX_TIMEOUT = 30.0
MAX_MAX_TIMEOUT = 3600.0
MAX_CONTEXT_BYTES = 50 * 1024 * 1024
MAX_CONTEXT_FILES = 200


@dataclass(frozen=True)
class ContextSnapshot:
    content: dict[str, str]
    manifest: list[dict[str, Any]]
    total_bytes: int


@dataclass(frozen=True)
class ValidatedRequest:
    question: str
    model: str
    max_iterations: int
    max_timeout: float
    context: dict[str, str]
    run_id: str | None = None


@dataclass(frozen=True)
class Callbacks:
    on_iteration_start: Callable[[int, int], None] | None = None
    on_iteration_complete: Callable[[int, int, float], None] | None = None
    on_subcall_start: Callable[[int, str, str], None] | None = None
    on_subcall_complete: Callable[[int, str, float, str | None], None] | None = None


def require_nonempty_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def validate_context_name(name: Any) -> str:
    if not isinstance(name, str) or not name:
        raise ValueError("context names must be non-empty strings")
    path = PurePath(name)
    windows_path = PureWindowsPath(name)
    if path.is_absolute() or windows_path.is_absolute() or ".." in path.parts:
        raise ValueError(f"context name must be relative and safe: {name!r}")
    return name


def validate_context(context: Any) -> dict[str, str]:
    if not isinstance(context, dict) or not context:
        raise ValueError("context must be a non-empty object")
    if len(context) > MAX_CONTEXT_FILES:
        raise ValueError(f"context may contain at most {MAX_CONTEXT_FILES} files")
    normalized: dict[str, str] = {}
    total_bytes = 0
    for raw_name, raw_content in context.items():
        name = validate_context_name(raw_name)
        if not isinstance(raw_content, str):
            raise ValueError(f"context entry {name!r} must contain text")
        if "\x00" in raw_content:
            raise ValueError(f"context entry {name!r} appears to be binary")
        total_bytes += len(raw_content.encode("utf-8"))
        normalized[name] = raw_content
    if total_bytes < 1 or total_bytes > MAX_CONTEXT_BYTES:
        raise ValueError("context size must be between 1 byte and 50 MiB")
    return normalized


def validate_request(request: Mapping[str, Any]) -> ValidatedRequest:
    question = require_nonempty_text(request.get("question"), "question")
    model = require_nonempty_text(request.get("model", DEFAULT_MODEL), "model")
    max_iterations = request.get("max_iterations", DEFAULT_MAX_ITERATIONS)
    if (
        not isinstance(max_iterations, int)
        or isinstance(max_iterations, bool)
        or not MIN_MAX_ITERATIONS <= max_iterations <= MAX_MAX_ITERATIONS
    ):
        raise ValueError("max_iterations must be an integer between 1 and 20")
    max_timeout = request.get("max_timeout", DEFAULT_MAX_TIMEOUT)
    if (
        not isinstance(max_timeout, (int, float))
        or isinstance(max_timeout, bool)
        or not MIN_MAX_TIMEOUT <= max_timeout <= MAX_MAX_TIMEOUT
    ):
        raise ValueError("max_timeout must be between 30 and 3600 seconds")
    run_id = request.get("run_id")
    if run_id is not None:
        run_id = require_nonempty_text(run_id, "run_id")
    return ValidatedRequest(
        question=question,
        model=model,
        max_iterations=max_iterations,
        max_timeout=float(max_timeout),
        context=validate_context(request.get("context")),
        run_id=run_id,
    )


def snapshot_context(
    *,
    context_files: Sequence[Path] | None = None,
    context_text: str | None = None,
) -> ContextSnapshot:
    files_selected = context_files is not None
    text_selected = context_text is not None
    if files_selected == text_selected or (files_selected and not context_files):
        raise ValueError("exactly one non-empty context input mode is required")

    if text_selected:
        assert context_text is not None
        text = require_nonempty_text(context_text, "context_text")
        payload = text.encode("utf-8")
        validate_snapshot_size(len(payload))
        return ContextSnapshot(
            content={"inline.txt": text},
            manifest=[
                {
                    "name": "inline.txt",
                    "source": "inline",
                    "bytes": len(payload),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                }
            ],
            total_bytes=len(payload),
        )

    assert context_files is not None
    if len(context_files) > MAX_CONTEXT_FILES:
        raise ValueError(f"context may contain at most {MAX_CONTEXT_FILES} files")
    content: dict[str, str] = {}
    manifest: list[dict[str, Any]] = []
    total_bytes = 0
    for source in context_files:
        path = Path(source).expanduser().resolve(strict=True)
        if not path.is_file():
            raise ValueError(f"Context path is not a file: {source}")
        name = path.name
        if name in content:
            raise ValueError(f"Duplicate context name: {name}")
        payload = path.read_bytes()
        total_bytes += len(payload)
        validate_snapshot_size(total_bytes)
        try:
            text = payload.decode("utf-8")
        except UnicodeDecodeError as error:
            raise ValueError(f"Context file appears to be binary: {path}") from error
        if "\x00" in text:
            raise ValueError(f"Context file appears to be binary: {path}")
        content[name] = text
        manifest.append(
            {
                "name": name,
                "source": str(path),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    validate_snapshot_size(total_bytes)
    return ContextSnapshot(content=content, manifest=manifest, total_bytes=total_bytes)


def validate_snapshot_size(total_bytes: int) -> None:
    if total_bytes < 1 or total_bytes > MAX_CONTEXT_BYTES:
        raise ValueError("context size must be between 1 byte and 50 MiB")


def run_rlm(
    request: Mapping[str, Any],
    callbacks: Callbacks,
    *,
    rlm_factory: Callable[..., Any] = RLM,
) -> RLMChatCompletion:
    validated = validate_request(request)
    with rlm_factory(
        backend="codex",
        backend_kwargs={
            "model_name": validated.model,
            "reasoning_effort": "medium",
        },
        environment="docker",
        max_depth=1,
        max_iterations=validated.max_iterations,
        max_timeout=validated.max_timeout,
        max_concurrent_subcalls=1,
        logger=RLMLogger(),
        on_iteration_start=callbacks.on_iteration_start,
        on_iteration_complete=callbacks.on_iteration_complete,
        on_subcall_start=callbacks.on_subcall_start,
        on_subcall_complete=callbacks.on_subcall_complete,
    ) as rlm:
        return rlm.completion(validated.context, root_prompt=validated.question)
