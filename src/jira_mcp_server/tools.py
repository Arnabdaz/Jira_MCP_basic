"""MCP tool definitions for Jira read operations."""

from __future__ import annotations

from typing import Any

from mcp.types import ToolAnnotations

from .app import mcp
from .client import get_jira_client

_READ_ONLY = ToolAnnotations(readOnlyHint=True)
_BYTES_PER_KB = 1024


@mcp.tool(annotations=_READ_ONLY)
async def read_jira_issue(issue_key: str) -> dict[str, Any]:
    """
    Fetch a Jira issue in full detail for bug understanding and resolution.

    Returns: summary, status, type, priority, assignee, reporter, description,
    labels, components, environment, linked issues (blocks/blocked by/relates to),
    attachment list, sub-tasks, parent issue key, and comment count.

    Call get_issue_comments() separately to read the actual comment text.
    """
    try:
        client = get_jira_client()
        issue = await client.get_issue(issue_key)

        lines: list[str] = [
            f"# {issue.key}: {issue.summary}",
            "",
            f"**Link:** {issue.url}",
            f"**Status:** {issue.status}  |  **Type:** {issue.issue_type}  |  **Priority:** {issue.priority or 'Not set'}",
            f"**Project:** {issue.project}",
            f"**Assignee:** {issue.assignee or 'Unassigned'}  |  **Reporter:** {issue.reporter or 'Unknown'}",
            f"**Created:** {issue.created}  |  **Updated:** {issue.updated}",
        ]

        if issue.labels:
            lines.append(f"**Labels:** {', '.join(issue.labels)}")
        if issue.components:
            lines.append(f"**Components:** {', '.join(issue.components)}")
        if issue.parent_key:
            lines.append(f"**Parent:** {issue.parent_key}")

        lines += ["", "## Description", issue.description or "*No description provided*"]

        if issue.environment:
            lines += ["", "## Environment", issue.environment]

        if issue.linked_issues:
            lines += ["", "## Linked Issues"]
            for li in issue.linked_issues:
                lines.append(f"- **{li.link_type}** [{li.key}]({li.url}): {li.summary}")

        if issue.attachments:
            lines += ["", "## Attachments"]
            for att in issue.attachments:
                size_str = f"{att.size} B" if att.size < _BYTES_PER_KB else f"{att.size // _BYTES_PER_KB} KB"
                lines.append(f"- [{att.filename}]({att.url}) ({size_str})")

        if issue.sub_tasks:
            lines += ["", "## Sub-tasks"]
            for st in issue.sub_tasks:
                lines.append(f"- {st.key}: {st.summary} [{st.status}]")

        if issue.comment_count > 0:
            lines += [
                "",
                f'*{issue.comment_count} comment(s) — call `get_issue_comments("{issue_key}")` to read them.*',
            ]

        return {"result": "\n".join(lines)}
    except Exception as e:
        return {"error": f"Error reading issue: {e!s}"}


@mcp.tool(annotations=_READ_ONLY)
async def search_jira_issues(
    jql: str, max_results: int = 20, start_at: int = 0
) -> dict[str, Any]:
    """
    Search Jira issues using JQL (Jira Query Language).

    Examples:
      - project = MYPROJ AND status = "In Progress"
      - assignee = currentUser() AND priority = High
      - text ~ "login error" AND created >= -7d

    Results are paginated. The response includes total count and a hint to call
    again with a higher start_at when more results are available.

    Args:
        jql: Any valid JQL query string.
        max_results: Number of results per page (1-100, default 20).
        start_at: Zero-based offset for pagination (default 0).
    """
    try:
        validated_max = max(1, min(max_results, 100))
        client = get_jira_client()
        issues, total = await client.search_issues(jql, validated_max, start_at)

        if not issues:
            return {"result": "No issues found matching the search criteria."}

        end = start_at + len(issues)
        lines: list[str] = [
            "# Search Results",
            f"**JQL:** `{jql}`",
            f"Showing {start_at + 1}-{end} of {total}",
            "",
        ]
        for issue in issues:
            lines += [
                f"## {issue.key}: {issue.summary}",
                f"**Link:** {issue.url}",
                f"**Status:** {issue.status}  |  **Type:** {issue.issue_type}  |  **Priority:** {issue.priority or 'Not set'}",
                f"**Project:** {issue.project}  |  **Assignee:** {issue.assignee or 'Unassigned'}",
                f"**Updated:** {issue.updated}",
                "",
            ]
        if end < total:
            lines.append(
                f"*More results available. Call again with `start_at={end}` to get the next page.*"
            )
        return {"result": "\n".join(lines)}
    except Exception as e:
        return {"error": f"Error searching issues: {e!s}"}


