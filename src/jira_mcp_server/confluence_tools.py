"""MCP tool definitions for Confluence read operations."""

from __future__ import annotations

import re
from typing import Any

from mcp.types import ToolAnnotations

from .app import mcp
from .confluence import ConfluencePage, get_confluence_client
from .sections import (
    Section,
    children_of,
    find_sections,
    parse_sections,
    render_outline,
    search_sections,
    search_terms,
    split_parts,
)

_READ_ONLY = ToolAnnotations(readOnlyHint=True)
_DEFAULT_MAX_CHARS = 15_000  # ~4k tokens: keeps a single page read a modest share of context
_INTRO_CHARS = 2_000
_MAX_MATCHES = 20  # cap ambiguous-section listings so they can't flood the context
_OUTLINE_MAX_ENTRIES = 1_000  # in tools the char budget, not an entry count, limits the outline
_MIN_MAX_CHARS = 200  # tiny budgets only produce thousands of useless parts
_NAV_HINT = (
    '*Read one section with `section="<number>"` (e.g. the number from the outline), '
    'or search this page with `find="keywords"`.*'
)
_SUBAGENT_TIP = (
    "*Tip: if you can delegate to a sub-agent, have it read the relevant sections "
    "and report back only what you need.*"
)


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
async def read_confluence_page(
    page: str,
    section: str | None = None,
    find: str | None = None,
    part: int = 1,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> dict[str, Any]:
    """
    Read a Confluence page as markdown, without flooding your context on long pages.

    Pages up to `max_chars` (default 15000) are returned whole. Longer pages
    return a numbered outline (section sizes) plus the intro; then:
      - `section="2.1"` (or a heading title) reads just that section,
      - `find="keywords"` lists the best-matching sections with snippets
        (combine with `section` to search only within that section),
      - `part=2`, `3`, ... pages through text without headings, or through a
        long intro shown in outline mode (part 1 is the outline).

    For long docs, if you can delegate to a sub-agent, have it navigate the page
    with these options and return only the facts you need.

    Accepts a numeric page id or a full page URL, such as
    https://<site>.atlassian.net/wiki/spaces/ENG/pages/12345/Page+Title
    (short /wiki/x/... links are not supported).

    Args:
        page: Page id or full Confluence page URL.
        section: Section number from the outline (e.g. "2.1") or a heading title.
        find: Keywords to search for within the page.
        part: Which part to read when text is split into parts (default 1).
        max_chars: Approximate size budget for the returned content, excluding the
            short page header and navigation hints (default 15000).
    """
    try:
        client = get_confluence_client()
        doc = await client.get_page(page)
        lines = _page_header(doc)
        budget = max(_MIN_MAX_CHARS, max_chars)
        lines.append(_page_content(doc.body, section, find, part, budget))
        return {"result": "\n".join(lines)}
    except Exception as e:
        return {"error": f"Error reading Confluence page: {e!s}"}


def _page_header(doc: ConfluencePage) -> list[str]:
    meta = [f"**Page id:** {doc.id}"]
    space = _space_label(doc.space_name, doc.space_key)
    if space:
        meta.append(f"**Space:** {space}")
    if doc.version is not None:
        meta.append(f"**Version:** {doc.version}")
    if doc.last_updated:
        meta.append(f"**Updated:** {doc.last_updated}")
    return [f"# {doc.title}", f"**Link:** {doc.url}", "  |  ".join(meta), "", "---", ""]


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _page_content(md: str, section: str | None, find: str | None, part: int, budget: int) -> str:
    intro, sections = parse_sections(md)
    query = find.strip() if find else ""
    if query and not search_terms(query):
        return f'Search query "{query}" is too short: use words of at least 2 characters.'

    scope: Section | None = None
    note = ""
    if section and section.strip():
        wanted = section.strip()
        matches = find_sections(sections, wanted)
        if not matches:
            outline = render_outline(sections, max_chars=budget) or "(this page has no headings)"
            return f'No section matches "{wanted}". Outline:\n\n{outline}'
        if len(matches) > 1:
            listing = "\n".join(f"- {s.number} {s.title}" for s in matches[:_MAX_MATCHES])
            if len(matches) > _MAX_MATCHES:
                listing += f"\n- … {len(matches) - _MAX_MATCHES} more (use a more specific title)"
            return (
                f'Several sections match "{wanted}":\n\n{listing}\n\n'
                "*Call again with the section number, e.g. "
                f'`section="{matches[0].number}"`.*'
            )
        scope = matches[0]
        note = _number_collision_note(sections, scope, wanted)

    if query:
        return note + _render_find(md, intro, sections, query, budget, scope)
    if scope is not None:
        return note + _render_scope(
            text=md[scope.start : scope.end],
            label=f"Section {scope.number}: {scope.title}",
            children=children_of(sections, scope),
            lead=md[scope.body_start : scope.own_end].strip(),
            section_arg=scope.number,
            part=part,
            budget=budget,
        )
    return _render_scope(
        text=md,
        label="Page",
        children=sections,
        lead=intro,
        section_arg=None,
        part=part,
        budget=budget,
    )


def _number_collision_note(sections: list[Section], chosen: Section, wanted: str) -> str:
    """Warn when an outline number also starts another heading ('1.2 Foo') in the page."""
    number = wanted.rstrip(".")
    if chosen.number != number:
        return ""
    # "1.2 Foo", "1.2. Foo", "1.2) Foo" match; "1.2.3 Foo" does not.
    own = re.compile(rf"^{re.escape(number)}(?:[.)](?!\d)|\s|$)")
    others = [s for s in sections if s is not chosen and own.match(s.title)]
    if not others:
        return ""
    other = others[0]
    return (
        f"*Note: section numbers refer to this outline; the page's own "
        f'"{other.title}" is section {other.number}.*\n\n'
    )


def _render_scope(
    *,
    text: str,
    label: str,
    children: list[Section],
    lead: str,
    section_arg: str | None,
    part: int,
    budget: int,
) -> str:
    """Whole text if it fits; else an outline of its subsections; else numbered parts."""
    prefix = f"**{label}**\n\n" if section_arg else ""
    if len(text) <= budget:
        if part == 1:
            return prefix + (text or "*[empty page]*")
        return f"Part {part} does not exist: {label} fits in one part (read it without `part`)."

    nav = f'section="{section_arg}", ' if section_arg else ""
    if len(children) == 1 and len(lead) <= _INTRO_CHARS:
        # An outline with a single entry (e.g. a page whose only heading is its title)
        # would just cost an extra call; page through the text directly.
        children = []
    if children:
        # part=1 is the outline; part=2.. page through the intro/lead text, which
        # belongs to no subsection and would otherwise be unreachable.
        if part > 1:
            if not lead:
                return (
                    f"Part {part} does not exist: {label} has no intro text before its "
                    'first section. Read a section with `section="<number>"`.'
                )
            lead_parts = split_parts(lead, budget)
            index = part - 2
            if index >= len(lead_parts):
                last = f" to `part={len(lead_parts) + 1}`" if len(lead_parts) > 1 else ""
                return (
                    f"Part {part} does not exist: the intro has "
                    f"{_plural(len(lead_parts), 'part')}, read with `{nav}part=2`{last}."
                )
            footer = f"*Intro part {index + 1} of {len(lead_parts)}.*"
            if index + 1 < len(lead_parts):
                footer += f" *Call again with `{nav}part={part + 1}` to continue.*"
            return "\n".join([prefix + lead_parts[index], "", "---", footer, _NAV_HINT])

        # Keep outline + intro preview within the budget (the intro gets at most a third).
        shown = lead[: min(_INTRO_CHARS, budget // 3)]
        out = [
            f"**{label} is long ({len(text):,} characters, "
            f"{_plural(len(children), 'section')}). "
            "Showing the outline instead of the full text.**",
            "",
            "## Outline",
            "",
            render_outline(
                children,
                max_entries=_OUTLINE_MAX_ENTRIES,
                max_chars=max(1, budget - len(shown)),
            ),
        ]
        if lead:
            out += ["", "## Intro", "", shown]
            if len(lead) > len(shown):
                out += [
                    "",
                    f"*[Intro continues: {len(lead):,} characters in total. "
                    f"Read it in full with `{nav}part=2`.]*",
                ]
        out += ["", "---", _NAV_HINT, _SUBAGENT_TIP]
        return "\n".join(out)

    parts = split_parts(text, budget)
    if not 1 <= part <= len(parts):
        return f"Part {part} does not exist: {label} has {_plural(len(parts), 'part')}."
    out = [prefix + parts[part - 1], "", "---"]
    footer = f"*Part {part} of {len(parts)} ({len(text):,} characters in total).*"
    if part < len(parts):
        footer += f" *Call again with `{nav}part={part + 1}` to continue.*"
    out += [footer, _SUBAGENT_TIP]
    return "\n".join(out)


def _render_find(
    md: str,
    intro: str,
    sections: list[Section],
    query: str,
    budget: int,
    scope: Section | None = None,
) -> str:
    hits = search_sections(md, intro, sections, query, scope=scope)
    where = f" within section {scope.number}" if scope else ""
    if not hits:
        outline_of = children_of(sections, scope) if scope else sections
        outline = render_outline(outline_of, max_entries=_OUTLINE_MAX_ENTRIES, max_chars=budget)
        return f'No matches for "{query}"{where or " in this page"}.' + (
            f"\n\nOutline:\n\n{outline}" if outline else ""
        )
    out = [f'## Matches for "{query}"{where}', ""]
    for hit in hits:
        heading = f"{hit.section.number} {hit.section.title}" if hit.section else "Intro"
        out += [f"### {heading}", f"> {hit.snippet}", ""]
    first = next((h.section for h in hits if h.section), None)
    if first:
        out.append(f'*Read a match in full with `section="{first.number}"`.*')
    return "\n".join(out)


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
