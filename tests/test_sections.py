"""Tests for long-document section navigation."""

from __future__ import annotations

from jira_mcp_server.sections import (
    children_of,
    find_sections,
    parse_sections,
    render_outline,
    search_sections,
    split_parts,
)

DOC = """Intro paragraph about Knox.

# Overview

Knox brokers tokens.

## Goals

Exchange tokens per RFC 8693.

#### Deep detail

Not numbered.

## Non-goals

No SAML.

# Configuration

Set up the topology.

## Token exchange

Configure the token exchange endpoint and audience.

### Audience

Use the service audience.

# Troubleshooting

401 errors mean the token expired.
"""


class TestParseSections:
    def test_intro_and_numbering(self) -> None:
        intro, sections = parse_sections(DOC)
        assert intro == "Intro paragraph about Knox."
        assert [(s.number, s.title) for s in sections] == [
            ("1", "Overview"),
            ("1.1", "Goals"),
            ("1.2", "Non-goals"),
            ("2", "Configuration"),
            ("2.1", "Token exchange"),
            ("2.1.1", "Audience"),
            ("3", "Troubleshooting"),
        ]

    def test_fourth_level_heading_stays_in_text(self) -> None:
        _, sections = parse_sections(DOC)
        goals = next(s for s in sections if s.number == "1.1")
        assert "#### Deep detail" in DOC[goals.start : goals.end]
        assert "Not numbered." in DOC[goals.start : goals.end]

    def test_section_end_covers_subsections(self) -> None:
        _, sections = parse_sections(DOC)
        config = next(s for s in sections if s.number == "2")
        text = DOC[config.start : config.end]
        assert text.startswith("# Configuration")
        assert "### Audience" in text
        assert "Troubleshooting" not in text
        assert config.size == config.end - config.start

    def test_own_end_stops_at_first_child(self) -> None:
        _, sections = parse_sections(DOC)
        config = next(s for s in sections if s.number == "2")
        own = DOC[config.start : config.own_end]
        assert "Set up the topology." in own
        assert "Token exchange" not in own
        assert DOC[config.body_start : config.own_end].strip() == "Set up the topology."

    def test_depth_normalised_when_doc_starts_at_h2(self) -> None:
        _, sections = parse_sections("## A\n\nx\n\n### B\n\ny\n\n## C\n\nz\n")
        assert [(s.number, s.depth) for s in sections] == [("1", 1), ("1.1", 2), ("2", 1)]

    def test_hash_lines_in_code_fence_are_not_headings(self) -> None:
        md = "# Setup\n\n```bash\n# install deps\nuv sync\n```\n\n# Run\n\ngo\n"
        _, sections = parse_sections(md)
        assert [s.title for s in sections] == ["Setup", "Run"]

    def test_no_headings(self) -> None:
        intro, sections = parse_sections("just text\n\nmore text")
        assert sections == []
        assert intro == "just text\n\nmore text"

    def test_empty(self) -> None:
        assert parse_sections("") == ("", [])


class TestChildrenOf:
    def test_whole_page(self) -> None:
        _, sections = parse_sections(DOC)
        assert children_of(sections, None) == sections

    def test_descendants_only(self) -> None:
        _, sections = parse_sections(DOC)
        config = next(s for s in sections if s.number == "2")
        assert [s.number for s in children_of(sections, config)] == ["2.1", "2.1.1"]


class TestRenderOutline:
    def test_lists_numbers_titles_sizes_with_indent(self) -> None:
        _, sections = parse_sections(DOC)
        outline = render_outline(sections)
        lines = outline.splitlines()
        assert lines[0].startswith("1 Overview")
        assert any(line.startswith("  1.1 Goals") for line in lines)
        assert any(line.startswith("    2.1.1 Audience") for line in lines)
        assert "chars" in lines[0]

    def test_collapses_to_two_levels_when_too_long(self) -> None:
        md = "".join(f"# S{i}\n\n## T{i}\n\n### U{i}\n\nx\n\n" for i in range(30))
        _, sections = parse_sections(md)
        assert len(sections) == 90
        outline = render_outline(sections, max_entries=80)
        assert "U0" not in outline
        assert "T0" in outline
        assert "30 deeper sections not shown" in outline


