"""Read-only Confluence Cloud client.

Confluence lives on the same Atlassian site as Jira (``<site>/wiki``) and accepts
the same email + API token, so this client reuses :class:`JiraClient`'s HTTP
session and credentials rather than needing its own configuration.

API versions (verified against Atlassian's published OpenAPI specs):
- Search uses REST v1 ``GET /wiki/rest/api/search`` (CQL); v2 has no search.
- Pages, spaces and children use REST v2 ``/wiki/api/v2/...``.
- Ticket -> page links come from Jira ``GET /rest/api/3/issue/{key}/remotelink``.
"""

from __future__ import annotations

import html
import json
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel

from .adf import extract_text
from .client import JiraApiError, JiraClient, get_jira_client

_SPACE_KEY_RE = re.compile(r"^[A-Za-z0-9_~-]+$")
_PAGE_PATH_RE = re.compile(r"/pages/(?:[a-z0-9-]+/)?(\d+)")
_PAGE_ID_QUERY_RE = re.compile(r"(?:^|[?&])pageId=(\d+)")
_SPACE_URL_RE = re.compile(r"/spaces/([^/?#]+)")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ConfluenceSearchResult(BaseModel):
    id: str
    title: str
    type: str  # page, blogpost, ...
    url: str
    space_key: str | None = None
    space_name: str | None = None
    excerpt: str = ""
    last_modified: str | None = None


class ConfluenceSearchPage(BaseModel):
    results: list[ConfluenceSearchResult] = []
    next_cursor: str | None = None
    total: int | None = None


class ConfluencePage(BaseModel):
    id: str
    title: str
    url: str
    body: str  # markdown converted from ADF
    space_key: str | None = None
    space_name: str | None = None
    version: int | None = None
    last_updated: str | None = None
    parent_id: str | None = None


class ConfluenceChild(BaseModel):
    id: str
    title: str
    type: str  # page, folder, whiteboard, database, embed
    url: str | None = None


class ConfluenceChildrenPage(BaseModel):
    children: list[ConfluenceChild] = []
    next_cursor: str | None = None


class ConfluenceLinkedPage(BaseModel):
    title: str
    url: str
    page_id: str | None = None
    relationship: str | None = None


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def parse_page_id(ref: str, site_url: str) -> str:
    """Return the numeric page id from an id or a Confluence page URL on ``site_url``."""
    ref = ref.strip()
    if ref.isdigit():
        return ref
    parsed = urlparse(ref)
    if not parsed.scheme or not parsed.netloc:
        msg = f"Not a Confluence page id or URL: {ref!r}"
        raise ValueError(msg)
    site_host = urlparse(site_url).hostname
    if parsed.hostname != site_host:
        msg = (
            f"That page is on a different Atlassian site ({parsed.hostname}); "
            f"this server is configured for {site_host}."
        )
        raise ValueError(msg)
    match = _PAGE_PATH_RE.search(parsed.path) or _PAGE_ID_QUERY_RE.search(parsed.query)
    if match:
        return match.group(1)
    msg = (
        f"Could not find a page id in {ref!r}. Short links (/wiki/x/...) are not "
        "supported; open the page and copy its full URL, or pass the numeric page id."
    )
    raise ValueError(msg)


def _cql_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def build_search_cql(
    query: str | None = None, space_key: str | None = None, cql: str | None = None
) -> str:
    """Build a CQL query: full-text search over pages/blog posts, or a raw CQL override."""
    if space_key is not None and not _SPACE_KEY_RE.match(space_key):
        msg = f"Invalid space key: {space_key!r}"
        raise ValueError(msg)
    space_clause = f" AND space = {_cql_string(space_key)}" if space_key else ""
    if cql and cql.strip():
        base = cql.strip()
        return f"({base}){space_clause}" if space_clause else base
    if query and query.strip():
        return f"type in (page, blogpost) AND text ~ {_cql_string(query.strip())}{space_clause}"
    msg = "Provide a search query or a CQL expression."
    raise ValueError(msg)


def clean_excerpt(excerpt: str) -> str:
    """Turn Confluence highlight markers into bold and normalise whitespace/entities."""
    text = excerpt.replace("@@@hl@@@", "**").replace("@@@endhl@@@", "**")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _cursor_from_link(link: str | None) -> str | None:
    if not link:
        return None
    values = parse_qs(urlparse(link).query).get("cursor")
    return values[0] if values else None


def _is_confluence_link(link: dict[str, Any]) -> bool:
    app = link.get("application") or {}
    marker = f"{app.get('type', '')} {app.get('name', '')}".lower()
    url = (link.get("object") or {}).get("url", "")
    return "confluence" in marker or "/wiki/" in url


