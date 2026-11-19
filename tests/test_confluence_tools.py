"""Tests for the Confluence MCP tool functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from jira_mcp_server.confluence import (
    ConfluenceChild,
    ConfluenceChildrenPage,
    ConfluenceLinkedPage,
    ConfluencePage,
    ConfluenceSearchPage,
    ConfluenceSearchResult,
)

PATCH = "jira_mcp_server.confluence_tools.get_confluence_client"


def _result(i: int = 1) -> ConfluenceSearchResult:
    return ConfluenceSearchResult(
        id=str(i),
        title=f"Doc {i}",
        type="page",
        url=f"https://acme.atlassian.net/wiki/spaces/ENG/pages/{i}/Doc",
        space_key="ENG",
        space_name="Engineering",
        excerpt="about **Knox**",
        last_modified="2026-10-01T10:00:00.000Z",
    )


def _page(body: str = "# Intro\n\nHello") -> ConfluencePage:
    return ConfluencePage(
        id="123",
        title="Knox Setup",
        url="https://acme.atlassian.net/wiki/spaces/ENG/pages/123/Knox",
        body=body,
        space_key="ENG",
        space_name="Engineering",
        version=7,
        last_updated="2026-10-02T09:00:00.000Z",
    )


class TestSearchConfluence:
    async def test_renders_results_and_cursor_hint(self) -> None:
        from jira_mcp_server.confluence_tools import search_confluence

        client = MagicMock()
        client.search = AsyncMock(
            return_value=ConfluenceSearchPage(results=[_result()], next_cursor="c2", total=12)
        )
        with patch(PATCH, return_value=client):
            out = await search_confluence(query="knox", space_key="ENG")
        text = out["result"]
        assert "Doc 1" in text
        assert "page id 1" in text
        assert "Engineering (ENG)" in text
        assert "about **Knox**" in text
        assert "about 12" in text
        assert 'cursor="c2"' in text
        client.search.assert_awaited_once_with("knox", "ENG", None, 10, None)

    async def test_clamps_max_results(self) -> None:
        from jira_mcp_server.confluence_tools import search_confluence

        client = MagicMock()
        client.search = AsyncMock(return_value=ConfluenceSearchPage(results=[_result()]))
        with patch(PATCH, return_value=client):
            await search_confluence(cql="label = rfc", max_results=999)
        assert client.search.await_args.args[3] == 50

    async def test_no_results(self) -> None:
        from jira_mcp_server.confluence_tools import search_confluence

        client = MagicMock()
        client.search = AsyncMock(return_value=ConfluenceSearchPage(results=[], total=0))
        with patch(PATCH, return_value=client):
            out = await search_confluence(query="nothing")
        assert "No Confluence content found" in out["result"]

    async def test_error_dict(self) -> None:
        from jira_mcp_server.confluence_tools import search_confluence

        client = MagicMock()
        client.search = AsyncMock(side_effect=ValueError("Provide a search query"))
        with patch(PATCH, return_value=client):
            out = await search_confluence()
        assert "error" in out
        assert "Provide a search query" in out["error"]


class TestReadConfluencePage:
    async def test_renders_metadata_and_body(self) -> None:
        from jira_mcp_server.confluence_tools import read_confluence_page

        client = MagicMock()
        client.get_page = AsyncMock(return_value=_page())
        with patch(PATCH, return_value=client):
            out = await read_confluence_page("123")
        text = out["result"]
        assert text.startswith("# Knox Setup")
        assert "Engineering (ENG)" in text
        assert "Version:** 7" in text
        assert "Hello" in text
        client.get_page.assert_awaited_once_with("123")

    async def test_truncates_long_body(self) -> None:
        from jira_mcp_server.confluence_tools import read_confluence_page

        client = MagicMock()
        client.get_page = AsyncMock(return_value=_page(body="x" * 5000))
        with patch(PATCH, return_value=client):
            out = await read_confluence_page("123", max_chars=1000)
        text = out["result"]
        assert "x" * 1000 in text
        assert "x" * 1001 not in text
        assert "truncated" in text
        assert "5000" in text

    async def test_empty_page_body(self) -> None:
        from jira_mcp_server.confluence_tools import read_confluence_page

        client = MagicMock()
        client.get_page = AsyncMock(return_value=_page(body=""))
        with patch(PATCH, return_value=client):
            out = await read_confluence_page("123")
        assert "*[empty page]*" in out["result"]

    async def test_bad_reference_returns_error(self) -> None:
        from jira_mcp_server.confluence_tools import read_confluence_page

        client = MagicMock()
        client.get_page = AsyncMock(side_effect=ValueError("different Atlassian site"))
        with patch(PATCH, return_value=client):
            out = await read_confluence_page("https://other.atlassian.net/wiki/x")
        assert "different Atlassian site" in out["error"]


class TestGetConfluencePageChildren:
    async def test_lists_children(self) -> None:
        from jira_mcp_server.confluence_tools import get_confluence_page_children

        client = MagicMock()
        client.get_page_children = AsyncMock(
            return_value=ConfluenceChildrenPage(
                children=[
                    ConfluenceChild(id="200", title="Child A", type="page", url="https://u/200"),
                    ConfluenceChild(id="201", title="Folder B", type="folder"),
                ],
                next_cursor="n2",
            )
        )
        with patch(PATCH, return_value=client):
            out = await get_confluence_page_children("123")
        text = out["result"]
        assert "Child A" in text
        assert "page id 200" in text
        assert "Folder B" in text
        assert "folder" in text
        assert 'cursor="n2"' in text

    async def test_no_children(self) -> None:
        from jira_mcp_server.confluence_tools import get_confluence_page_children

        client = MagicMock()
        client.get_page_children = AsyncMock(return_value=ConfluenceChildrenPage())
        with patch(PATCH, return_value=client):
            out = await get_confluence_page_children("123")
        assert "no child pages" in out["result"]


class TestGetIssueConfluencePages:
    async def test_lists_linked_pages(self) -> None:
        from jira_mcp_server.confluence_tools import get_issue_confluence_pages

        client = MagicMock()
        client.get_issue_linked_pages = AsyncMock(
            return_value=[
                ConfluenceLinkedPage(
                    title="Design doc",
                    url="https://acme.atlassian.net/wiki/x",
                    page_id="555",
                    relationship="mentioned in",
                )
            ]
        )
        with patch(PATCH, return_value=client):
            out = await get_issue_confluence_pages("PROJ-1")
        text = out["result"]
        assert "PROJ-1" in text
        assert "Design doc" in text
        assert "page id 555" in text
        assert "mentioned in" in text
        assert "read_confluence_page" in text

    async def test_none_linked(self) -> None:
        from jira_mcp_server.confluence_tools import get_issue_confluence_pages

        client = MagicMock()
        client.get_issue_linked_pages = AsyncMock(return_value=[])
        with patch(PATCH, return_value=client):
            out = await get_issue_confluence_pages("PROJ-1")
        assert "No Confluence pages are linked" in out["result"]


class TestMissingConfig:
    async def test_all_tools_return_error_dict(self) -> None:
        from jira_mcp_server.confluence_tools import (
            get_confluence_page_children,
            get_issue_confluence_pages,
            read_confluence_page,
            search_confluence,
        )

        with patch(PATCH, side_effect=ValueError("Missing env vars")):
            results = [
                await search_confluence(query="x"),
                await read_confluence_page("1"),
                await get_confluence_page_children("1"),
                await get_issue_confluence_pages("PROJ-1"),
            ]
        for r in results:
            assert "error" in r, r


class TestRegistration:
    async def test_tools_registered_as_read_only(self) -> None:
        import jira_mcp_server.server  # noqa: F401  (registers tools)
        from jira_mcp_server.app import mcp

        tools = {t.name: t for t in await mcp.list_tools()}
        for name in (
            "search_confluence",
            "read_confluence_page",
            "get_confluence_page_children",
            "get_issue_confluence_pages",
        ):
            assert name in tools, name
            assert tools[name].annotations is not None
            assert tools[name].annotations.readOnlyHint is True
