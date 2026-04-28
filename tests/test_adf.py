"""Tests for the ADF (Atlassian Document Format) parser."""

from __future__ import annotations

from typing import Any

import pytest

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
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello world"}]}
        ],
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
                "content": [
                    {"type": "text", "text": "myFunc", "marks": [{"type": "code"}]}
                ],
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
