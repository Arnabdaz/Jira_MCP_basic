"""Tests for the ADF (Atlassian Document Format) parser."""

from __future__ import annotations

from typing import Any

from jira_mcp_server.adf import extract_text


def test_none_returns_none() -> None:
    assert extract_text(None) is None


def test_empty_string_returns_empty() -> None:
    assert extract_text("") == ""


def test_plain_string_passthrough() -> None:
    assert extract_text("hello world") == "hello world"


def test_paragraph() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Hello world"}]}],
    }
    result = extract_text(adf)
    assert result is not None
    assert "Hello world" in result


def test_heading_level_2() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": "Section Title"}],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "## Section Title" in result


def test_bullet_list() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Item one"}],
                            }
                        ],
                    },
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Item two"}],
                            }
                        ],
                    },
                ],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "- Item one" in result
    assert "- Item two" in result


def test_ordered_list() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "orderedList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "First step"}],
                            }
                        ],
                    },
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Second step"}],
                            }
                        ],
                    },
                ],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "1. First step" in result
    assert "2. Second step" in result


def test_code_block() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "codeBlock",
                "attrs": {"language": "python"},
                "content": [{"type": "text", "text": "print('hello')"}],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "```python" in result
    assert "print('hello')" in result
    assert "```" in result


def test_inline_code() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "myFunc", "marks": [{"type": "code"}]}],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "`myFunc`" in result


def test_bold_and_italic_marks() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "bold", "marks": [{"type": "strong"}]},
                    {"type": "text", "text": " and "},
                    {"type": "text", "text": "italic", "marks": [{"type": "em"}]},
                ],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "**bold**" in result
    assert "*italic*" in result


def test_table() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "table",
                "content": [
                    {
                        "type": "tableRow",
                        "content": [
                            {
                                "type": "tableHeader",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "Name"}],
                                    }
                                ],
                            },
                            {
                                "type": "tableHeader",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "Value"}],
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "type": "tableRow",
                        "content": [
                            {
                                "type": "tableCell",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "foo"}],
                                    }
                                ],
                            },
                            {
                                "type": "tableCell",
                                "content": [
                                    {
                                        "type": "paragraph",
                                        "content": [{"type": "text", "text": "bar"}],
                                    }
                                ],
                            },
                        ],
                    },
                ],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "Name" in result
    assert "Value" in result
    assert "foo" in result
    assert "bar" in result
    assert "|" in result


def test_unknown_node_recurses_into_children() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "unknownFutureNode",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Fallback text"}],
                    }
                ],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "Fallback text" in result


def test_blockquote() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "blockquote",
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Quoted text"}],
                    }
                ],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "> Quoted text" in result


def test_hard_break() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "line one"},
                    {"type": "hardBreak"},
                    {"type": "text", "text": "line two"},
                ],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "line one" in result
    assert "line two" in result
    assert "\n" in result


def test_rule() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [{"type": "rule"}],
    }
    result = extract_text(adf)
    assert result is not None
    assert "---" in result


def test_panel() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "panel",
                "attrs": {"panelType": "warning"},
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Watch out!"}],
                    }
                ],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "[WARNING]" in result
    assert "Watch out!" in result


def test_mention_adds_at_prefix() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "mention", "attrs": {"text": "Alice"}},
                ],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "@Alice" in result


def test_mention_no_double_at() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "mention", "attrs": {"text": "@Bob"}},
                ],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "@Bob" in result
    assert "@@Bob" not in result


def test_inline_card_no_trailing_space() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "inlineCard", "attrs": {"url": "https://example.com"}},
                ],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "https://example.com" in result
    # URL should not have a trailing space injected before the paragraph newline
    assert "https://example.com " not in result.replace("\n", "")


def test_media_single_with_alt() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "mediaSingle",
                "content": [
                    {"type": "media", "attrs": {"alt": "screenshot.png"}},
                ],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "[screenshot.png]" in result


