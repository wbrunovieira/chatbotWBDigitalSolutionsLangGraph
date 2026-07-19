"""The agent tool-calling loop: the model decides to call tools, results feed back, bounded."""

import pytest

import nodes
import langfuse_client
import tools


def tool_call_response(name, arguments, content=None):
    return {
        "choices": [{"message": {
            "content": content,
            "tool_calls": [{"id": "call_1", "function": {"name": name, "arguments": arguments}}],
        }}],
        "usage": {},
    }


def text_response(text):
    return {"choices": [{"message": {"content": text}}], "usage": {}}


def sequence_chat(responses):
    state = {"n": 0}

    async def fake(messages, temperature=0.7, use_tools=False):
        r = responses[min(state["n"], len(responses) - 1)]
        state["n"] += 1
        return r

    return fake


@pytest.fixture(autouse=True)
def quiet_langfuse(monkeypatch):
    monkeypatch.setattr(langfuse_client, "start_llm_generation", lambda **kw: None)
    monkeypatch.setattr(langfuse_client, "end_llm_generation", lambda **kw: None)


class TestToolLoop:
    async def test_no_tool_call_returns_text(self, monkeypatch):
        monkeypatch.setattr(nodes.generation, "_deepseek_chat", sequence_chat([text_response("Olá! 👋")]))
        reply, results = await nodes._run_tool_loop([], None, None)
        assert reply == "Olá! 👋"
        assert results == []

    async def test_model_calls_create_lead_then_answers(self, monkeypatch):
        monkeypatch.setattr(nodes.generation, "_deepseek_chat", sequence_chat([
            tool_call_response("create_lead", '{"business_name": "Padaria do Zé"}'),
            text_response("Registrei seu contato! 😊"),
        ]))
        dispatched = []

        async def fake_dispatch(name, args):
            dispatched.append((name, args))
            return {"ok": True, "message": "saved", "data": {"lead_id": "L1"}}

        monkeypatch.setattr(tools, "dispatch", fake_dispatch)

        reply, results = await nodes._run_tool_loop([], None, None)
        assert reply == "Registrei seu contato! 😊"
        assert dispatched == [("create_lead", {"business_name": "Padaria do Zé"})]
        assert results[0]["tool"] == "create_lead"
        assert results[0]["result"]["ok"] is True

    async def test_hallucinated_args_become_empty_and_still_dispatch(self, monkeypatch):
        # Invalid JSON in the tool-call arguments must not crash; it parses to {} and
        # dispatch handles the validation failure gracefully.
        monkeypatch.setattr(nodes.generation, "_deepseek_chat", sequence_chat([
            tool_call_response("create_lead", "not-json{{"),
            text_response("ok"),
        ]))
        seen = []

        async def fake_dispatch(name, args):
            seen.append(args)
            return {"ok": False, "message": "handoff"}

        monkeypatch.setattr(tools, "dispatch", fake_dispatch)
        reply, results = await nodes._run_tool_loop([], None, None)
        assert seen == [{}]
        assert reply == "ok"

    async def test_loop_is_bounded_and_forces_final_text(self, monkeypatch):
        async def fake(messages, temperature=0.7, use_tools=False):
            # Keep requesting a tool while tools are offered; answer in text once they're off.
            return tool_call_response("create_lead", "{}") if use_tools else text_response("resposta final")

        monkeypatch.setattr(nodes.generation, "_deepseek_chat", fake)

        async def fake_dispatch(name, args):
            return {"ok": True, "message": "ok"}

        monkeypatch.setattr(tools, "dispatch", fake_dispatch)
        reply, results = await nodes._run_tool_loop([], None, None, max_iters=2)
        assert reply == "resposta final"
        assert len(results) == 2  # one dispatch per bounded iteration, then a forced text answer

    async def test_malformed_api_response_degrades_gracefully(self, monkeypatch):
        monkeypatch.setattr(nodes.generation, "_deepseek_chat", sequence_chat([{"error": "500"}]))
        reply, results = await nodes._run_tool_loop([], None, None)
        assert "WhatsApp" in reply
        assert results == []

    async def test_multiple_tool_calls_in_one_turn_all_get_tool_messages(self, monkeypatch):
        # Every tool_call id MUST get a matching role:tool message or DeepSeek 400s the
        # next call. The loop only exercised one call/turn before; this guards two.
        multi = {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "a", "function": {"name": "create_lead", "arguments": '{"business_name":"X"}'}},
            {"id": "b", "function": {"name": "schedule_meeting", "arguments": "{}"}},
        ]}}], "usage": {}}
        monkeypatch.setattr(nodes.generation, "_deepseek_chat", sequence_chat([multi, text_response("ok")]))

        async def fake_dispatch(name, args):
            return {"ok": True, "message": name}

        monkeypatch.setattr(tools, "dispatch", fake_dispatch)
        messages = []
        reply, results = await nodes._run_tool_loop(messages, None, None)
        assert reply == "ok"
        assert len(results) == 2
        tool_msgs = [m for m in messages if m.get("role") == "tool"]
        assert {m["tool_call_id"] for m in tool_msgs} == {"a", "b"}