@mcp.tool(annotations=_READ_ONLY)
async def get_my_work(
    status_filter: str | None = None, max_results: int = 20, start_at: int = 0
) -> dict[str, Any]:
    """
    Get Jira issues assigned to the currently authenticated user.

    Optionally filter by status (e.g., "In Progress", "Open", "To Do").
    Results are ordered by most recently updated and support pagination.

    Args:
        status_filter: Jira status name to filter by (optional).
        max_results: Number of results per page (1-100, default 20).
        start_at: Zero-based offset for pagination (default 0).
    """
    try:
        validated_max = max(1, min(max_results, 100))
        client = get_jira_client()
        issues, total = await client.get_my_work(status_filter, validated_max, start_at)

        if not issues:
            suffix = f" with status '{status_filter}'" if status_filter else ""
            return {"result": f"No assigned issues found{suffix}."}

        end = start_at + len(issues)
        lines: list[str] = ["# My Work", f"Showing {start_at + 1}-{end} of {total}"]
        if status_filter:
            lines.append(f"**Status Filter:** {status_filter}")
        lines.append("")

        for issue in issues:
            lines += [
                f"## {issue.key}: {issue.summary}",
                f"**Link:** {issue.url}",
                f"**Status:** {issue.status}  |  **Type:** {issue.issue_type}  |  **Priority:** {issue.priority or 'Not set'}",
                f"**Project:** {issue.project}  |  **Updated:** {issue.updated}",
                "",
            ]

        if end < total:
            lines.append(
                f"*More results available. Call again with `start_at={end}` to get the next page.*"
            )
        return {"result": "\n".join(lines)}
    except Exception as e:
        return {"error": f"Error getting work: {e!s}"}


@mcp.tool(annotations=_READ_ONLY)
async def get_issue_comments(
    issue_key: str, max_results: int = 20, start_at: int = 0
) -> dict[str, Any]:
    """
    Get comments for a Jira issue in chronological order (oldest first).

    Returns author, timestamp, and full comment text for each comment.
    Supports pagination for issues with many comments.

    Args:
        issue_key: The issue key (e.g., PROJ-123).
        max_results: Number of comments per page (1-100, default 20).
        start_at: Zero-based offset for pagination (default 0).
    """
    try:
        validated_max = max(1, min(max_results, 100))
        client = get_jira_client()
        comments, total = await client.get_issue_comments(issue_key, validated_max, start_at)

        if not comments:
            return {"result": f"No comments found on {issue_key}."}

        end = start_at + len(comments)
        lines: list[str] = [
            f"# Comments on {issue_key}",
            f"Showing {start_at + 1}-{end} of {total}",
            "",
        ]
        for comment in comments:
            lines += [
                f"### {comment.author} — {comment.created}",
                comment.body or "*[empty comment]*",
                "",
            ]

        if end < total:
            lines.append(
                f"*More comments available. Call again with `start_at={end}` to get the next page.*"
            )
        return {"result": "\n".join(lines)}
    except Exception as e:
        return {"error": f"Error getting comments: {e!s}"}


@mcp.tool(annotations=_READ_ONLY)
async def get_projects() -> dict[str, Any]:
    """
    List all Jira projects accessible to the authenticated user.

    Returns project key, name, type (software/service_desk/business), and lead.
    Useful for discovering project keys before writing JQL queries.
    """
    try:
        client = get_jira_client()
        projects = await client.get_projects()

        if not projects:
            return {"result": "No accessible Jira projects found."}

        lines: list[str] = [f"# Jira Projects ({len(projects)} total)", ""]
        for project in projects:
            lead_str = f"  |  **Lead:** {project.lead}" if project.lead else ""
            lines.append(
                f"- **{project.key}** — {project.name} ({project.project_type}){lead_str}"
            )
        return {"result": "\n".join(lines)}
    except Exception as e:
        return {"error": f"Error getting projects: {e!s}"}
