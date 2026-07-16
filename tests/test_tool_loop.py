"""The agent tool-calling loop: the model decides to call tools, results feed back, bounded."""

import pytest

import nodes
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
    monkeypatch.setattr(nodes, "start_llm_generation", lambda **kw: None)
    monkeypatch.setattr(nodes, "end_llm_generation", lambda **kw: None)


class TestToolLoop:
    async def test_no_tool_call_returns_text(self, monkeypatch):
        monkeypatch.setattr(nodes, "_deepseek_chat", sequence_chat([text_response("Olá! 👋")]))
        reply, results = await nodes._run_tool_loop([], None, None)
        assert reply == "Olá! 👋"
        assert results == []

    async def test_model_calls_create_lead_then_answers(self, monkeypatch):
        monkeypatch.setattr(nodes, "_deepseek_chat", sequence_chat([
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
        monkeypatch.setattr(nodes, "_deepseek_chat", sequence_chat([
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

        monkeypatch.setattr(nodes, "_deepseek_chat", fake)

        async def fake_dispatch(name, args):
            return {"ok": True, "message": "ok"}

        monkeypatch.setattr(tools, "dispatch", fake_dispatch)
        reply, results = await nodes._run_tool_loop([], None, None, max_iters=2)
        assert reply == "resposta final"
        assert len(results) == 2  # one dispatch per bounded iteration, then a forced text answer

    async def test_malformed_api_response_degrades_gracefully(self, monkeypatch):
        monkeypatch.setattr(nodes, "_deepseek_chat", sequence_chat([{"error": "500"}]))
        reply, results = await nodes._run_tool_loop([], None, None)
        assert "WhatsApp" in reply
        assert results == []
