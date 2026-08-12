import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "recursive_context.json"
LIVE_ENABLED = os.getenv("RLM_LIVE_CODEX") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE_ENABLED,
    reason="requires RLM_LIVE_CODEX=1",
)


def invoke_cli(
    environment: dict[str, str],
    *arguments: str,
    timeout: float = 120.0,
) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, "-m", "rlm.codex_tool.cli", *arguments],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        cwd=Path(os.environ.get("TEMP", Path.cwd())),
        timeout=timeout,
    )
    assert result.returncode == 0, result.stdout or result.stderr
    return json.loads(result.stdout)


def count_plain_llm_calls(metadata: dict[str, Any]) -> int:
    return sum(
        len(code_block["result"]["rlm_calls"])
        for iteration in metadata["iterations"]
        for code_block in iteration["code_blocks"]
    )


def test_live_cli_runs_rlm_locally_and_returns_result(tmp_path: Path) -> None:
    source_directory = tmp_path / "source"
    source_directory.mkdir()
    context_file = source_directory / FIXTURE.name
    context_file.write_bytes(FIXTURE.read_bytes())
    source_snapshot = context_file.read_bytes()

    environment = os.environ.copy()
    environment.pop("OPENAI_API_KEY", None)
    environment["RLM_CODEX_HOME"] = str(tmp_path / "state")

    started = invoke_cli(
        environment,
        "start",
        "--question",
        (
            "Parse the JSON string in context['recursive_context.json']. In Python, "
            "call llm_query exactly once with child_prompt, strip the response, prepend "
            "answer_prefix, set answer['content'] and answer['ready']=True. Do not infer "
            "or hardcode the child response."
        ),
        "--context-file",
        str(context_file),
        "--max-iterations",
        "4",
        "--max-timeout",
        "600",
    )
    run_id = started["run"]["id"]
    worker_pid = started["run"]["pid"]

    result = invoke_cli(
        environment,
        "result",
        run_id,
        "--wait",
        "--wait-timeout",
        "700",
        timeout=720,
    )["result"]
    status = invoke_cli(environment, "status", run_id)["run"]

    assert result["status"] == "succeeded"
    assert result["response"].strip() == "RLM-CODEX-7391"
    assert result["metadata"]["run_metadata"]["environment_type"] == "local"
    assert count_plain_llm_calls(result["metadata"]) == 1
    assert result["usage_summary"]["total_cost"] is None
    assert status["status"] == "succeeded"
    assert status["pid"] is None
    assert worker_pid is not None
    assert context_file.read_bytes() == source_snapshot
