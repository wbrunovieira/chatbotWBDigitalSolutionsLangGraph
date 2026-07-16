"""MCP server smoke test: an MCP client can list the tools and call one."""

import json

import pytest

import mcp_server
import tools


def _result(ret) -> dict:
    """Extract the tool's JSON result from a FastMCP call_tool return (content list)."""
    content = ret[0] if isinstance(ret, tuple) else ret
    return json.loads(content[0].text)


class TestMcpServer:
    async def test_lists_the_three_tools_with_schemas(self):
        listed = await mcp_server.mcp.list_tools()
        assert {t.name for t in listed} == {"create_lead", "schedule_meeting", "handoff_to_human"}
        create = next(t for t in listed if t.name == "create_lead")
        props = create.inputSchema["properties"]
        assert "business_name" in props
        assert "description" in props

    async def test_call_returns_structured_result(self, monkeypatch):
        async def fake_dispatch(name, args):
            return {"ok": True, "message": f"called {name}", "data": {"lead_id": "L1"}}

        monkeypatch.setattr(tools, "dispatch", fake_dispatch)
        result = _result(await mcp_server.mcp.call_tool("schedule_meeting", {"description": "x"}))
        # The result exposes ok + message + data, so the calling model can act on it.
        assert result["ok"] is True
        assert result["message"] == "called schedule_meeting"
        assert result["data"]["lead_id"] == "L1"

    async def test_failure_is_raised_as_a_protocol_error(self, monkeypatch):
        # A tool failure (dispatch ok:False) must surface as a protocol-level MCP error, not
        # a dict that reads like success — FastMCP raises ToolError, which becomes isError=True
        # for the client so the model can retry / fall back.
        async def fake_dispatch(name, args):
            return {"ok": False, "message": "handoff WhatsApp", "error": "crm down"}

        monkeypatch.setattr(tools, "dispatch", fake_dispatch)
        with pytest.raises(Exception) as exc:
            await mcp_server.mcp.call_tool("create_lead", {"business_name": "X"})
        assert "handoff WhatsApp" in str(exc.value)

    async def test_binds_mcp_caller_and_forwards_args(self, monkeypatch):
        seen = {}

        async def fake_dispatch(name, args):
            seen["name"], seen["args"], seen["ip"] = name, args, tools._client_ip.get()
            return {"ok": True, "message": "ok"}

        monkeypatch.setattr(tools, "dispatch", fake_dispatch)
        await mcp_server.mcp.call_tool("create_lead", {"business_name": "Padaria do Zé"})
        assert seen["name"] == "create_lead"
        assert seen["args"]["business_name"] == "Padaria do Zé"
        assert seen["ip"] == "mcp"  # tagged MCP -> bypasses the public per-IP lead cap