def test_expand_with_title() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "expand",
                "attrs": {"title": "Details"},
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": "Hidden content"}],
                    }
                ],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "Details" in result
    assert "Hidden content" in result


def test_strike_mark() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "deleted", "marks": [{"type": "strike"}]}],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "~~deleted~~" in result


def test_nested_bullet_list_indentation() -> None:
    adf: dict[str, Any] = {
        "type": "doc",
        "content": [
            {
                "type": "bulletList",
                "content": [
                    {
                        "type": "listItem",
                        "content": [
                            {
                                "type": "paragraph",
                                "content": [{"type": "text", "text": "Parent"}],
                            },
                            {
                                "type": "bulletList",
                                "content": [
                                    {
                                        "type": "listItem",
                                        "content": [
                                            {
                                                "type": "paragraph",
                                                "content": [{"type": "text", "text": "Child"}],
                                            }
                                        ],
                                    }
                                ],
                            },
                        ],
                    }
                ],
            }
        ],
    }
    result = extract_text(adf)
    assert result is not None
    assert "- Parent" in result
    assert "  - Child" in result  # two-space indent for depth=1


# ---------------------------------------------------------------------------
# Confluence-heavy node types and marks
# ---------------------------------------------------------------------------


def _doc(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {"type": "doc", "version": 1, "content": list(blocks)}


def _para(*inline: dict[str, Any]) -> dict[str, Any]:
    return {"type": "paragraph", "content": list(inline)}


def test_link_mark_renders_markdown_link() -> None:
    adf = _doc(
        _para(
            {
                "type": "text",
                "text": "the RFC",
                "marks": [{"type": "link", "attrs": {"href": "https://example.com/rfc"}}],
            }
        )
    )
    assert "[the RFC](https://example.com/rfc)" in (extract_text(adf) or "")


def test_link_mark_combined_with_strong() -> None:
    adf = _doc(
        _para(
            {
                "type": "text",
                "text": "docs",
                "marks": [
                    {"type": "strong"},
                    {"type": "link", "attrs": {"href": "https://x.io"}},
                ],
            }
        )
    )
    assert "[**docs**](https://x.io)" in (extract_text(adf) or "")


def test_link_mark_without_href_keeps_text() -> None:
    adf = _doc(_para({"type": "text", "text": "plain", "marks": [{"type": "link"}]}))
    assert extract_text(adf) == "plain"


def test_extension_macro_placeholder() -> None:
    adf = _doc(
        {
            "type": "extension",
            "attrs": {
                "extensionType": "com.atlassian.confluence.macro.core",
                "extensionKey": "toc",
            },
        }
    )
    assert "[macro: toc]" in (extract_text(adf) or "")


def test_inline_extension_macro_placeholder() -> None:
    adf = _doc(
        _para(
            {"type": "text", "text": "See "},
            {"type": "inlineExtension", "attrs": {"extensionKey": "jira"}},
        )
    )
    assert "See [macro: jira]" in (extract_text(adf) or "")


def test_bodied_extension_keeps_inner_content() -> None:
    adf = _doc(
        {
            "type": "bodiedExtension",
            "attrs": {"extensionKey": "details"},
            "content": [_para({"type": "text", "text": "Owner: team"})],
        }
    )
    assert "Owner: team" in (extract_text(adf) or "")


def test_status_lozenge() -> None:
    adf = _doc(_para({"type": "status", "attrs": {"text": "IN PROGRESS", "color": "blue"}}))
    assert "[IN PROGRESS]" in (extract_text(adf) or "")


def test_date_renders_iso_day() -> None:
    adf = _doc(_para({"type": "date", "attrs": {"timestamp": "1700000000000"}}))
    assert "2023-11-14" in (extract_text(adf) or "")


def test_date_with_bad_timestamp_is_skipped() -> None:
    adf = _doc(
        _para({"type": "text", "text": "x"}, {"type": "date", "attrs": {"timestamp": "nope"}})
    )
    assert extract_text(adf) == "x"


def test_emoji_uses_text_then_shortname() -> None:
    with_text = _doc(_para({"type": "emoji", "attrs": {"shortName": ":tada:", "text": "🎉"}}))
    short_only = _doc(_para({"type": "emoji", "attrs": {"shortName": ":tada:"}}))
    assert extract_text(with_text) == "🎉"
    assert extract_text(short_only) == ":tada:"


def test_task_list_checkboxes() -> None:
    adf = _doc(
        {
            "type": "taskList",
            "content": [
                {
                    "type": "taskItem",
                    "attrs": {"state": "DONE"},
                    "content": [{"type": "text", "text": "ship"}],
                },
                {
                    "type": "taskItem",
                    "attrs": {"state": "TODO"},
                    "content": [{"type": "text", "text": "test"}],
                },
            ],
        }
    )
    result = extract_text(adf) or ""
    assert "- [x] ship" in result
    assert "- [ ] test" in result


def test_decision_list() -> None:
    adf = _doc(
        {
            "type": "decisionList",
            "content": [
                {"type": "decisionItem", "content": [{"type": "text", "text": "Use OAuth"}]}
            ],
        }
    )
    assert "- Decision: Use OAuth" in (extract_text(adf) or "")


def test_nested_expand_like_expand() -> None:
    adf = _doc(
        {
            "type": "nestedExpand",
            "attrs": {"title": "Details"},
            "content": [_para({"type": "text", "text": "hidden"})],
        }
    )
    result = extract_text(adf) or ""
    assert "**Details**" in result
    assert "hidden" in result


def test_table_cell_newlines_are_flattened_so_rows_stay_on_one_line() -> None:
    adf = _doc(
        {
            "type": "table",
            "content": [
                {
                    "type": "tableRow",
                    "content": [
                        {"type": "tableHeader", "content": [_para({"type": "text", "text": "h"})]},
                    ],
                },
                {
                    "type": "tableRow",
                    "content": [
                        {
                            "type": "tableCell",
                            "content": [
                                _para({"type": "text", "text": "first"}),
                                {
                                    "type": "heading",
                                    "attrs": {"level": 2},
                                    "content": [{"type": "text", "text": "InCell"}],
                                },
                                _para({"type": "text", "text": "a|b"}),
                            ],
                        },
                    ],
                },
            ],
        }
    )
    result = extract_text(adf) or ""
    assert "| first<br>## InCell<br>a\\|b |" in result
    assert not any(line.startswith("#") for line in result.splitlines())


# ---------------------------------------------------------------------------
# Fence-like text must not look like a code fence (review 2)
# ---------------------------------------------------------------------------


def test_paragraph_starting_with_backtick_fence_is_escaped() -> None:
    result = extract_text(_doc(_para({"type": "text", "text": "``` opens a code block"}))) or ""
    assert result.startswith("\\``` opens a code block")


def test_strike_text_starting_with_tilde_is_escaped() -> None:
    strike = {"type": "text", "text": "~2d", "marks": [{"type": "strike"}]}
    assert (extract_text(_doc(_para(strike))) or "").startswith("\\~~~2d~~")


def test_inline_code_with_backticks_uses_longer_delimiter() -> None:
    def code(text: str) -> str:
        node = {"type": "text", "text": text, "marks": [{"type": "code"}]}
        return extract_text(_doc(_para(node))) or ""

    assert code("```") == "```` ``` ````"
    assert code("a`b") == "``a`b``"
    assert code("plain") == "`plain`"


def test_code_block_fence_is_longer_than_backtick_runs_inside() -> None:
    block = {
        "type": "codeBlock",
        "attrs": {"language": "markdown"},
        "content": [{"type": "text", "text": "Example:\n```\n# Not a heading"}],
    }
    result = extract_text(_doc(block)) or ""
    assert result.startswith("````markdown\n")
    assert result.rstrip().endswith("````")
