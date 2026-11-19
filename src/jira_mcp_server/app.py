"""MCP server instance — imported by both server.py and the tool modules."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from mcp.server.mcpserver import MCPServer

from . import __version__


@contextlib.asynccontextmanager
async def _lifespan(app: MCPServer) -> AsyncIterator[None]:  # noqa: ARG001
    """Close the Jira HTTP client on server shutdown."""
    yield
    from .client import _jira_client  # noqa: PLC0415

    if _jira_client is not None:
        await _jira_client.close()


# MCP SDK 2.x: FastMCP was renamed MCPServer. Pass the version explicitly — 2.x
# reports an empty serverInfo.version otherwise.
mcp = MCPServer("jira-mcp", version=__version__, lifespan=_lifespan)
