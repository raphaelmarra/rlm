"""Run an isolated RLM through an existing ChatGPT Codex login."""

import os

from rlm import RLM

if os.getenv("OPENAI_API_KEY"):
    raise RuntimeError("Unset OPENAI_API_KEY; this example requires ChatGPT authentication")

with RLM(
    backend="codex",
    backend_kwargs={
        "model_name": "gpt-5.6-terra",
        "reasoning_effort": "medium",
    },
    environment="docker",
    max_depth=1,
    max_iterations=6,
    max_timeout=600,
    max_concurrent_subcalls=1,
) as rlm:
    result = rlm.completion(
        "Find the sum of the integers in this context and return only the result.\n\n"
        "[17, 23, 41, 59]"
    )

print(result.response)
