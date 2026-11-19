"""Tests for MCP tool functions."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from jira_mcp_server.client import (
    JiraAttachment,
    JiraComment,
    JiraIssue,
    JiraLinkedIssue,
    JiraProject,
    JiraSearchPage,
    JiraSubTask,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_issue(
    key: str = "PROJ-1",
    comment_count: int = 0,
    **kwargs: object,
) -> JiraIssue:
    defaults: dict[str, object] = {
        "key": key,
        "id": "10001",
        "summary": "Test bug",
        "status": "Open",
        "issue_type": "Bug",
        "created": "2024-01-01T00:00:00.000Z",
        "updated": "2024-01-02T00:00:00.000Z",
        "project": "PROJ",
        "url": f"https://test.atlassian.net/browse/{key}",
        "comment_count": comment_count,
        "labels": [],
        "components": [],
        "linked_issues": [],
        "attachments": [],
        "sub_tasks": [],
    }
    defaults.update(kwargs)
    return JiraIssue(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TestReadJiraIssue
# ---------------------------------------------------------------------------


class TestReadJiraIssue:
    async def test_success_contains_key_and_summary(self) -> None:
        from jira_mcp_server.tools import read_jira_issue

        mock_client = MagicMock()
        mock_client.get_issue = AsyncMock(return_value=make_issue())
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await read_jira_issue("PROJ-1")
        assert "result" in result
        assert "PROJ-1" in result["result"]
        assert "Test bug" in result["result"]

    async def test_labels_shown(self) -> None:
        from jira_mcp_server.tools import read_jira_issue

        mock_client = MagicMock()
        mock_client.get_issue = AsyncMock(
            return_value=make_issue(labels=["regression", "p1"])
        )
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await read_jira_issue("PROJ-1")
        assert "regression" in result["result"]
        assert "p1" in result["result"]

    async def test_comment_count_hint_shown(self) -> None:
        from jira_mcp_server.tools import read_jira_issue

        mock_client = MagicMock()
        mock_client.get_issue = AsyncMock(return_value=make_issue(comment_count=5))
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await read_jira_issue("PROJ-1")
        assert "5 comment" in result["result"]
        assert "get_issue_comments" in result["result"]

    async def test_no_comment_hint_when_zero(self) -> None:
        from jira_mcp_server.tools import read_jira_issue

        mock_client = MagicMock()
        mock_client.get_issue = AsyncMock(return_value=make_issue(comment_count=0))
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await read_jira_issue("PROJ-1")
        assert "get_issue_comments" not in result["result"]

    async def test_linked_issues_shown(self) -> None:
        from jira_mcp_server.tools import read_jira_issue

        linked = [
            JiraLinkedIssue(
                key="PROJ-2",
                summary="Blocker",
                url="https://test.atlassian.net/browse/PROJ-2",
                link_type="blocks",
            )
        ]
        mock_client = MagicMock()
        mock_client.get_issue = AsyncMock(return_value=make_issue(linked_issues=linked))
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await read_jira_issue("PROJ-1")
        assert "PROJ-2" in result["result"]
        assert "blocks" in result["result"]

    async def test_attachments_shown(self) -> None:
        from jira_mcp_server.tools import read_jira_issue

        attachments = [
            JiraAttachment(
                filename="error.log",
                url="https://test.atlassian.net/attach/1/error.log",
                size=1024,
                created="2024-01-01",
            )
        ]
        mock_client = MagicMock()
        mock_client.get_issue = AsyncMock(return_value=make_issue(attachments=attachments))
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await read_jira_issue("PROJ-1")
        assert "error.log" in result["result"]
        assert "1 KB" in result["result"]

    async def test_attachment_small_shown_in_bytes(self) -> None:
        from jira_mcp_server.tools import read_jira_issue

        attachments = [
            JiraAttachment(
                filename="small.txt",
                url="https://test.atlassian.net/attach/2/small.txt",
                size=512,
                created="2024-01-01",
            )
        ]
        mock_client = MagicMock()
        mock_client.get_issue = AsyncMock(return_value=make_issue(attachments=attachments))
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await read_jira_issue("PROJ-1")
        assert "512 B" in result["result"]

    async def test_subtasks_shown(self) -> None:
        from jira_mcp_server.tools import read_jira_issue

        sub_tasks = [JiraSubTask(key="PROJ-10", summary="Fix it", status="To Do")]
        mock_client = MagicMock()
        mock_client.get_issue = AsyncMock(return_value=make_issue(sub_tasks=sub_tasks))
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await read_jira_issue("PROJ-1")
        assert "PROJ-10" in result["result"]

    async def test_parent_key_shown(self) -> None:
        from jira_mcp_server.tools import read_jira_issue

        mock_client = MagicMock()
        mock_client.get_issue = AsyncMock(return_value=make_issue(parent_key="PROJ-5"))
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await read_jira_issue("PROJ-1")
        assert "PROJ-5" in result["result"]

    async def test_error_returns_error_key(self) -> None:
        from jira_mcp_server.tools import read_jira_issue

        with patch(
            "jira_mcp_server.tools.get_jira_client",
            side_effect=ValueError("Missing env"),
        ):
            result = await read_jira_issue("PROJ-1")
        assert "error" in result


# ---------------------------------------------------------------------------
# TestSearchJiraIssues
# ---------------------------------------------------------------------------


class TestSearchJiraIssues:
    async def test_success_with_pagination_footer(self) -> None:
        from jira_mcp_server.tools import search_jira_issues

        issues = [make_issue(key=f"PROJ-{i}") for i in range(1, 21)]
        mock_client = MagicMock()
        mock_client.search_issues = AsyncMock(
            return_value=JiraSearchPage(issues=issues, next_page_token="tok-2", total=50)
        )
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await search_jira_issues("project = PROJ")
        assert "result" in result
        assert 'page_token="tok-2"' in result["result"]
        assert "50" in result["result"]

    async def test_page_token_forwarded_to_client(self) -> None:
        from jira_mcp_server.tools import search_jira_issues

        mock_client = MagicMock()
        mock_client.search_issues = AsyncMock(
            return_value=JiraSearchPage(issues=[make_issue()], next_page_token=None)
        )
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            await search_jira_issues("project = PROJ", max_results=5, page_token="tok-2")
        mock_client.search_issues.assert_awaited_once_with("project = PROJ", 5, "tok-2")

    async def test_empty_results(self) -> None:
        from jira_mcp_server.tools import search_jira_issues

        mock_client = MagicMock()
        mock_client.search_issues = AsyncMock(return_value=JiraSearchPage(issues=[], total=0))
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await search_jira_issues("project = NONE")
        assert "No issues found" in result["result"]

    async def test_no_pagination_footer_when_all_shown(self) -> None:
        from jira_mcp_server.tools import search_jira_issues

        mock_client = MagicMock()
        mock_client.search_issues = AsyncMock(
            return_value=JiraSearchPage(issues=[make_issue()], total=1)
        )
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await search_jira_issues("project = PROJ")
        assert "page_token=" not in result["result"]

    async def test_unknown_total_still_renders(self) -> None:
        from jira_mcp_server.tools import search_jira_issues

        mock_client = MagicMock()
        mock_client.search_issues = AsyncMock(
            return_value=JiraSearchPage(issues=[make_issue()], next_page_token="t", total=None)
        )
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await search_jira_issues("project = PROJ")
        assert "PROJ-1" in result["result"]
        assert "None" not in result["result"]

    async def test_error_returns_error_key(self) -> None:
        from jira_mcp_server.tools import search_jira_issues

        with patch(
            "jira_mcp_server.tools.get_jira_client",
            side_effect=ValueError("Missing env"),
        ):
            result = await search_jira_issues("project = PROJ")
        assert "error" in result


# ---------------------------------------------------------------------------
# TestGetMyWork
# ---------------------------------------------------------------------------


class TestGetMyWork:
    async def test_success(self) -> None:
        from jira_mcp_server.tools import get_my_work

        mock_client = MagicMock()
        mock_client.get_my_work = AsyncMock(
            return_value=JiraSearchPage(issues=[make_issue()], total=1)
        )
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await get_my_work()
        assert "PROJ-1" in result["result"]

    async def test_empty_returns_message(self) -> None:
        from jira_mcp_server.tools import get_my_work

        mock_client = MagicMock()
        mock_client.get_my_work = AsyncMock(return_value=JiraSearchPage(issues=[], total=0))
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await get_my_work()
        assert "No assigned issues" in result["result"]

    async def test_pagination_footer(self) -> None:
        from jira_mcp_server.tools import get_my_work

        issues = [make_issue(key=f"PROJ-{i}") for i in range(20)]
        mock_client = MagicMock()
        mock_client.get_my_work = AsyncMock(
            return_value=JiraSearchPage(issues=issues, next_page_token="tok-2", total=45)
        )
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await get_my_work()
        assert 'page_token="tok-2"' in result["result"]

    async def test_page_token_forwarded_to_client(self) -> None:
        from jira_mcp_server.tools import get_my_work

        mock_client = MagicMock()
        mock_client.get_my_work = AsyncMock(return_value=JiraSearchPage(issues=[make_issue()]))
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            await get_my_work(status_filter="Open", max_results=7, page_token="tok-2")
        mock_client.get_my_work.assert_awaited_once_with("Open", 7, "tok-2")

    async def test_status_filter_shown_in_output(self) -> None:
        from jira_mcp_server.tools import get_my_work

        mock_client = MagicMock()
        mock_client.get_my_work = AsyncMock(
            return_value=JiraSearchPage(issues=[make_issue()], total=1)
        )
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await get_my_work(status_filter="In Progress")
        assert "In Progress" in result["result"]

    async def test_empty_with_status_filter_shows_filter_in_message(self) -> None:
        from jira_mcp_server.tools import get_my_work

        mock_client = MagicMock()
        mock_client.get_my_work = AsyncMock(return_value=JiraSearchPage(issues=[], total=0))
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await get_my_work(status_filter="Done")
        assert "Done" in result["result"]


# ---------------------------------------------------------------------------
# TestGetIssueComments
# ---------------------------------------------------------------------------


class TestGetIssueComments:
    async def test_success(self) -> None:
        from jira_mcp_server.tools import get_issue_comments

        comments = [
            JiraComment(
                id="1",
                author="Alice",
                created="2024-01-01",
                updated="2024-01-01",
                body="First comment",
            ),
            JiraComment(
                id="2",
                author="Bob",
                created="2024-01-02",
                updated="2024-01-02",
                body="Second comment",
            ),
        ]
        mock_client = MagicMock()
        mock_client.get_issue_comments = AsyncMock(return_value=(comments, 2))
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await get_issue_comments("PROJ-1")
        assert "Alice" in result["result"]
        assert "First comment" in result["result"]
        assert "Bob" in result["result"]

    async def test_empty_comments(self) -> None:
        from jira_mcp_server.tools import get_issue_comments

        mock_client = MagicMock()
        mock_client.get_issue_comments = AsyncMock(return_value=([], 0))
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await get_issue_comments("PROJ-1")
        assert "No comments" in result["result"]

    async def test_pagination_footer(self) -> None:
        from jira_mcp_server.tools import get_issue_comments

        comments = [
            JiraComment(
                id=str(i),
                author="Alice",
                created="2024-01-01",
                updated="2024-01-01",
                body=f"Comment {i}",
            )
            for i in range(20)
        ]
        mock_client = MagicMock()
        mock_client.get_issue_comments = AsyncMock(return_value=(comments, 35))
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await get_issue_comments("PROJ-1")
        assert "start_at=20" in result["result"]


# ---------------------------------------------------------------------------
# TestGetProjects
# ---------------------------------------------------------------------------


class TestGetProjects:
    async def test_success(self) -> None:
        from jira_mcp_server.tools import get_projects

        projects = [
            JiraProject(
                key="MYPROJ",
                id="1",
                name="My Project",
                project_type="software",
                lead="Alice",
            )
        ]
        mock_client = MagicMock()
        mock_client.get_projects = AsyncMock(return_value=projects)
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await get_projects()
        assert "MYPROJ" in result["result"]
        assert "My Project" in result["result"]

    async def test_empty_projects(self) -> None:
        from jira_mcp_server.tools import get_projects

        mock_client = MagicMock()
        mock_client.get_projects = AsyncMock(return_value=[])
        with patch("jira_mcp_server.tools.get_jira_client", return_value=mock_client):
            result = await get_projects()
        assert "No accessible" in result["result"]


# ---------------------------------------------------------------------------
# TestMissingEnvVars — all tools return {"error": ...} when config is absent
# ---------------------------------------------------------------------------


class TestMissingEnvVars:
    async def test_all_tools_return_error_dict(self) -> None:
        from jira_mcp_server.tools import (
            get_issue_comments,
            get_my_work,
            get_projects,
            read_jira_issue,
            search_jira_issues,
        )

        with patch(
            "jira_mcp_server.tools.get_jira_client",
            side_effect=ValueError("Missing env vars"),
        ):
            results = [
                await read_jira_issue("PROJ-1"),
                await search_jira_issues("project = PROJ"),
                await get_my_work(),
                await get_issue_comments("PROJ-1"),
                await get_projects(),
            ]

        for r in results:
            assert "error" in r, f"Expected 'error' key in {r}"
