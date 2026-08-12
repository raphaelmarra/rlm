"""Sequential, resumable runners for the direct and RLM benchmark arms."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from typing import Any, Protocol, cast

import psutil

from oolong_codex.config import BenchmarkConfig, BenchmarkPaths
from oolong_codex.models import CaseRecord, RawResult
from oolong_codex.storage import read_json, write_json_atomic
from rlm.clients.codex import CodexClient

TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "orphaned"}


class Client(Protocol):
    def completion(self, prompt: str) -> str: ...

    def get_last_usage(self) -> Any: ...


CliInvoker = Callable[..., dict[str, Any]]


def arm_for_method(config: BenchmarkConfig, method: str) -> str:
    matches = [arm for arm, assigned in config.arms.items() if assigned == method]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one arm assigned to {method!r}")
    return matches[0]


def invoke_cli(
    arguments: list[str],
    *,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Invoke the local JSON-only CLI and retain error envelopes."""

    executable = shutil.which("rlm-codex")
    if executable is None:
        raise RuntimeError("rlm-codex was not found on PATH")
    completed = subprocess.run(
        [executable, *arguments],
        check=False,
        capture_output=True,
        encoding="utf-8",
        env=dict(env) if env is not None else None,
        timeout=timeout,
    )
    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"rlm-codex returned invalid JSON (exit {completed.returncode}): "
            f"{completed.stderr.strip()}"
        ) from error
    if not isinstance(envelope, dict):
        raise RuntimeError("rlm-codex returned a non-object JSON envelope")
    if str(envelope.get("schema_version")) != "1" or envelope.get("command") != arguments[0]:
        raise RuntimeError("rlm-codex returned an incompatible JSON envelope")
    if not isinstance(envelope.get("ok"), bool):
        raise RuntimeError("rlm-codex JSON envelope is missing a boolean ok field")
    if completed.returncode == 0 and not envelope["ok"]:
        raise RuntimeError("rlm-codex returned an error envelope with exit code zero")
    if completed.returncode != 0 and envelope["ok"]:
        raise RuntimeError("rlm-codex returned a success envelope with nonzero exit code")
    return cast(dict[str, Any], envelope)


def run_baseline_case(
    case: CaseRecord,
    config: BenchmarkConfig,
    client_factory: Callable[..., Client] = CodexClient,
) -> RawResult:
    """Run one context-in-prompt completion without exposing the gold file."""

    question = case.question_path.read_text(encoding="utf-8")
    context = case.context_path.read_text(encoding="utf-8")
    prompt = f"{question}\n\n<context>\n{context}\n</context>"
    client = client_factory(
        model_name=config.model_name,
        reasoning_effort=config.reasoning_effort,
        timeout=config.max_timeout,
    )
    started = time.monotonic()
    response = client.completion(prompt)
    wall_seconds = time.monotonic() - started
    usage = client.get_last_usage()
    return RawResult(
        case_id=case.id,
        arm=arm_for_method(config, "baseline"),
        response=response,
        status="succeeded",
        wall_seconds=wall_seconds,
        input_tokens=usage.total_input_tokens,
        output_tokens=usage.total_output_tokens,
        calls=usage.total_calls,
        total_cost=usage.total_cost,
        metadata={
            "context_sha256": case.context_sha256,
            "question_sha256": case.question_sha256,
        },
    )