class TestGenerateResponseWiring:
    async def test_degrades_on_transport_error_instead_of_raising(self, monkeypatch):
        # The whole-node guarantee: a non-ReadTimeout transport error must NOT 500 —
        # this fails before the #2 fix (generate_response caught ReadTimeout only).
        import httpx as _httpx

        async def boom(messages, temperature=0.7, use_tools=False):
            raise _httpx.ConnectError("connection refused")

        monkeypatch.setattr(nodes.generation, "_deepseek_chat", boom)
        state = {"user_input": "oi", "augmented_input": "responda", "langfuse_trace": None, "messages": []}
        result = await nodes.generate_response(state)
        assert result["step"] == "error_generation"
        assert "WhatsApp" in result["response"]


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.headers = {}
        self.text = str(payload)

    def json(self):
        return self._payload


# Long enough to trip needs_revision (len > config.REVISION_MAX_LENGTH), so these tests
# exercise the revision LLM path and its failure fallbacks rather than the short-answer skip.
LONG_RESPONSE = "Olá! " + (
    "Podemos desenvolver sites, automações e soluções de IA sob medida para o seu negócio. " * 8
)


class TestReviseResponseWiring:
    async def test_degrades_when_api_returns_error_body_instead_of_500(self, monkeypatch):
        # An expired/invalid DeepSeek key returns JSON without "choices". revise_response
        # must fall back to the already-generated answer, not raise KeyError -> 500.
        # (Reproduces the crash the one-command demo surfaced with a bad key.)
        monkeypatch.setattr(langfuse_client, "get_prompt", lambda *a, **k: None)

        async def fake_cc(*a, **k):
            return _FakeResp({"error": {"message": "Unauthorized"}})

        monkeypatch.setattr(nodes.deepseek_client, "chat_completion", fake_cc)
        original = LONG_RESPONSE
        state = {"response": original, "language": "pt-BR", "langfuse_trace": None}

        result = await nodes.revise_response(state)

        assert result["step"] == "revise_response_skipped"
        assert result["revised_response"] == original

    async def test_degrades_on_non_json_gateway_body(self, monkeypatch):
        # A 502 gateway returns HTML, not JSON -> response.json() raises. Must fall back to
        # the original answer, not 500 (the json() parse used to be outside the guard).
        monkeypatch.setattr(langfuse_client, "get_prompt", lambda *a, **k: None)

        class _Html:
            text = "<html>502 Bad Gateway</html>"
            headers = {}

            def json(self):
                raise ValueError("no json")

        async def fake_cc(*a, **k):
            return _Html()

        monkeypatch.setattr(nodes.deepseek_client, "chat_completion", fake_cc)
        result = await nodes.revise_response({"response": LONG_RESPONSE, "language": "pt-BR"})
        assert result["step"] == "revise_response_skipped"
        assert result["revised_response"] == LONG_RESPONSE

    async def test_timeout_keeps_original_not_an_english_error(self, monkeypatch):
        import httpx as _httpx

        monkeypatch.setattr(langfuse_client, "get_prompt", lambda *a, **k: None)

        async def boom(*a, **k):
            raise _httpx.ReadTimeout("slow")

        monkeypatch.setattr(nodes.deepseek_client, "chat_completion", boom)
        result = await nodes.revise_response({"response": LONG_RESPONSE, "language": "pt-BR"})
        assert result["revised_response"] == LONG_RESPONSE   # not an English error string
        assert result["step"] == "revise_response_skipped"
