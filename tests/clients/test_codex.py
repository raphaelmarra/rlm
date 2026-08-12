import asyncio
import threading
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from rlm.clients.codex import CodexClient, CodexExecution, SDKCodexExecutor
from rlm.core.types import ModelUsageSummary


@dataclass
class ExecutorCall:
    messages: list[dict[str, str]]
    model: str
    timeout: float
    reasoning_effort: str
    service_tier: str | None


class FakeExecutor:
    def __init__(
        self,
        response: str = "next",
        input_tokens: int = 12,
        output_tokens: int = 4,
    ) -> None:
        self.execution = CodexExecution(response, input_tokens, output_tokens)
        self.calls: list[ExecutorCall] = []

    def run(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        timeout: float,
        reasoning_effort: str,
        service_tier: str | None,
    ) -> CodexExecution:
        self.calls.append(ExecutorCall(messages, model, timeout, reasoning_effort, service_tier))
        return self.execution

    async def arun(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        timeout: float,
        reasoning_effort: str,
        service_tier: str | None,
    ) -> CodexExecution:
        await asyncio.sleep(0)
        return self.run(
            messages=messages,
            model=model,
            timeout=timeout,
            reasoning_effort=reasoning_effort,
            service_tier=service_tier,
        )


def test_completion_rejects_api_key_before_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "present")
    executor = FakeExecutor()
    client = CodexClient(model_name="gpt-5.6-terra", executor=executor)

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        client.completion("hello")

    assert executor.calls == []


def test_completion_preserves_message_order_and_tracks_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    executor = FakeExecutor(response="next", input_tokens=12, output_tokens=4)
    client = CodexClient(
        model_name="gpt-5.6-terra",
        reasoning_effort="high",
        service_tier="fast",
        executor=executor,
    )

    result = client.completion(
        [
            {"role": "system", "content": "rules"},
            {"role": "developer", "content": "constraints"},
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "attempt"},
        ]
    )

    assert result == "next"
    assert executor.calls == [
        ExecutorCall(
            messages=[
                {"role": "system", "content": "rules"},
                {"role": "developer", "content": "constraints"},
                {"role": "user", "content": "question"},
                {"role": "assistant", "content": "attempt"},
            ],
            model="gpt-5.6-terra",
            timeout=300.0,
            reasoning_effort="high",
            service_tier="fast",
        )
    ]
    assert client.get_last_usage() == ModelUsageSummary(1, 12, 4, None)
    assert client.get_usage_summary().model_usage_summaries["gpt-5.6-terra"] == (
        ModelUsageSummary(1, 12, 4, None)
    )


@pytest.mark.asyncio
async def test_acompletion_uses_async_executor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    executor = FakeExecutor(response="async response", input_tokens=5, output_tokens=2)
    client = CodexClient(model_name="gpt-5.6-terra", executor=executor)

    assert await client.acompletion("hello") == "async response"
    assert client.get_last_usage() == ModelUsageSummary(1, 5, 2, None)