class TestFindSections:
    def test_by_number(self) -> None:
        _, sections = parse_sections(DOC)
        assert [s.title for s in find_sections(sections, "2.1")] == ["Token exchange"]

    def test_by_exact_title_case_insensitive(self) -> None:
        _, sections = parse_sections(DOC)
        assert [s.number for s in find_sections(sections, "troubleshooting")] == ["3"]

    def test_by_substring(self) -> None:
        _, sections = parse_sections(DOC)
        assert [s.number for s in find_sections(sections, "goal")] == ["1.1", "1.2"]

    def test_exact_title_beats_substring(self) -> None:
        _, sections = parse_sections(DOC)
        assert [s.number for s in find_sections(sections, "Goals")] == ["1.1"]

    def test_ambiguous_section_lists_matches(self) -> None:
        _, sections = parse_sections("# Overview\n\na\n\n# API\n\n## Overview\n\nb\n")
        assert [s.number for s in find_sections(sections, "Overview")] == ["1", "2.1"]

    def test_no_match(self) -> None:
        _, sections = parse_sections(DOC)
        assert find_sections(sections, "billing") == []


class TestSearchSections:
    def test_ranks_all_terms_above_some(self) -> None:
        intro, sections = parse_sections(DOC)
        hits = search_sections(DOC, intro, sections, "token exchange")
        assert hits[0].section is not None
        assert hits[0].section.number == "2.1"
        assert "token exchange" in hits[0].snippet.lower()

    def test_case_insensitive_and_limit(self) -> None:
        intro, sections = parse_sections(DOC)
        hits = search_sections(DOC, intro, sections, "KNOX", limit=1)
        assert len(hits) == 1

    def test_intro_hit_has_no_section(self) -> None:
        intro, sections = parse_sections(DOC)
        hits = search_sections(DOC, intro, sections, "intro paragraph")
        assert hits[0].section is None

    def test_no_hits(self) -> None:
        intro, sections = parse_sections(DOC)
        assert search_sections(DOC, intro, sections, "kubernetes") == []

    def test_snippet_is_bounded(self) -> None:
        md = "# Big\n\n" + ("filler " * 500) + "needle " + ("filler " * 500)
        intro, sections = parse_sections(md)
        hits = search_sections(md, intro, sections, "needle")
        assert "needle" in hits[0].snippet
        assert len(hits[0].snippet) <= 420


class TestSplitParts:
    def test_short_text_single_part(self) -> None:
        assert split_parts("hello", 100) == ["hello"]

    def test_splits_at_paragraph_boundaries(self) -> None:
        text = "\n\n".join(f"para {i} " + "x" * 40 for i in range(10))
        parts = split_parts(text, 120)
        assert all(len(p) <= 120 for p in parts)
        assert all(p.startswith("para ") for p in parts)
        assert "".join(p.replace("\n", "") for p in parts).count("para") == 10

    def test_oversized_paragraph_is_hard_cut(self) -> None:
        parts = split_parts("y" * 250, 100)
        assert [len(p) for p in parts] == [100, 100, 50]


class TestPathologicalInput:
    def test_long_heading_line_parses_quickly(self) -> None:
        """Regression: an overlapping heading regex backtracked quadratically."""
        import time

        line = "# " + " #" * 50_000 + "x"
        started = time.perf_counter()
        _, sections = parse_sections(line + "\n\nbody\n")
        assert time.perf_counter() - started < 0.5
        assert len(sections) == 1

    def test_closing_hashes_are_stripped_from_title(self) -> None:
        _, sections = parse_sections("## Setup ##\n\nx\n\n## C# tips\n\ny\n")
        assert [s.title for s in sections] == ["Setup", "C# tips"]
