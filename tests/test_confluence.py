"""Tests for the Confluence client (shares HTTP session and credentials with JiraClient)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from jira_mcp_server.client import JiraApiError, JiraClient, JiraConfig
from jira_mcp_server.confluence import (
    ConfluenceClient,
    build_search_cql,
    clean_excerpt,
    parse_page_id,
)

SITE = "https://acme.atlassian.net"


def _adf(text: str) -> str:
    """Confluence returns the ADF body as a JSON-encoded string."""
    return json.dumps(
        {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
        }
    )


def _resp(data: Any, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.raise_for_status = MagicMock()
    r.headers = {"content-type": "application/json"}
    r.json.return_value = data
    return r


class _Router:
    """Mock httpx request routing by URL path suffix; records calls."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    async def __call__(self, method: str, url: str, **kwargs: Any) -> MagicMock:
        self.calls.append((method, url, kwargs))
        path = url.split("?")[0]
        for suffix, data in self.routes.items():
            if path.endswith(suffix):
                if isinstance(data, Exception):
                    raise data
                return _resp(data)
        msg = f"unexpected request {method} {url}"
        raise AssertionError(msg)

    def find(self, suffix: str) -> tuple[str, str, dict[str, Any]]:
        return next(c for c in self.calls if c[1].split("?")[0].endswith(suffix))


def _client(routes: dict[str, Any]) -> tuple[ConfluenceClient, _Router]:
    jira = JiraClient(JiraConfig(base_url=SITE, email="a@b.com", api_token="t"))
    router = _Router(routes)
    jira.session = AsyncMock()
    # Pass the bound async method: AsyncMock only awaits coroutine-function side effects.
    jira.session.request = AsyncMock(side_effect=router.__call__)
    return ConfluenceClient(jira), router


# ---------------------------------------------------------------------------
# parse_page_id
# ---------------------------------------------------------------------------


class TestParsePageId:
    def test_plain_id(self) -> None:
        assert parse_page_id(" 12364448766 ", SITE) == "12364448766"

    def test_modern_page_url(self) -> None:
        url = f"{SITE}/wiki/spaces/ENG/pages/12364448766/Knox+RFC+8693+Token+Exchange"
        assert parse_page_id(url, SITE) == "12364448766"

    def test_legacy_viewpage_url(self) -> None:
        assert parse_page_id(f"{SITE}/wiki/pages/viewpage.action?pageId=42", SITE) == "42"

    def test_edit_url(self) -> None:
        assert parse_page_id(f"{SITE}/wiki/spaces/ENG/pages/edit-v2/77", SITE) == "77"

    def test_rejects_other_site(self) -> None:
        with pytest.raises(ValueError, match="different Atlassian site"):
            parse_page_id("https://other.atlassian.net/wiki/spaces/X/pages/1/T", SITE)

    def test_rejects_tiny_link(self) -> None:
        with pytest.raises(ValueError, match="page id"):
            parse_page_id(f"{SITE}/wiki/x/AbCdEf", SITE)

    def test_rejects_garbage(self) -> None:
        with pytest.raises(ValueError, match="Not a Confluence page id or URL"):
            parse_page_id("not a page", SITE)


# ---------------------------------------------------------------------------
# build_search_cql / clean_excerpt
# ---------------------------------------------------------------------------


class TestBuildSearchCql:
    def test_text_query_bounded_to_pages_and_blogposts(self) -> None:
        cql = build_search_cql(query="token exchange")
        assert cql == 'type in (page, blogpost) AND text ~ "token exchange"'

    def test_escapes_quotes_and_backslashes(self) -> None:
        cql = build_search_cql(query='say "hi" \\ bye')
        assert 'text ~ "say \\"hi\\" \\\\ bye"' in cql

    def test_space_filter(self) -> None:
        cql = build_search_cql(query="knox", space_key="ENG")
        assert cql.endswith(' AND space = "ENG"')

    def test_raw_cql_passthrough(self) -> None:
        assert build_search_cql(cql="label = rfc") == "label = rfc"

    def test_raw_cql_with_space_is_combined(self) -> None:
        assert build_search_cql(cql="label = rfc", space_key="ENG") == (
            '(label = rfc) AND space = "ENG"'
        )

    def test_rejects_invalid_space_key(self) -> None:
        with pytest.raises(ValueError, match="space key"):
            build_search_cql(query="x", space_key='ENG" OR space = "HR')

    def test_requires_query_or_cql(self) -> None:
        with pytest.raises(ValueError, match="search query or a CQL"):
            build_search_cql()


