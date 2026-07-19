"""The shared DeepSeek transport seam builds the right request (url, model, headers, options)."""

import pytest

import deepseek_client


class _Recorder:
    def __init__(self):
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return "RESP"


@pytest.fixture
def rec(monkeypatch):
    recorder = _Recorder()
    monkeypatch.setattr(deepseek_client.httpx, "AsyncClient", lambda *a, **k: recorder)
    return recorder


class TestChatCompletion:
    async def test_basic_body_and_headers(self, rec):
        out = await deepseek_client.chat_completion(
            [{"role": "user", "content": "hi"}], temperature=0.3
        )
        call = rec.calls[0]
        assert call["url"] == deepseek_client.DEEPSEEK_API_URL
        assert call["json"]["model"] == deepseek_client.DEEPSEEK_MODEL
        assert call["json"]["temperature"] == 0.3
        assert call["json"]["messages"] == [{"role": "user", "content": "hi"}]
        assert "tools" not in call["json"]
        assert "response_format" not in call["json"]
        assert call["headers"]["Authorization"].startswith("Bearer ")
        assert call["headers"]["Content-Type"] == "application/json"
        assert out == "RESP"  # returns the raw response for the caller to unpack

    async def test_tools_response_format_and_extra_headers(self, rec):
        await deepseek_client.chat_completion(
            [],
            tools=[{"type": "function"}],
            response_format={"type": "json_object"},
            extra_headers={"X-Foo": "1"},
        )
        call = rec.calls[0]
        assert call["json"]["tools"] == [{"type": "function"}]
        assert call["json"]["tool_choice"] == "auto"
        assert call["json"]["response_format"] == {"type": "json_object"}
        assert call["headers"]["X-Foo"] == "1"  # merged, not replacing auth
        assert call["headers"]["Authorization"].startswith("Bearer ")
