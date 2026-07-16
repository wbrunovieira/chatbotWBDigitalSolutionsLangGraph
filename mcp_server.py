"""
MCP server exposing the agent's tools over the Model Context Protocol.

Any MCP client — Claude Desktop, Cursor, the MCP Inspector — can list and call the SAME
create_lead / schedule_meeting / handoff_to_human that the in-app LangGraph agent uses.
One tool implementation (`tools.py`), two consumers (the agent and MCP). Calls go through
`tools.dispatch`, so they inherit the same Pydantic validation, timeout + retry, per-IP
lead cap, and graceful fallback.

Run (stdio transport):  python mcp_server.py
"""

from typing import Optional

from mcp.server.fastmcp import FastMCP

import tools

mcp = FastMCP("wb-digital-solutions")


@mcp.tool()
async def create_lead(
    business_name: str,
    contact_name: Optional[str] = None,
    contact_whatsapp: Optional[str] = None,
    contact_email: Optional[str] = None,
    description: str = "",
) -> str:
    """Save an interested person or company as a lead in the WB Digital Solutions CRM.
    Provide whatever the person shared; only business_name is required."""
    result = await tools.dispatch("create_lead", {
        "business_name": business_name,
        "contact_name": contact_name,
        "contact_whatsapp": contact_whatsapp,
        "contact_email": contact_email,
        "description": description,
    })
    return result["message"]


@mcp.tool()
async def schedule_meeting(business_name: Optional[str] = None, description: str = "") -> str:
    """Return the direct link to book a meeting with the WB Digital Solutions team
    (and capture the lead)."""
    result = await tools.dispatch("schedule_meeting", {
        "business_name": business_name,
        "description": description,
    })
    return result["message"]


@mcp.tool()
async def handoff_to_human(reason: str = "") -> str:
    """Hand the conversation to a human on WhatsApp."""
    result = await tools.dispatch("handoff_to_human", {"reason": reason})
    return result["message"]


if __name__ == "__main__":
    mcp.run()