class TestCleanExcerpt:
    def test_highlight_markers_become_bold(self) -> None:
        assert clean_excerpt("use @@@hl@@@Knox@@@endhl@@@ here") == "use **Knox** here"

    def test_unescapes_html_and_collapses_whitespace(self) -> None:
        assert clean_excerpt("a &amp; b\n\n  c") == "a & b c"


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


SEARCH_RESPONSE = {
    "results": [
        {
            "content": {"id": "123", "type": "page", "title": "Knox Setup"},
            "title": "@@@hl@@@Knox@@@endhl@@@ Setup",
            "excerpt": "configure @@@hl@@@Knox@@@endhl@@@ token exchange",
            "url": "/spaces/ENG/pages/123/Knox+Setup",
            "resultGlobalContainer": {"title": "Engineering", "displayUrl": "/spaces/ENG"},
            "lastModified": "2026-10-01T10:00:00.000Z",
        }
    ],
    "totalSize": 37,
    "_links": {
        "base": f"{SITE}/wiki",
        "next": "/rest/api/search?next=true&cursor=abc%3D%3D&limit=10&cql=x",
    },
}


class TestSearch:
    async def test_calls_v1_search_with_cql_and_limit(self) -> None:
        client, router = _client({"/wiki/rest/api/search": SEARCH_RESPONSE})
        await client.search(query="knox", max_results=10)
        method, url, kwargs = router.find("/wiki/rest/api/search")
        assert method == "GET"
        assert url == f"{SITE}/wiki/rest/api/search"
        assert kwargs["params"]["cql"] == 'type in (page, blogpost) AND text ~ "knox"'
        assert kwargs["params"]["limit"] == 10
        assert "cursor" not in kwargs["params"]

    async def test_parses_results(self) -> None:
        client, _ = _client({"/wiki/rest/api/search": SEARCH_RESPONSE})
        page = await client.search(query="knox")
        assert page.total == 37
        assert page.next_cursor == "abc=="
        r = page.results[0]
        assert r.id == "123"
        assert r.title == "Knox Setup"  # un-highlighted content title
        assert r.type == "page"
        assert r.space_key == "ENG"
        assert r.space_name == "Engineering"
        assert r.url == f"{SITE}/wiki/spaces/ENG/pages/123/Knox+Setup"
        assert r.excerpt == "configure **Knox** token exchange"
        assert r.last_modified == "2026-10-01T10:00:00.000Z"

    async def test_cursor_sent_on_next_page(self) -> None:
        client, router = _client({"/wiki/rest/api/search": {"results": [], "_links": {}}})
        page = await client.search(query="knox", cursor="abc==")
        params = router.find("/wiki/rest/api/search")[2]["params"]
        assert params["cursor"] == "abc=="
        assert params["next"] == "true"
        assert page.next_cursor is None


# ---------------------------------------------------------------------------
# get_page
# ---------------------------------------------------------------------------


PAGE_RESPONSE = {
    "id": "123",
    "title": "Knox Setup",
    "spaceId": "98",
    "parentId": "100",
    "version": {"number": 7, "createdAt": "2026-10-02T09:00:00.000Z"},
    "body": {"atlas_doc_format": {"representation": "atlas_doc_format", "value": _adf("Hi")}},
    "_links": {"base": f"{SITE}/wiki", "webui": "/spaces/ENG/pages/123/Knox+Setup"},
}


