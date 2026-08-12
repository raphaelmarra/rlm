import asyncio
import json
import os
import tempfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, Protocol

from rlm.clients.base_lm import BaseLM
from rlm.core.types import ModelUsageSummary, UsageSummary

BACKEND_INSTRUCTIONS = """You are the language-model backend inside a Recursive Language Model.
Return only the next RLM model message. Do not execute Python blocks that you produce. Do not
inspect or modify a project. The caller will execute any REPL block in its isolated environment.
"""

SUPPORTED_ROLES = {"system", "developer", "user", "assistant"}
SUPPORTED_REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}


@dataclass(frozen=True)
class CodexExecution:
    response: str
    input_tokens: int
    output_tokens: int


class CodexExecutor(Protocol):
    def run(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        timeout: float,
        reasoning_effort: str,
        service_tier: str | None,
    ) -> CodexExecution: ...

    async def arun(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        timeout: float,
        reasoning_effort: str,
        service_tier: str | None,
    ) -> CodexExecution: ...


def normalize_messages(prompt: str | list[dict[str, Any]]) -> list[dict[str, str]]:
    if isinstance(prompt, str):
        return [{"role": "user", "content": prompt}]
    if not isinstance(prompt, list) or not all(isinstance(item, dict) for item in prompt):
        raise ValueError(f"Invalid prompt type: {type(prompt)}")

    messages: list[dict[str, str]] = []
    for item in prompt:
        role = item.get("role")
        content = item.get("content")
        if role not in SUPPORTED_ROLES:
            raise ValueError(f"Unsupported message role: {role!r}")
        if not isinstance(content, str):
            raise ValueError("Codex messages require text content")
        messages.append({"role": role, "content": content})
    return messages


def build_codex_input(messages: list[dict[str, str]]) -> tuple[str, str]:
    instruction_parts = [BACKEND_INSTRUCTIONS.strip()]
    transcript: list[dict[str, str]] = []
    for message in messages:
        if message["role"] in {"system", "developer"}:
            instruction_parts.append(f"{message['role']}: {message['content']}")
        else:
            transcript.append(message)

    prompt = "Return only the next RLM model message for this ordered conversation.\n" + json.dumps(
        transcript, ensure_ascii=False
    )
    return "\n\n".join(instruction_parts), prompt


class SDKCodexExecutor:
    def __init__(
        self,
        *,
        codex_factory: Any | None = None,
        async_codex_factory: Any | None = None,
        require_chatgpt_auth: bool = True,
    ) -> None:
        self.codex_factory = codex_factory
        self.async_codex_factory = async_codex_factory
        self.require_chatgpt_auth = require_chatgpt_auth

    def run(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        timeout: float,
        reasoning_effort: str,
        service_tier: str | None,
    ) -> CodexExecution:
        try:
            from openai_codex import ApprovalMode, Codex, Sandbox
            from openai_codex.generated.v2_all import ReasoningEffort
        except ImportError as error:
            raise ImportError(
                "Codex backend requires the optional dependency: uv sync --extra codex"
            ) from error

        factory = self.codex_factory or Codex
        base_instructions, prompt = build_codex_input(messages)
        with tempfile.TemporaryDirectory(prefix="rlm_codex_") as temporary_directory:
            with factory() as codex:
                if self.require_chatgpt_auth:
                    account_response = codex.account()
                    account = getattr(account_response, "account", None)
                    account_root = getattr(account, "root", None)
                    if getattr(account_root, "type", None) != "chatgpt":
                        raise ValueError("Codex backend requires ChatGPT authentication")

                thread = codex.thread_start(
                    approval_mode=ApprovalMode.deny_all,
                    base_instructions=base_instructions,
                    cwd=temporary_directory,
                    ephemeral=True,
                    model=model,
                    sandbox=Sandbox.read_only,
                    service_tier=service_tier,
                )
                pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="rlm-codex-turn")
                future = pool.submit(
                    thread.run,
                    prompt,
                    effort=ReasoningEffort(reasoning_effort),
                )
                try:
                    result = future.result(timeout=timeout)
                except FutureTimeoutError as error:
                    close = getattr(codex, "close", None)
                    if callable(close):
                        close()
                    raise TimeoutError(
                        f"Codex completion timed out after {timeout} seconds"
                    ) from error
                finally:
                    pool.shutdown(wait=False, cancel_futures=True)

        usage = getattr(result, "usage", None)
        last_usage = getattr(usage, "last", None)
        if last_usage is None:
            raise ValueError("Codex response did not include token usage")
        return CodexExecution(
            response=getattr(result, "final_response", None),
            input_tokens=last_usage.input_tokens,
            output_tokens=last_usage.output_tokens,
        )

    async def arun(
        self,
        *,
        messages: list[dict[str, str]],
        model: str,
        timeout: float,
        reasoning_effort: str,
        service_tier: str | None,
    ) -> CodexExecution:
        try:
            from openai_codex import ApprovalMode, AsyncCodex, Sandbox
            from openai_codex.generated.v2_all import ReasoningEffort
        except ImportError as error:
            raise ImportError(
                "Codex backend requires the optional dependency: uv sync --extra codex"
            ) from error

        factory = self.async_codex_factory or AsyncCodex
        base_instructions, prompt = build_codex_input(messages)
        with tempfile.TemporaryDirectory(prefix="rlm_codex_") as temporary_directory:
            async with factory() as codex:
                if self.require_chatgpt_auth:
                    account_response = await codex.account()
                    account = getattr(account_response, "account", None)
                    account_root = getattr(account, "root", None)
                    if getattr(account_root, "type", None) != "chatgpt":
                        raise ValueError("Codex backend requires ChatGPT authentication")

                thread = await codex.thread_start(
                    approval_mode=ApprovalMode.deny_all,
                    base_instructions=base_instructions,
                    cwd=temporary_directory,
                    ephemeral=True,
                    model=model,
                    sandbox=Sandbox.read_only,
                    service_tier=service_tier,
                )
                try:
                    result = await asyncio.wait_for(
                        thread.run(
                            prompt,
                            effort=ReasoningEffort(reasoning_effort),
                        ),
                        timeout=timeout,
                    )
                except TimeoutError as error:
                    raise TimeoutError(
                        f"Codex completion timed out after {timeout} seconds"
                    ) from error

        usage = getattr(result, "usage", None)
        last_usage = getattr(usage, "last", None)
        if last_usage is None:
            raise ValueError("Codex response did not include token usage")
        return CodexExecution(
            response=getattr(result, "final_response", None),
            input_tokens=last_usage.input_tokens,
            output_tokens=last_usage.output_tokens,
        )


