"""The LangGraph checkpointer gives the agent short-term conversation memory (#9)."""

import pytest
from langgraph.graph import END, StateGraph
from langgraph.checkpoint.memory import MemorySaver

import langfuse_client
import nodes
from graph_config import ChatState


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    monkeypatch.setattr(langfuse_client, "start_llm_generation", lambda **kw: None)
    monkeypatch.setattr(langfuse_client, "end_llm_generation", lambda **kw: None)
    monkeypatch.setattr(langfuse_client, "get_prompt", lambda *a, **k: None)


def _one_node_graph():
    wf = StateGraph(ChatState)
    wf.add_node("gen", nodes.generation.generate_response)
    wf.set_entry_point("gen")
    wf.add_edge("gen", END)
    return wf.compile(checkpointer=MemorySaver())


class TestConversationMemory:
    async def test_second_turn_sees_the_first_turn(self, monkeypatch):
        seen = []

        async def fake_chat(messages, temperature=0.7, use_tools=False):
            seen.append(messages)
            return {"choices": [{"message": {"content": "resposta do bot"}}], "usage": {}}

        monkeypatch.setattr(nodes.generation, "_deepseek_chat", fake_chat)

        graph = _one_node_graph()
        cfg = {"configurable": {"thread_id": "conv-1"}}

        await graph.ainvoke({"user_input": "quero um site novo", "language": "pt-BR"}, cfg)
        await graph.ainvoke({"user_input": "e quanto custa?", "language": "pt-BR"}, cfg)

        # The LLM call on turn 2 must include turn 1's exchange (persisted by the checkpointer).
        turn2 = seen[-1]
        contents = " ".join(m["content"] for m in turn2)
        assert "quero um site novo" in contents      # turn 1's user message
        assert "resposta do bot" in contents          # turn 1's assistant reply
        assert "e quanto custa?" in contents           # turn 2's current message

    async def test_separate_threads_do_not_share_memory(self, monkeypatch):
        seen = []

        async def fake_chat(messages, temperature=0.7, use_tools=False):
            seen.append(messages)
            return {"choices": [{"message": {"content": "ok"}}], "usage": {}}

        monkeypatch.setattr(nodes.generation, "_deepseek_chat", fake_chat)
        graph = _one_node_graph()

        await graph.ainvoke({"user_input": "sou da thread A", "language": "pt-BR"},
                            {"configurable": {"thread_id": "A"}})
        await graph.ainvoke({"user_input": "sou da thread B", "language": "pt-BR"},
                            {"configurable": {"thread_id": "B"}})

        # thread B must NOT see thread A's message.
        assert "sou da thread A" not in " ".join(m["content"] for m in seen[-1])


class TestThreadIsolationForSharedUsers:
    """The 'anon' default user_id must not make strangers share a memory thread (blocker fix)."""

    def test_real_user_id_keys_stable_memory(self):
        import main
        assert main._memory_thread_id("user-42") == "user-42"

    def test_anonymous_visitors_get_isolated_ephemeral_threads(self):
        import main
        t1 = main._memory_thread_id("anon")
        t2 = main._memory_thread_id("anon")
        assert t1 != t2                       # two anon visitors do NOT share memory
        assert t1.startswith("ephemeral-")
        assert main._memory_thread_id("")  != main._memory_thread_id("")   # empty id too