@pytest.mark.parametrize(
    ("prompt", "message"),
    [
        (123, "Invalid prompt type"),
        ([{"role": "tool", "content": "x"}], "Unsupported message role"),
        ([{"role": "user", "content": {"text": "x"}}], "text content"),
    ],
)
def test_completion_rejects_unknown_input(
    monkeypatch: pytest.MonkeyPatch,
    prompt: Any,
    message: str,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = CodexClient(model_name="gpt-5.6-terra", executor=FakeExecutor())

    with pytest.raises(ValueError, match=message):
        client.completion(prompt)


def test_completion_rejects_empty_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = CodexClient(model_name="gpt-5.6-terra", executor=FakeExecutor(response="  "))

    with pytest.raises(ValueError, match="empty response"):
        client.completion("hello")


def test_usage_accumulates_per_selected_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    executor = FakeExecutor(input_tokens=3, output_tokens=2)
    client = CodexClient(model_name="gpt-5.6-terra", executor=executor)

    client.completion("one")
    client.completion("two", model="gpt-5.6-sol")

    summary = client.get_usage_summary().model_usage_summaries
    assert summary == {
        "gpt-5.6-terra": ModelUsageSummary(1, 3, 2, None),
        "gpt-5.6-sol": ModelUsageSummary(1, 3, 2, None),
    }


class FakeThread:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.run_input: str | None = None
        self.run_kwargs: dict[str, Any] = {}

    def run(self, prompt: str, **kwargs: Any) -> Any:
        self.run_input = prompt
        self.run_kwargs = kwargs
        return self.result


class BlockingThread(FakeThread):
    def __init__(self, result: Any) -> None:
        super().__init__(result)
        self.started = threading.Event()
        self.release = threading.Event()

    def run(self, prompt: str, **kwargs: Any) -> Any:
        self.run_input = prompt
        self.run_kwargs = kwargs
        self.started.set()
        self.release.wait(timeout=1)
        return self.result


class RaisingThread(FakeThread):
    def run(self, prompt: str, **kwargs: Any) -> Any:
        self.run_input = prompt
        self.run_kwargs = kwargs
        raise RuntimeError("turn failed")


class FakeCodex:
    def __init__(self, account_type: str = "chatgpt") -> None:
        usage = SimpleNamespace(
            last=SimpleNamespace(input_tokens=8, output_tokens=3),
        )
        self.thread = FakeThread(SimpleNamespace(final_response="sdk response", usage=usage))
        self.account_type = account_type
        self.thread_kwargs: dict[str, Any] = {}
        self.closed = False
        self.close_called = False

    def __enter__(self) -> "FakeCodex":
        return self

    def __exit__(self, *args: Any) -> None:
        self.closed = True

    def account(self) -> Any:
        return SimpleNamespace(
            account=SimpleNamespace(root=SimpleNamespace(type=self.account_type))
        )

    def thread_start(self, **kwargs: Any) -> FakeThread:
        self.thread_kwargs = kwargs
        return self.thread

    def close(self) -> None:
        self.close_called = True
        release = getattr(self.thread, "release", None)
        if release is not None:
            release.set()


def test_sdk_executor_uses_ephemeral_read_only_thread_and_cleans_temp_dir() -> None:
    codex = FakeCodex()
    executor = SDKCodexExecutor(codex_factory=lambda: codex)

    execution = executor.run(
        messages=[
            {"role": "system", "content": "rules"},
            {"role": "user", "content": "question"},
        ],
        model="gpt-5.6-terra",
        timeout=5,
        reasoning_effort="medium",
        service_tier=None,
    )

    assert execution == CodexExecution("sdk response", 8, 3)
    assert codex.closed is True
    assert codex.thread_kwargs["ephemeral"] is True
    assert codex.thread_kwargs["sandbox"].value == "read-only"
    assert codex.thread_kwargs["approval_mode"].value == "deny_all"
    assert Path(codex.thread_kwargs["cwd"]).exists() is False
    assert "Return only the next RLM model message" in codex.thread.run_input
    assert '"role": "user"' in codex.thread.run_input


def test_sdk_executor_rejects_non_chatgpt_account() -> None:
    codex = FakeCodex(account_type="apiKey")
    executor = SDKCodexExecutor(codex_factory=lambda: codex)

    with pytest.raises(ValueError, match="ChatGPT authentication"):
        executor.run(
            messages=[{"role": "user", "content": "question"}],
            model="gpt-5.6-terra",
            timeout=5,
            reasoning_effort="medium",
            service_tier=None,
        )

    assert codex.closed is True


def test_sdk_executor_times_out_and_closes_codex() -> None:
    codex = FakeCodex()
    codex.thread = BlockingThread(codex.thread.result)
    executor = SDKCodexExecutor(codex_factory=lambda: codex)

    with pytest.raises(TimeoutError, match="timed out"):
        executor.run(
            messages=[{"role": "user", "content": "question"}],
            model="gpt-5.6-terra",
            timeout=0.01,
            reasoning_effort="medium",
            service_tier=None,
        )

    assert codex.close_called is True
    assert codex.closed is True
    assert Path(codex.thread_kwargs["cwd"]).exists() is False


def test_sdk_executor_cleans_up_after_turn_error() -> None:
    codex = FakeCodex()
    codex.thread = RaisingThread(codex.thread.result)
    executor = SDKCodexExecutor(codex_factory=lambda: codex)

    with pytest.raises(RuntimeError, match="turn failed"):
        executor.run(
            messages=[{"role": "user", "content": "question"}],
            model="gpt-5.6-terra",
            timeout=5,
            reasoning_effort="medium",
            service_tier=None,
        )

    assert codex.closed is True
    assert Path(codex.thread_kwargs["cwd"]).exists() is False


class FakeAsyncThread:
    def __init__(self) -> None:
        usage = SimpleNamespace(last=SimpleNamespace(input_tokens=7, output_tokens=2))
        self.result = SimpleNamespace(final_response="async sdk response", usage=usage)
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run(self, prompt: str, **kwargs: Any) -> Any:
        self.started.set()
        await self.release.wait()
        return self.result


class FakeAsyncCodex:
    def __init__(self) -> None:
        self.thread = FakeAsyncThread()
        self.thread_kwargs: dict[str, Any] = {}
        self.closed = False

    async def __aenter__(self) -> "FakeAsyncCodex":
        return self

    async def __aexit__(self, *args: Any) -> None:
        self.closed = True

    async def account(self) -> Any:
        return SimpleNamespace(account=SimpleNamespace(root=SimpleNamespace(type="chatgpt")))

    async def thread_start(self, **kwargs: Any) -> FakeAsyncThread:
        self.thread_kwargs = kwargs
        return self.thread


@pytest.mark.asyncio
async def test_sdk_async_executor_returns_response_and_usage() -> None:
    codex = FakeAsyncCodex()
    codex.thread.release.set()
    executor = SDKCodexExecutor(async_codex_factory=lambda: codex)

    execution = await executor.arun(
        messages=[{"role": "user", "content": "question"}],
        model="gpt-5.6-terra",
        timeout=5,
        reasoning_effort="medium",
        service_tier=None,
    )

    assert execution == CodexExecution("async sdk response", 7, 2)
    assert codex.closed is True
    assert codex.thread_kwargs["ephemeral"] is True
    assert codex.thread_kwargs["sandbox"].value == "read-only"


@pytest.mark.asyncio
async def test_sdk_async_executor_cleans_up_when_cancelled() -> None:
    codex = FakeAsyncCodex()
    executor = SDKCodexExecutor(async_codex_factory=lambda: codex)
    task = asyncio.create_task(
        executor.arun(
            messages=[{"role": "user", "content": "question"}],
            model="gpt-5.6-terra",
            timeout=5,
            reasoning_effort="medium",
            service_tier=None,
        )
    )
    await codex.thread.started.wait()

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert codex.closed is True
    assert Path(codex.thread_kwargs["cwd"]).exists() is False


def test_get_client_registers_codex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from rlm.clients import get_client

    client = get_client(
        "codex",
        {"model_name": "gpt-5.6-terra", "executor": FakeExecutor()},
    )

    assert isinstance(client, CodexClient)
