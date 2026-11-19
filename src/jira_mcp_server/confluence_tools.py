"""MCP tool definitions for Confluence read operations."""

from __future__ import annotations

from typing import Any

from mcp.types import ToolAnnotations

from .app import mcp
from .confluence import get_confluence_client

_READ_ONLY = ToolAnnotations(readOnlyHint=True)
_DEFAULT_MAX_CHARS = 40_000


def _space_label(name: str | None, key: str | None) -> str | None:
    if name and key:
        return f"{name} ({key})"
    return name or key


def _cursor_hint(cursor: str) -> str:
    return f'*More results available. Call again with `cursor="{cursor}"` to get the next page.*'


@mcp.tool(annotations=_READ_ONLY)
async def search_confluence(
    query: str | None = None,
    space_key: str | None = None,
    cql: str | None = None,
    max_results: int = 10,
    cursor: str | None = None,
) -> dict[str, Any]:
    """
    Search Confluence pages and blog posts.

    Pass `query` for full-text search (e.g. "Knox token exchange"), optionally
    limited to one space with `space_key` (e.g. "ENG"). For anything more
    specific, pass a raw CQL expression in `cql` instead, e.g.
    `title ~ "RFC" AND label = "design"` or `ancestor = 12345`.

    Each result includes its page id; read it with `read_confluence_page`.

    Args:
        query: Free-text search terms.
        space_key: Restrict results to this space key (optional).
        cql: Raw Confluence Query Language expression; used instead of `query`.
        max_results: Results per page (1-50, default 10).
        cursor: Cursor from the previous page to fetch the next one.
    """
    try:
        validated_max = max(1, min(max_results, 50))
        client = get_confluence_client()
        page = await client.search(query, space_key, cql, validated_max, cursor)

        if not page.results:
            return {"result": "No Confluence content found matching the search."}

        count = len(page.results)
        summary = f"Showing {count} result{'s' if count != 1 else ''}"
        if page.total is not None:
            summary += f" (about {page.total} total)"
        lines: list[str] = ["# Confluence Search Results", summary, ""]
        for r in page.results:
            lines.append(f"## {r.title}")
            lines.append(f"**Link:** {r.url}")
            meta = [f"**Type:** {r.type} (page id {r.id})"]
            space = _space_label(r.space_name, r.space_key)
            if space:
                meta.append(f"**Space:** {space}")
            if r.last_modified:
                meta.append(f"**Modified:** {r.last_modified}")
            lines.append("  |  ".join(meta))
            if r.excerpt:
                lines.append(f"> {r.excerpt}")
            lines.append("")
        if page.next_cursor:
            lines.append(_cursor_hint(page.next_cursor))
        return {"result": "\n".join(lines)}
    except Exception as e:
        return {"error": f"Error searching Confluence: {e!s}"}


@mcp.tool(annotations=_READ_ONLY)
async def read_confluence_page(page: str, max_chars: int = _DEFAULT_MAX_CHARS) -> dict[str, Any]:
    """
    Read a Confluence page's full content as markdown.

    Accepts a numeric page id or a full page URL, such as
    https://<site>.atlassian.net/wiki/spaces/ENG/pages/12345/Page+Title
    (short /wiki/x/... links are not supported).

    Args:
        page: Page id or full Confluence page URL.
        max_chars: Truncate the body after this many characters (default 40000).
    """
    try:
        client = get_confluence_client()
        doc = await client.get_page(page)

        lines: list[str] = [f"# {doc.title}", f"**Link:** {doc.url}"]
        meta = [f"**Page id:** {doc.id}"]
        space = _space_label(doc.space_name, doc.space_key)
        if space:
            meta.append(f"**Space:** {space}")
        if doc.version is not None:
            meta.append(f"**Version:** {doc.version}")
        if doc.last_updated:
            meta.append(f"**Updated:** {doc.last_updated}")
        lines += ["  |  ".join(meta), "", "---", ""]

        body = doc.body
        limit = max(1, max_chars)
        if len(body) > limit:
            lines.append(body[:limit])
            lines += [
                "",
                f"*[Content truncated: showing {limit} of {len(body)} characters. "
                "Call again with a larger `max_chars` to read more.]*",
            ]
        else:
            lines.append(body or "*[empty page]*")
        return {"result": "\n".join(lines)}
    except Exception as e:
        return {"error": f"Error reading Confluence page: {e!s}"}


@mcp.tool(annotations=_READ_ONLY)
async def get_confluence_page_children(
    page: str, max_results: int = 25, cursor: str | None = None
) -> dict[str, Any]:
    """
    List the direct child pages (and folders) of a Confluence page.

    Useful for walking a documentation tree, e.g. from a space's overview page.

    Args:
        page: Parent page id or full Confluence page URL.
        max_results: Children per page (1-100, default 25).
        cursor: Cursor from the previous page to fetch the next one.
    """
    try:
        validated_max = max(1, min(max_results, 100))
        client = get_confluence_client()
        result = await client.get_page_children(page, validated_max, cursor)

        if not result.children:
            return {"result": "This page has no child pages."}

        lines: list[str] = [f"# Child pages of {page}", ""]
        for child in result.children:
            entry = f"- **{child.title}** ({child.type}, page id {child.id})"
            if child.url:
                entry += f" — {child.url}"
            lines.append(entry)
        if result.next_cursor:
            lines += ["", _cursor_hint(result.next_cursor)]
        return {"result": "\n".join(lines)}
    except Exception as e:
        return {"error": f"Error listing Confluence page children: {e!s}"}


@mcp.tool(annotations=_READ_ONLY)
async def get_issue_confluence_pages(issue_key: str) -> dict[str, Any]:
    """
    List the Confluence pages linked to a Jira issue (design docs, RFCs, runbooks).

    These are the pages shown under the issue's "Confluence pages" / "mentioned
    in" links. Read any of them with `read_confluence_page`.

    Args:
        issue_key: The issue key (e.g., PROJ-123).
    """
    try:
        client = get_confluence_client()
        pages = await client.get_issue_linked_pages(issue_key)

        if not pages:
            return {"result": f"No Confluence pages are linked to {issue_key}."}

        lines: list[str] = [f"# Confluence pages linked to {issue_key}", ""]
        for p in pages:
            entry = f"- **{p.title}** — {p.url}"
            page_id = f"page id {p.page_id}" if p.page_id else None
            details = [d for d in (p.relationship, page_id) if d]
            if details:
                entry += f" ({', '.join(details)})"
            lines.append(entry)
        lines += ["", "*Read a page with `read_confluence_page` using its page id or URL.*"]
        return {"result": "\n".join(lines)}
    except Exception as e:
        return {"error": f"Error getting linked Confluence pages: {e!s}"}