class TestGetPage:
    async def test_reads_v2_page_as_adf_and_converts(self) -> None:
        client, router = _client(
            {
                "/wiki/api/v2/pages/123": PAGE_RESPONSE,
                "/wiki/api/v2/spaces/98": {"id": "98", "key": "ENG", "name": "Engineering"},
            }
        )
        page = await client.get_page(f"{SITE}/wiki/spaces/ENG/pages/123/Knox+Setup")
        _, url, kwargs = router.find("/wiki/api/v2/pages/123")
        assert url == f"{SITE}/wiki/api/v2/pages/123"
        assert kwargs["params"]["body-format"] == "atlas_doc_format"
        assert page.id == "123"
        assert page.title == "Knox Setup"
        assert page.body == "Hi"
        assert page.version == 7
        assert page.last_updated == "2026-10-02T09:00:00.000Z"
        assert page.url == f"{SITE}/wiki/spaces/ENG/pages/123/Knox+Setup"
        assert page.space_key == "ENG"
        assert page.space_name == "Engineering"
        assert page.parent_id == "100"

    async def test_space_lookup_failure_is_non_fatal(self) -> None:
        client, _ = _client(
            {
                "/wiki/api/v2/pages/123": PAGE_RESPONSE,
                "/wiki/api/v2/spaces/98": JiraApiError("Jira API error: 403", 403),
            }
        )
        page = await client.get_page("123")
        assert page.title == "Knox Setup"
        assert page.space_key is None

    async def test_empty_body(self) -> None:
        data = {**PAGE_RESPONSE, "body": {}, "spaceId": None}
        client, _ = _client({"/wiki/api/v2/pages/123": data})
        page = await client.get_page("123")
        assert page.body == ""


# ---------------------------------------------------------------------------
# get_page_children
# ---------------------------------------------------------------------------


class TestGetPageChildren:
    async def test_lists_direct_children_with_cursor(self) -> None:
        client, router = _client(
            {
                "/wiki/api/v2/pages/123/direct-children": {
                    "results": [
                        {"id": "200", "title": "Child A", "type": "page"},
                        {"id": "201", "title": "Folder B", "type": "folder"},
                    ],
                    "_links": {"next": "/wiki/api/v2/pages/123/direct-children?cursor=nxt"},
                }
            }
        )
        page = await client.get_page_children("123", max_results=2, cursor="prev")
        params = router.find("/direct-children")[2]["params"]
        assert params == {"limit": 2, "cursor": "prev"}
        assert page.next_cursor == "nxt"
        assert [c.title for c in page.children] == ["Child A", "Folder B"]
        assert page.children[0].url == f"{SITE}/wiki/pages/viewpage.action?pageId=200"
        assert page.children[1].type == "folder"


# ---------------------------------------------------------------------------
# get_issue_linked_pages (Jira remote links -> Confluence)
# ---------------------------------------------------------------------------


class TestIssueLinkedPages:
    async def test_filters_confluence_links_and_extracts_page_ids(self) -> None:
        client, router = _client(
            {
                "/rest/api/3/issue/PROJ-1/remotelink": [
                    {
                        "globalId": "appId=abc&pageId=555",
                        "application": {"type": "com.atlassian.confluence", "name": "Confluence"},
                        "relationship": "mentioned in",
                        "object": {
                            "title": "Design doc",
                            "url": f"{SITE}/wiki/pages/viewpage.action?pageId=555",
                        },
                    },
                    {
                        # No application info, but a Confluence URL
                        "object": {
                            "title": "RFC",
                            "url": f"{SITE}/wiki/spaces/ENG/pages/777/RFC",
                        }
                    },
                    {
                        "application": {"type": "com.github", "name": "GitHub"},
                        "object": {"title": "PR #1", "url": "https://github.com/x/y/pull/1"},
                    },
                ]
            }
        )
        pages = await client.get_issue_linked_pages("PROJ-1")
        _, url, _ = router.find("/remotelink")
        assert url == f"{SITE}/rest/api/3/issue/PROJ-1/remotelink"
        assert [(p.title, p.page_id) for p in pages] == [("Design doc", "555"), ("RFC", "777")]
        assert pages[0].relationship == "mentioned in"

    async def test_other_site_link_has_no_page_id(self) -> None:
        """A page id from another site would read the wrong page on ours."""
        client, _ = _client(
            {
                "/rest/api/3/issue/PROJ-1/remotelink": [
                    {
                        "globalId": "appId=zzz&pageId=999",
                        "application": {"type": "com.atlassian.confluence"},
                        "object": {
                            "title": "Partner doc",
                            "url": "https://partner.atlassian.net/wiki/spaces/P/pages/999/Doc",
                        },
                    }
                ]
            }
        )
        pages = await client.get_issue_linked_pages("PROJ-1")
        assert pages[0].title == "Partner doc"
        assert pages[0].page_id is None

    async def test_no_links(self) -> None:
        client, _ = _client({"/rest/api/3/issue/PROJ-1/remotelink": []})
        assert await client.get_issue_linked_pages("PROJ-1") == []
