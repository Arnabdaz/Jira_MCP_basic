"""ADF (Atlassian Document Format) to readable markdown converter."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def extract_text(adf_data: Any) -> str | None:
    """Extract readable markdown text from ADF data, or return plain strings as-is."""
    if adf_data is None:
        return None
    if isinstance(adf_data, str):
        return adf_data
    if isinstance(adf_data, dict):
        if "content" in adf_data:
            result = _process_nodes(adf_data["content"]).strip()
            return result if result else None
        if "text" in adf_data:
            return str(adf_data["text"])
    return None


def _process_nodes(nodes: list[dict[str, Any]], depth: int = 0) -> str:
    return "".join(_process_node(n, depth) for n in nodes)


def _process_node(node: dict[str, Any], depth: int = 0) -> str:
    node_type = node.get("type", "")
    content: list[dict[str, Any]] = node.get("content", [])

    if node_type == "text":
        text: str = node.get("text", "")
        marks = {m["type"] for m in node.get("marks", [])}
        if "code" in marks:
            text = f"`{text}`"
        if "strong" in marks:
            text = f"**{text}**"
        if "em" in marks:
            text = f"*{text}*"
        if "strike" in marks:
            text = f"~~{text}~~"
        href = next(
            (
                m.get("attrs", {}).get("href")
                for m in node.get("marks", [])
                if m.get("type") == "link"
            ),
            None,
        )
        if href:
            text = f"[{text}]({href})"
        return text

    if node_type == "paragraph":
        return _process_nodes(content, depth) + "\n\n"

    if node_type == "heading":
        level: int = node.get("attrs", {}).get("level", 1)
        prefix = "#" * level
        return f"{prefix} {_process_nodes(content, depth).strip()}\n\n"

    if node_type == "hardBreak":
        return "\n"

    if node_type == "rule":
        return "---\n\n"

    if node_type == "bulletList":
        return _process_nodes(content, depth)

    if node_type == "orderedList":
        return _process_ordered_list(content, depth)

    if node_type == "listItem":
        lines = []
        for child in content:
            if child.get("type") in ("bulletList", "orderedList"):
                lines.append(_process_node(child, depth + 1))
            else:
                lines.append(_process_node(child, depth))
        inner = "".join(lines).strip()
        indent = "  " * depth
        return f"{indent}- {inner}\n"

    if node_type == "codeBlock":
        lang: str = node.get("attrs", {}).get("language", "")
        inner = _process_nodes(content)
        return f"```{lang}\n{inner}\n```\n\n"

    if node_type == "blockquote":
        inner = _process_nodes(content).strip()
        quoted = "\n".join(f"> {line}" for line in inner.splitlines())
        return f"{quoted}\n\n"

    if node_type == "panel":
        panel_type: str = node.get("attrs", {}).get("panelType", "info").upper()
        inner = _process_nodes(content).strip()
        quoted = "\n".join(f"> {line}" for line in inner.splitlines())
        return f"> [{panel_type}]\n{quoted}\n\n"

    if node_type == "table":
        return _process_table(content)

    if node_type in ("tableRow", "tableCell", "tableHeader"):
        return _process_nodes(content)

    if node_type == "mention":
        display: str = node.get("attrs", {}).get("text", "unknown")
        return display if display.startswith("@") else f"@{display}"

    if node_type in ("inlineCard", "blockCard"):
        url: str = node.get("attrs", {}).get("url", "")
        return url

    if node_type == "mediaSingle":
        return _process_nodes(content)

    if node_type == "media":
        alt: str = node.get("attrs", {}).get("alt", "attachment")
        return f"[{alt}]"

    if node_type in ("expand", "nestedExpand"):
        title: str = node.get("attrs", {}).get("title", "")
        inner = _process_nodes(content).strip()
        return f"**{title}**\n{inner}\n\n" if title else f"{inner}\n\n"

    # Confluence macros. Bodied macros (e.g. panels, details) keep their content;
    # body-less ones (toc, jira issue list, children...) would otherwise vanish silently.
    if node_type in ("extension", "inlineExtension", "bodiedExtension"):
        if content:
            return _process_nodes(content, depth)
        key: str = node.get("attrs", {}).get("extensionKey", "unknown")
        return f"[macro: {key}]" if node_type == "inlineExtension" else f"[macro: {key}]\n\n"

    if node_type == "status":
        return f"[{node.get('attrs', {}).get('text', '')}]"

    if node_type == "date":
        return _format_date(node.get("attrs", {}).get("timestamp"))

    if node_type == "emoji":
        attrs = node.get("attrs", {})
        return str(attrs.get("text") or attrs.get("shortName") or "")

    if node_type in ("taskList", "decisionList"):
        return _process_nodes(content, depth) + "\n"

    if node_type == "taskItem":
        box = "[x]" if node.get("attrs", {}).get("state") == "DONE" else "[ ]"
        return f"{'  ' * depth}- {box} {_process_nodes(content, depth).strip()}\n"

    if node_type == "decisionItem":
        return f"{'  ' * depth}- Decision: {_process_nodes(content, depth).strip()}\n"

    # Unknown node type — recurse into children if present
    if content:
        return _process_nodes(content)
    return ""


def _format_date(timestamp: Any) -> str:
    """ADF date nodes carry a UTC epoch-milliseconds string; render as YYYY-MM-DD."""
    try:
        return datetime.fromtimestamp(int(timestamp) / 1000, tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _process_ordered_list(items: list[dict[str, Any]], depth: int = 0) -> str:
    parts = []
    indent = "  " * depth
    for i, item in enumerate(items, 1):
        lines = []
        for child in item.get("content", []):
            if child.get("type") in ("bulletList", "orderedList"):
                lines.append(_process_node(child, depth + 1))
            else:
                lines.append(_process_node(child, depth))
        inner = "".join(lines).strip()
        parts.append(f"{indent}{i}. {inner}\n")
    return "".join(parts) + "\n"


def _process_table(rows: list[dict[str, Any]]) -> str:
    table_rows: list[list[str]] = []
    for row in rows:
        if row.get("type") != "tableRow":
            continue
        cells = [
            _process_nodes(cell.get("content", [])).strip()
            for cell in row.get("content", [])
            if cell.get("type") in ("tableCell", "tableHeader")
        ]
        table_rows.append(cells)

    if not table_rows:
        return ""

    max_cols = max(len(r) for r in table_rows)
    lines = []
    header = table_rows[0] + [""] * (max_cols - len(table_rows[0]))
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * max_cols) + " |")
    for data_row in table_rows[1:]:
        padded = data_row + [""] * (max_cols - len(data_row))
        lines.append("| " + " | ".join(padded) + " |")
    return "\n".join(lines) + "\n\n"
