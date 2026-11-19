"""Tests for the Confluence MCP tool functions."""

from __future__ import annotations

from typing import Any
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


LONG_DOC = (
    "Intro about Knox.\n\n"
    "# Architecture\n\n" + "a" * 3000 + "\n\n"
    "# Configuration\n\nSet up Knox first.\n\n"
    "## Token exchange\n\nConfigure the token exchange endpoint.\n\n" + "b" * 1500 + "\n\n"
    "## Audience\n\n" + "c" * 1500 + "\n"
)


async def _read(doc: ConfluencePage, **kwargs: Any) -> str:
    from jira_mcp_server.confluence_tools import read_confluence_page

    client = MagicMock()
    client.get_page = AsyncMock(return_value=doc)
    with patch(PATCH, return_value=client):
        out = await read_confluence_page("123", **kwargs)
    assert "result" in out, out
    return str(out["result"])


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

    async def test_no_headings_falls_back_to_parts(self) -> None:
        text = await _read(_page(body="x" * 5000), max_chars=1000)
        assert "x" * 1000 in text
        assert "x" * 1001 not in text
        assert "Part 1 of 5" in text
        assert "part=2" in text

    async def test_next_part(self) -> None:
        body = "\n\n".join(f"para{i} " + "p" * 400 for i in range(5))
        text = await _read(_page(body=body), max_chars=1000, part=2)
        assert "Part 2 of" in text
        assert "para0" not in text

    async def test_part_out_of_range(self) -> None:
        text = await _read(_page(body="x" * 3000), max_chars=1000, part=99)
        assert "has 3 parts" in text

    async def test_default_limit_is_15000(self) -> None:
        fits = await _read(_page(body="y" * 15000))
        assert "y" * 15000 in fits
        too_big = await _read(_page(body="y" * 15001))
        assert "Part 1 of 2" in too_big

    async def test_long_page_returns_outline_and_intro_not_body(self) -> None:
        text = await _read(_page(body=LONG_DOC), max_chars=1000)
        assert "## Outline" in text
        assert "1 Architecture" in text
        assert "  2.1 Token exchange" in text
        assert "Intro about Knox." in text
        assert "a" * 100 not in text
        assert 'section="' in text
        assert 'find="' in text
        assert "sub-agent" in text

    async def test_section_by_number_returns_only_that_section(self) -> None:
        text = await _read(_page(body=LONG_DOC), section="2.1", max_chars=5000)
        assert "## Token exchange" in text
        assert "Configure the token exchange endpoint." in text
        assert "a" * 100 not in text
        assert "Section 2.1" in text

    async def test_section_by_title(self) -> None:
        text = await _read(_page(body=LONG_DOC), section="architecture", max_chars=5000)
        assert "a" * 3000 in text

    async def test_section_too_big_with_children_shows_sub_outline(self) -> None:
        text = await _read(_page(body=LONG_DOC), section="2", max_chars=1000)
        assert "## Outline" in text
        assert "2.1 Token exchange" in text
        assert "1 Architecture" not in text
        assert "Set up Knox first." in text  # the section's own lead text

    async def test_huge_leaf_section_is_split_into_parts(self) -> None:
        text = await _read(_page(body=LONG_DOC), section="1", max_chars=1000)
        assert "Part 1 of" in text
        assert 'section="1", part=2' in text

    async def test_ambiguous_section_lists_matches(self) -> None:
        body = "# Overview\n\n" + "a" * 2000 + "\n\n# API\n\n## Overview\n\nb\n"
        text = await _read(_page(body=body), section="Overview", max_chars=1000)
        assert "Several sections match" in text
        assert "1 Overview" in text
        assert "2.1 Overview" in text

    async def test_unknown_section_shows_outline(self) -> None:
        text = await _read(_page(body=LONG_DOC), section="billing", max_chars=1000)
        assert 'No section matches "billing"' in text
        assert "1 Architecture" in text

    async def test_find_returns_numbered_matches(self) -> None:
        text = await _read(_page(body=LONG_DOC), find="token exchange", max_chars=1000)
        assert '## Matches for "token exchange"' in text
        assert "2.1 Token exchange" in text
        assert 'section="2.1"' in text

    async def test_find_no_matches(self) -> None:
        text = await _read(_page(body=LONG_DOC), find="kubernetes", max_chars=1000)
        assert 'No matches for "kubernetes"' in text

    async def test_find_on_short_page_still_searches(self) -> None:
        text = await _read(_page(body="# A\n\nsmall knox page\n"), find="knox")
        assert '## Matches for "knox"' in text

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