def _page_id_from_link(link: dict[str, Any], site_url: str) -> str | None:
    """Page id for a link on ``site_url``; None for other sites (their ids aren't ours)."""
    url_host = urlparse((link.get("object") or {}).get("url", "")).hostname
    if url_host and url_host != urlparse(site_url).hostname:
        return None
    match = _PAGE_ID_QUERY_RE.search(link.get("globalId") or "")
    if match:
        return match.group(1)
    parsed = urlparse((link.get("object") or {}).get("url", ""))
    match = _PAGE_PATH_RE.search(parsed.path) or _PAGE_ID_QUERY_RE.search(parsed.query)
    return match.group(1) if match else None


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class ConfluenceClient:
    """Read-only Confluence Cloud client sharing a JiraClient's session and site."""

    def __init__(self, jira: JiraClient) -> None:
        self._http = jira
        self.site_url = jira.base_url
        self.wiki_url = f"{jira.base_url}/wiki"

    async def search(
        self,
        query: str | None = None,
        space_key: str | None = None,
        cql: str | None = None,
        max_results: int = 10,
        cursor: str | None = None,
    ) -> ConfluenceSearchPage:
        """Search pages and blog posts with CQL (REST v1 search)."""
        params: dict[str, Any] = {
            "cql": build_search_cql(query, space_key, cql),
            "limit": max_results,
        }
        if cursor:
            params["cursor"] = cursor
            params["next"] = "true"
        data = await self._http.request_path("GET", "wiki/rest/api/search", params=params)
        base = (data.get("_links") or {}).get("base") or self.wiki_url
        results = []
        for item in data.get("results", []):
            content = item.get("content") or {}
            if not content.get("id"):
                continue  # non-content results (users, spaces)
            container = item.get("resultGlobalContainer") or {}
            space_match = _SPACE_URL_RE.search(container.get("displayUrl") or "")
            results.append(
                ConfluenceSearchResult(
                    id=str(content["id"]),
                    title=content.get("title") or clean_excerpt(item.get("title", "")),
                    type=content.get("type", "page"),
                    url=f"{base}{item.get('url', '')}",
                    space_key=space_match.group(1) if space_match else None,
                    space_name=container.get("title"),
                    excerpt=clean_excerpt(item.get("excerpt", "")),
                    last_modified=item.get("lastModified"),
                )
            )
        return ConfluenceSearchPage(
            results=results,
            next_cursor=_cursor_from_link((data.get("_links") or {}).get("next")),
            total=data.get("totalSize"),
        )

    async def get_page(self, page_ref: str) -> ConfluencePage:
        """Read a page by id or URL; the ADF body is converted to markdown."""
        page_id = parse_page_id(page_ref, self.site_url)
        data = await self._http.request_path(
            "GET", f"wiki/api/v2/pages/{page_id}", params={"body-format": "atlas_doc_format"}
        )
        raw_body = ((data.get("body") or {}).get("atlas_doc_format") or {}).get("value")
        body = extract_text(json.loads(raw_body)) if raw_body else None

        space_key = space_name = None
        if data.get("spaceId"):
            try:
                space = await self._http.request_path(
                    "GET", f"wiki/api/v2/spaces/{data['spaceId']}"
                )
                space_key, space_name = space.get("key"), space.get("name")
            except JiraApiError:
                pass  # space details are a nicety; the page itself was readable

        links = data.get("_links") or {}
        version = data.get("version") or {}
        return ConfluencePage(
            id=str(data.get("id", page_id)),
            title=data.get("title", ""),
            url=f"{links.get('base') or self.wiki_url}{links.get('webui', '')}",
            body=body or "",
            space_key=space_key,
            space_name=space_name,
            version=version.get("number"),
            last_updated=version.get("createdAt"),
            parent_id=data.get("parentId"),
        )

    async def get_page_children(
        self, page_ref: str, max_results: int = 25, cursor: str | None = None
    ) -> ConfluenceChildrenPage:
        """List the direct children (pages, folders, ...) of a page."""
        page_id = parse_page_id(page_ref, self.site_url)
        params: dict[str, Any] = {"limit": max_results}
        if cursor:
            params["cursor"] = cursor
        data = await self._http.request_path(
            "GET", f"wiki/api/v2/pages/{page_id}/direct-children", params=params
        )
        children = [
            ConfluenceChild(
                id=str(c.get("id", "")),
                title=c.get("title", ""),
                type=c.get("type", "page"),
                url=(
                    f"{self.wiki_url}/pages/viewpage.action?pageId={c.get('id')}"
                    if c.get("type", "page") == "page"
                    else None
                ),
            )
            for c in data.get("results", [])
        ]
        return ConfluenceChildrenPage(
            children=children,
            next_cursor=_cursor_from_link((data.get("_links") or {}).get("next")),
        )

    async def get_issue_linked_pages(self, issue_key: str) -> list[ConfluenceLinkedPage]:
        """Confluence pages linked from a Jira issue (via Jira remote links)."""
        data = await self._http.request_path("GET", f"rest/api/3/issue/{issue_key}/remotelink")
        links = data if isinstance(data, list) else [data] if data else []
        return [
            ConfluenceLinkedPage(
                title=(link.get("object") or {}).get("title") or "Untitled",
                url=(link.get("object") or {}).get("url", ""),
                page_id=_page_id_from_link(link, self.site_url),
                relationship=link.get("relationship"),
            )
            for link in links
            if _is_confluence_link(link)
        ]


_confluence_client: ConfluenceClient | None = None


def get_confluence_client() -> ConfluenceClient:
    """Return the Confluence client singleton, built on the shared Jira client."""
    global _confluence_client  # noqa: PLW0603
    if _confluence_client is None:
        _confluence_client = ConfluenceClient(get_jira_client())
    return _confluence_client