class CodexClient(BaseLM):
    def __init__(
        self,
        model_name: str,
        reasoning_effort: str = "medium",
        service_tier: str | None = None,
        require_chatgpt_auth: bool = True,
        executor: CodexExecutor | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(model_name=model_name, **kwargs)
        if reasoning_effort not in SUPPORTED_REASONING_EFFORTS:
            raise ValueError(f"Unsupported reasoning effort: {reasoning_effort}")
        self.reasoning_effort = reasoning_effort
        self.service_tier = service_tier
        self.require_chatgpt_auth = require_chatgpt_auth
        self.executor = executor or SDKCodexExecutor(require_chatgpt_auth=require_chatgpt_auth)
        self.model_call_counts: dict[str, int] = defaultdict(int)
        self.model_input_tokens: dict[str, int] = defaultdict(int)
        self.model_output_tokens: dict[str, int] = defaultdict(int)
        self.last_usage = ModelUsageSummary(0, 0, 0, None)

    def validate_environment(self) -> None:
        if self.require_chatgpt_auth and os.getenv("OPENAI_API_KEY"):
            raise ValueError("OPENAI_API_KEY must be unset when using the Codex backend")

    def completion(
        self,
        prompt: str | list[dict[str, Any]],
        model: str | None = None,
    ) -> str:
        self.validate_environment()
        selected_model = self.require_model(model)
        execution = self.executor.run(
            messages=normalize_messages(prompt),
            model=selected_model,
            timeout=self.timeout,
            reasoning_effort=self.reasoning_effort,
            service_tier=self.service_tier,
        )
        return self.finish_execution(execution, selected_model)

    async def acompletion(
        self,
        prompt: str | list[dict[str, Any]],
        model: str | None = None,
    ) -> str:
        self.validate_environment()
        selected_model = self.require_model(model)
        execution = await self.executor.arun(
            messages=normalize_messages(prompt),
            model=selected_model,
            timeout=self.timeout,
            reasoning_effort=self.reasoning_effort,
            service_tier=self.service_tier,
        )
        return self.finish_execution(execution, selected_model)

    def require_model(self, model: str | None) -> str:
        selected_model = model or self.model_name
        if not selected_model:
            raise ValueError("Model name is required for Codex client")
        return selected_model

    def finish_execution(self, execution: CodexExecution, model: str) -> str:
        if not isinstance(execution.response, str) or not execution.response.strip():
            raise ValueError("Codex returned an empty response")
        self.model_call_counts[model] += 1
        self.model_input_tokens[model] += execution.input_tokens
        self.model_output_tokens[model] += execution.output_tokens
        self.last_usage = ModelUsageSummary(
            total_calls=1,
            total_input_tokens=execution.input_tokens,
            total_output_tokens=execution.output_tokens,
            total_cost=None,
        )
        return execution.response.strip()

    def get_usage_summary(self) -> UsageSummary:
        return UsageSummary(
            model_usage_summaries={
                model: ModelUsageSummary(
                    total_calls=self.model_call_counts[model],
                    total_input_tokens=self.model_input_tokens[model],
                    total_output_tokens=self.model_output_tokens[model],
                    total_cost=None,
                )
                for model in self.model_call_counts
            }
        )

    def get_last_usage(self) -> ModelUsageSummary:
        return self.last_usage