class TestReviewFixes:
    async def test_long_intro_is_reachable_with_parts(self) -> None:
        intro = "\n\n".join(f"MARK{i:03d} " + "i" * 200 for i in range(120))
        body = intro + "\n\n# Appendix\n\nsmall\n"
        first = await _read(_page(body=body), max_chars=15000)
        assert "## Outline" in first
        assert "part=2" in first
        later = [await _read(_page(body=body), max_chars=15000, part=n) for n in (2, 3)]
        joined = "".join(later)
        assert "MARK000" in joined
        assert "MARK119" in joined
        assert "Intro part 1 of 2" in later[0]

    async def test_long_section_lead_is_reachable_with_parts(self) -> None:
        lead = "\n\n".join(f"LEAD{i:03d} " + "l" * 200 for i in range(100))
        body = "# One\n\n" + lead + "\n\n## Child\n\nsmall\n\n# Two\n\nx\n"
        first = await _read(_page(body=body), section="1", max_chars=15000)
        assert "## Outline" in first
        assert 'section="1", part=2' in first
        second = await _read(_page(body=body), section="1", max_chars=15000, part=2)
        assert "LEAD000" in second

    async def test_ambiguous_listing_is_capped(self) -> None:
        body = "".join(f"# Topic {i}\n\n" + "t" * 50 + "\n\n" for i in range(300))
        text = await _read(_page(body=body), section="topic", max_chars=1000)
        assert "Several sections match" in text
        assert "Topic 19" in text
        assert "Topic 25" not in text
        assert "280 more" in text


class TestMinorFixes:
    async def test_part_out_of_range_keeps_label_case(self) -> None:
        body = "# One\n\n" + "a" * 2000 + "\n\n# Other\n\n" + "b" * 50
        text = await _read(_page(body=body), section="2", part=5, max_chars=1000)
        assert "Part 5 does not exist: Section 2: Other fits in one part" in text

    async def test_singular_section_count(self) -> None:
        body = "i" * 2500 + "\n\n# Only\n\n" + "z" * 3000
        text = await _read(_page(body=body), max_chars=1000)
        assert "1 section)" in text

    async def test_outline_number_collision_note(self) -> None:
        body = (
            "# Overview\n\n" + "o" * 600 + "\n\n## Intro\n\nx\n\n## Details\n\ny\n\n"
            "# 1.2 Legacy notes\n\n" + "l" * 600 + "\n"
        )
        text = await _read(_page(body=body), section="1.2", max_chars=5000)
        assert "**Section 1.2: Details**" in text
        assert 'own "1.2 Legacy notes" is section 2' in text

    async def test_find_query_too_short(self) -> None:
        text = await _read(_page(body=LONG_DOC), find="a !", max_chars=1000)
        assert "too short" in text

    async def test_find_within_section(self) -> None:
        text = await _read(_page(body=LONG_DOC), find="knox", section="2", max_chars=1000)
        assert "### 2 Configuration" in text
        assert "### Intro" not in text
        assert "within section 2" in text

    async def test_outline_mode_respects_budget(self) -> None:
        body = (
            "i" * 2500
            + "\n\n"
            + "".join(f"# Section {i}\n\n" + "s" * 50 + "\n\n" for i in range(90))
        )
        text = await _read(_page(body=body), max_chars=1000)
        assert "## Outline" in text
        assert len(text) < 1000 + 900  # content within budget, plus fixed header/hints


class TestReview2Fixes:
    async def test_part2_without_intro_says_so(self) -> None:
        body = "# A\n\n" + "a" * 3000 + "\n\n# B\n\n" + "b" * 3000
        text = await _read(_page(body=body), max_chars=1000, part=2)
        assert "no intro text" in text
        assert "0 parts" not in text

    async def test_part2_on_short_page(self) -> None:
        text = await _read(_page(body="# A\n\nshort\n\n# B\n\nshort\n"), part=2)
        assert "fits in one part" in text

    async def test_collision_note_ignores_deeper_numbers(self) -> None:
        body = (
            "# Overview\n\n" + "o" * 600 + "\n\n## Intro\n\nx\n\n## Details\n\ny\n\n"
            "# 1.2.3 Legacy\n\n" + "l" * 600 + "\n"
        )
        text = await _read(_page(body=body), section="1.2", max_chars=5000)
        assert "**Section 1.2: Details**" in text
        assert "Note:" not in text

    async def test_no_match_outline_respects_budget_and_scope(self) -> None:
        body = "# One\n\n" + "".join(f"## Sub {i}\n\n" + "s" * 40 + "\n\n" for i in range(200))
        body += "# Two\n\n" + "t" * 40
        text = await _read(_page(body=body), find="zzzz", section="1", max_chars=1000)
        assert 'No matches for "zzzz" within section 1' in text
        assert "2 Two" not in text
        assert len(text) < 1000 + 600

    async def test_outline_lists_more_than_80_sections_when_budget_allows(self) -> None:
        body = "".join(f"# S{i}\n\n" + "x" * 80 + "\n\n" for i in range(200))
        text = await _read(_page(body=body))
        assert "## Outline" in text
        assert "S199" in text

    async def test_single_section_page_goes_straight_to_parts(self) -> None:
        text = await _read(_page(body="# Title\n\n" + "w" * 20_000), max_chars=15_000)
        assert "## Outline" not in text
        assert "Part 1 of 2" in text

    async def test_tiny_max_chars_is_raised_to_a_floor(self) -> None:
        text = await _read(_page(body="x" * 1000), max_chars=1)
        assert "Part 1 of 5" in text
