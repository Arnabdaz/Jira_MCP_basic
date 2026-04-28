"""FastMCP application instance — imported by both server.py and tools.py."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from mcp.server.fastmcp import FastMCP


@contextlib.asynccontextmanager
async def _lifespan(app: FastMCP) -> AsyncIterator[None]:  # noqa: ARG001
    """Close the Jira HTTP client on server shutdown."""
    yield
    from .client import _jira_client  # noqa: PLC0415

    if _jira_client is not None:
        await _jira_client.close()


mcp = FastMCP("jira-mcp", lifespan=_lifespan)
