import os

import pytest

from rlm.clients.codex import CodexClient


@pytest.mark.skipif(
    os.getenv("RLM_LIVE_CODEX") != "1",
    reason="requires RLM_LIVE_CODEX=1",
)
def test_live_codex_subscription_returns_marker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = CodexClient(model_name="gpt-5.6-terra", timeout=180)

    assert client.completion("Reply with exactly RLM_CODEX_OK") == "RLM_CODEX_OK"
    assert client.get_last_usage().total_input_tokens > 0
    assert client.get_last_usage().total_output_tokens > 0
    assert client.get_last_usage().total_cost is None