def run_rlm_case(
    case: CaseRecord,
    config: BenchmarkConfig,
    paths: BenchmarkPaths,
    cli_invoker: CliInvoker = invoke_cli,
    pid_exists: Callable[[int], bool] = psutil.pid_exists,
) -> RawResult:
    """Start or resume one durable local RLM job and collect its terminal state."""

    arm = arm_for_method(config, "rlm")
    attempt_path = paths.attempt_path(arm, case.id)
    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)
    started = time.monotonic()

    if attempt_path.exists():
        attempt = read_json(attempt_path)
    else:
        start_envelope = cli_invoker(
            [
                "start",
                "--question",
                case.question_path.read_text(encoding="utf-8"),
                "--context-file",
                str(case.context_path),
                "--model",
                config.model_name,
                "--max-iterations",
                str(config.max_iterations),
                "--max-timeout",
                str(config.max_timeout),
            ],
            env=environment,
            timeout=60,
        )
        if not start_envelope.get("ok"):
            raise RuntimeError(f"rlm-codex start failed: {start_envelope.get('error')}")
        run = start_envelope["run"]
        attempt = {"run_id": run["id"], "pid": run.get("pid")}
        write_json_atomic(attempt_path, attempt)

    run_id = str(attempt["run_id"])
    original_pid = attempt.get("pid")
    result_envelope = cli_invoker(
        [
            "result",
            run_id,
            "--wait",
            "--wait-timeout",
            str(config.max_timeout),
        ],
        env=environment,
        timeout=config.max_timeout + 60,
    )
    status_envelope = cli_invoker(
        ["status", run_id],
        env=environment,
        timeout=60,
    )
    if not status_envelope.get("ok"):
        raise RuntimeError(f"rlm-codex status failed: {status_envelope.get('error')}")
    result_payload = cast(dict[str, Any], result_envelope.get("result", {}))
    state = cast(dict[str, Any], status_envelope.get("run", {}))
    if not result_envelope.get("ok"):
        if state.get("status") not in TERMINAL_STATUSES or not result_payload:
            raise RuntimeError(
                f"rlm-codex result is not terminal; resume run {run_id}: "
                f"{result_envelope.get('error')}"
            )
    if not result_payload.get("status"):
        raise RuntimeError(f"rlm-codex result for {run_id} is missing status")
    status = str(result_payload.get("status") or state.get("status") or "failed")
    metadata = cast(dict[str, Any], result_payload.get("metadata") or {})
    usage = cast(dict[str, Any], result_payload.get("usage_summary") or {})
    model_usages = cast(dict[str, dict[str, Any]], usage.get("model_usage_summaries") or {})
    original_pid_alive = bool(original_pid and pid_exists(int(original_pid)))
    error_value = result_payload.get("error") or result_envelope.get("error") or state.get("error")

    return RawResult(
        case_id=case.id,
        arm=arm,
        response=str(result_payload.get("response") or result_payload.get("partial_answer") or ""),
        status=status,
        wall_seconds=float(result_payload.get("execution_time") or (time.monotonic() - started)),
        input_tokens=sum(int(item.get("total_input_tokens", 0)) for item in model_usages.values()),
        output_tokens=sum(
            int(item.get("total_output_tokens", 0)) for item in model_usages.values()
        ),
        calls=sum(int(item.get("total_calls", 0)) for item in model_usages.values()),
        total_cost=usage.get("total_cost"),
        run_id=run_id,
        pid=state.get("pid"),
        original_pid=original_pid,
        metadata={
            "context_sha256": case.context_sha256,
            "question_sha256": case.question_sha256,
            "subcalls": count_subcalls(metadata),
            "original_pid_alive": original_pid_alive,
            "rlm_metadata": metadata,
            "cli_result": result_envelope,
            "cli_status": status_envelope,
        },
        error=json.dumps(error_value, ensure_ascii=False) if error_value is not None else None,
    )


def count_subcalls(metadata: Mapping[str, Any]) -> int:
    count = 0
    for iteration in metadata.get("iterations", []):
        for code_block in iteration.get("code_blocks", []):
            result = code_block.get("result") or {}
            count += len(result.get("rlm_calls") or [])
    return count


def run_arm(
    method: str,
    cases: Sequence[CaseRecord],
    config: BenchmarkConfig,
    paths: BenchmarkPaths,
) -> list[RawResult]:
    """Run cases sequentially, reusing terminal raw results on restart."""

    arm = arm_for_method(config, method)
    results: list[RawResult] = []
    for case in cases:
        raw_path = paths.raw_path(arm, case.id)
        if raw_path.exists():
            saved = read_json(raw_path)
            if saved.get("status") in TERMINAL_STATUSES:
                results.append(RawResult(**saved))
                continue
        if method == "baseline":
            result = run_baseline_case(case, config)
        elif method == "rlm":
            result = run_rlm_case(case, config, paths)
        else:
            raise ValueError(f"Unsupported benchmark method: {method!r}")
        write_json_atomic(raw_path, asdict(result))
        results.append(result)
    return results
