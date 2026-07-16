"""MCP server smoke test: an MCP client can list the tools and call one."""

import mcp_server
import tools


class TestMcpServer:
    async def test_lists_the_three_tools_with_schemas(self):
        listed = await mcp_server.mcp.list_tools()
        assert {t.name for t in listed} == {"create_lead", "schedule_meeting", "handoff_to_human"}
        create = next(t for t in listed if t.name == "create_lead")
        props = create.inputSchema["properties"]
        assert "business_name" in props
        assert "description" in props

    async def test_call_returns_a_valid_result(self, monkeypatch):
        async def fake_dispatch(name, args):
            return {"ok": True, "message": f"called {name}", "data": {}}

        monkeypatch.setattr(tools, "dispatch", fake_dispatch)
        content, structured = await mcp_server.mcp.call_tool("schedule_meeting", {"description": "quer conversar"})
        assert structured["result"].startswith("called schedule_meeting")
        assert content[0].text.startswith("called schedule_meeting")

    async def test_call_forwards_args_through_the_shared_dispatch(self, monkeypatch):
        seen = {}

        async def fake_dispatch(name, args):
            seen["name"], seen["args"] = name, args
            return {"ok": True, "message": "ok"}

        monkeypatch.setattr(tools, "dispatch", fake_dispatch)
        await mcp_server.mcp.call_tool("create_lead", {"business_name": "Padaria do Zé", "description": "quer um site"})
        assert seen["name"] == "create_lead"
        assert seen["args"]["business_name"] == "Padaria do Zé"
        assert seen["args"]["description"] == "quer um site"
