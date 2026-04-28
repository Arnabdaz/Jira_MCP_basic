"""Tests for JiraClient, data models, and parsing logic."""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from jira_mcp_server.client import (
    JiraApiError,
    JiraAttachment,
    JiraClient,
    JiraComment,
    JiraConfig,
    JiraIssue,
    JiraLinkedIssue,
    JiraProject,
    JiraSubTask,
    get_jira_client,
)


# ---------------------------------------------------------------------------
# TestJiraConfig
# ---------------------------------------------------------------------------


class TestJiraConfig:
    def test_valid_config(self) -> None:
        config = JiraConfig(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="token123",
        )
        assert config.base_url == "https://test.atlassian.net"
        assert config.email == "test@example.com"
        assert config.api_token == "token123"

    def test_missing_field_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            JiraConfig(base_url="https://test.atlassian.net", email="test@example.com")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# TestJiraClientInit
# ---------------------------------------------------------------------------


class TestJiraClientInit:
    def _make_client(self, base_url: str = "https://test.atlassian.net/") -> JiraClient:
        return JiraClient(JiraConfig(base_url=base_url, email="a@b.com", api_token="t"))

    def test_strips_trailing_slash(self) -> None:
        client = self._make_client("https://test.atlassian.net/")
        assert client.base_url == "https://test.atlassian.net"

    def test_get_user_display_name_none(self) -> None:
        client = self._make_client()
        assert client._get_user_display_name(None) is None

    def test_get_user_display_name_prefers_displayName(self) -> None:
        client = self._make_client()
        result = client._get_user_display_name(
            {"displayName": "Alice", "emailAddress": "alice@x.com"}
        )
        assert result == "Alice"

    def test_get_user_display_name_falls_back_to_email(self) -> None:
        client = self._make_client()
        result = client._get_user_display_name({"emailAddress": "alice@x.com"})
        assert result == "alice@x.com"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_issue_data(extra_fields: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a minimal valid Jira issue API response."""
    data: dict[str, Any] = {
        "key": "PROJ-1",
        "id": "10001",
        "fields": {
            "summary": "Test bug",
            "status": {"name": "Open"},
            "issuetype": {"name": "Bug"},
            "created": "2024-01-01T00:00:00.000+0000",
            "updated": "2024-01-02T00:00:00.000+0000",
            "project": {"key": "PROJ"},
            "assignee": {"displayName": "Alice"},
            "reporter": {"displayName": "Bob"},
            "priority": {"name": "High"},
            "description": None,
            "labels": [],
            "components": [],
            "issuelinks": [],
            "attachment": [],
            "subtasks": [],
            "parent": None,
            "comment": {"total": 0},
            "environment": None,
        },
    }
    if extra_fields:
        data["fields"].update(extra_fields)
    return data


# ---------------------------------------------------------------------------
# TestParseIssue
# ---------------------------------------------------------------------------


class TestParseIssue:
    def setup_method(self) -> None:
        self.client = JiraClient(
            JiraConfig(base_url="https://test.atlassian.net", email="a@b.com", api_token="t")
        )

    def test_basic_fields(self) -> None:
        issue = self.client._parse_issue(_minimal_issue_data())
        assert issue.key == "PROJ-1"
        assert issue.summary == "Test bug"
        assert issue.status == "Open"
        assert issue.issue_type == "Bug"
        assert issue.project == "PROJ"
        assert issue.url == "https://test.atlassian.net/browse/PROJ-1"
        assert issue.assignee == "Alice"
        assert issue.priority == "High"

    def test_labels(self) -> None:
        issue = self.client._parse_issue(_minimal_issue_data({"labels": ["regression", "p1"]}))
        assert issue.labels == ["regression", "p1"]

    def test_components(self) -> None:
        issue = self.client._parse_issue(
            _minimal_issue_data({"components": [{"name": "Frontend"}, {"name": "Auth"}]})
        )
        assert issue.components == ["Frontend", "Auth"]

    def test_linked_issues_outward(self) -> None:
        issue = self.client._parse_issue(
            _minimal_issue_data(
                {
                    "issuelinks": [
                        {
                            "type": {"outward": "blocks"},
                            "outwardIssue": {
                                "key": "PROJ-2",
                                "fields": {"summary": "Blocked issue"},
                            },
                        }
                    ]
                }
            )
        )
        assert len(issue.linked_issues) == 1
        assert issue.linked_issues[0].key == "PROJ-2"
        assert issue.linked_issues[0].link_type == "blocks"

    def test_linked_issues_inward(self) -> None:
        issue = self.client._parse_issue(
            _minimal_issue_data(
                {
                    "issuelinks": [
                        {
                            "type": {"inward": "is blocked by"},
                            "inwardIssue": {
                                "key": "PROJ-3",
                                "fields": {"summary": "Blocker"},
                            },
                        }
                    ]
                }
            )
        )
        assert len(issue.linked_issues) == 1
        assert issue.linked_issues[0].link_type == "is blocked by"

    def test_attachments(self) -> None:
        issue = self.client._parse_issue(
            _minimal_issue_data(
                {
                    "attachment": [
                        {
                            "filename": "screenshot.png",
                            "content": "https://test.atlassian.net/secure/1/screenshot.png",
                            "size": 204800,
                            "created": "2024-01-01T00:00:00.000+0000",
                        }
                    ]
                }
            )
        )
        assert len(issue.attachments) == 1
        assert issue.attachments[0].filename == "screenshot.png"
        assert issue.attachments[0].size == 204800

    def test_subtasks(self) -> None:
        issue = self.client._parse_issue(
            _minimal_issue_data(
                {
                    "subtasks": [
                        {
                            "key": "PROJ-10",
                            "fields": {"summary": "Sub task", "status": {"name": "To Do"}},
                        }
                    ]
                }
            )
        )
        assert len(issue.sub_tasks) == 1
        assert issue.sub_tasks[0].key == "PROJ-10"
        assert issue.sub_tasks[0].status == "To Do"

    def test_parent_key(self) -> None:
        issue = self.client._parse_issue(_minimal_issue_data({"parent": {"key": "PROJ-5"}}))
        assert issue.parent_key == "PROJ-5"

    def test_comment_count(self) -> None:
        issue = self.client._parse_issue(_minimal_issue_data({"comment": {"total": 7}}))
        assert issue.comment_count == 7

    def test_comment_count_zero_when_null(self) -> None:
        data = _minimal_issue_data()
        data["fields"]["comment"] = None
        issue = self.client._parse_issue(data)
        assert issue.comment_count == 0


# ---------------------------------------------------------------------------
# TestParseComment
# ---------------------------------------------------------------------------


class TestParseComment:
    def setup_method(self) -> None:
        self.client = JiraClient(
            JiraConfig(base_url="https://test.atlassian.net", email="a@b.com", api_token="t")
        )

    def test_plain_text_body(self) -> None:
        comment = self.client._parse_comment(
            {
                "id": "100",
                "author": {"displayName": "Alice"},
                "created": "2024-01-01T10:00:00.000+0000",
                "updated": "2024-01-01T10:00:00.000+0000",
                "body": "Plain text comment",
            }
        )
        assert comment.id == "100"
        assert comment.author == "Alice"
        assert comment.body == "Plain text comment"

    def test_adf_body(self) -> None:
        comment = self.client._parse_comment(
            {
                "id": "101",
                "author": {"displayName": "Bob"},
                "created": "2024-01-01T10:00:00.000+0000",
                "updated": "2024-01-01T10:00:00.000+0000",
                "body": {
                    "type": "doc",
                    "version": 1,
                    "content": [
                        {
                            "type": "paragraph",
                            "content": [{"type": "text", "text": "ADF comment"}],
                        }
                    ],
                },
            }
        )
        assert "ADF comment" in comment.body


# ---------------------------------------------------------------------------
# TestParseProject
# ---------------------------------------------------------------------------


class TestParseProject:
    def setup_method(self) -> None:
        self.client = JiraClient(
            JiraConfig(base_url="https://test.atlassian.net", email="a@b.com", api_token="t")
        )

    def test_basic_project(self) -> None:
        project = self.client._parse_project(
            {
                "key": "MYPROJ",
                "id": "10000",
                "name": "My Project",
                "projectTypeKey": "software",
                "lead": {"displayName": "Alice"},
            }
        )
        assert project.key == "MYPROJ"
        assert project.name == "My Project"
        assert project.project_type == "software"
        assert project.lead == "Alice"

    def test_project_without_lead(self) -> None:
        project = self.client._parse_project(
            {"key": "X", "id": "1", "name": "X", "projectTypeKey": "business"}
        )
        assert project.lead is None


# ---------------------------------------------------------------------------
# TestAsyncMethods
# ---------------------------------------------------------------------------


class TestAsyncMethods:
    def setup_method(self) -> None:
        self.client = JiraClient(
            JiraConfig(base_url="https://test.atlassian.net", email="a@b.com", api_token="t")
        )

    def _mock_response(self, json_data: dict[str, Any]) -> MagicMock:
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.headers = {"content-type": "application/json"}
        mock_resp.json.return_value = json_data
        return mock_resp

    async def test_search_issues_returns_tuple_with_total(self) -> None:
        self.client.session = AsyncMock()
        self.client.session.request = AsyncMock(
            return_value=self._mock_response(
                {
                    "total": 5,
                    "startAt": 0,
                    "maxResults": 20,
                    "issues": [
                        {
                            "key": "PROJ-1",
                            "id": "1",
                            "fields": _minimal_issue_data()["fields"],
                        }
                    ],
                }
            )
        )
        issues, total = await self.client.search_issues("project = PROJ")
        assert total == 5
        assert len(issues) == 1
        assert issues[0].key == "PROJ-1"

    async def test_search_issues_pagination_params_sent(self) -> None:
        self.client.session = AsyncMock()
        self.client.session.request = AsyncMock(
            return_value=self._mock_response(
                {"total": 0, "startAt": 20, "maxResults": 10, "issues": []}
            )
        )
        await self.client.search_issues("project = PROJ", max_results=10, start_at=20)
        call_kwargs = self.client.session.request.call_args
        body = call_kwargs.kwargs.get("json") or {}
        assert body["startAt"] == 20
        assert body["maxResults"] == 10

    async def test_get_issue_comments_returns_tuple_with_total(self) -> None:
        self.client.session = AsyncMock()
        self.client.session.request = AsyncMock(
            return_value=self._mock_response(
                {
                    "total": 3,
                    "startAt": 0,
                    "maxResults": 20,
                    "comments": [
                        {
                            "id": "1",
                            "author": {"displayName": "Alice"},
                            "created": "2024-01-01T10:00:00.000Z",
                            "updated": "2024-01-01T10:00:00.000Z",
                            "body": "First comment",
                        }
                    ],
                }
            )
        )
        comments, total = await self.client.get_issue_comments("PROJ-1")
        assert total == 3
        assert len(comments) == 1
        assert comments[0].author == "Alice"

    async def test_get_projects_returns_list(self) -> None:
        self.client.session = AsyncMock()
        self.client.session.request = AsyncMock(
            return_value=self._mock_response(
                {
                    "total": 1,
                    "startAt": 0,
                    "maxResults": 50,
                    "values": [
                        {
                            "key": "PROJ",
                            "id": "10000",
                            "name": "My Project",
                            "projectTypeKey": "software",
                            "lead": {"displayName": "Alice"},
                        }
                    ],
                }
            )
        )
        projects = await self.client.get_projects()
        assert len(projects) == 1
        assert projects[0].key == "PROJ"

    async def test_http_error_raises_jira_api_error(self) -> None:
        import httpx

        self.client.session = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {"errorMessages": ["Issue not found"]}
        mock_resp.text = "Not Found"
        self.client.session.request = AsyncMock(
            side_effect=httpx.HTTPStatusError(
                "404", request=MagicMock(), response=mock_resp
            )
        )
        with pytest.raises(JiraApiError) as exc_info:
            await self.client.get_issue("PROJ-999")
        assert "404" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestEnvironmentVariables
# ---------------------------------------------------------------------------


class TestEnvironmentVariables:
    def test_get_jira_client_with_env_vars(self) -> None:
        import jira_mcp_server.client as client_module

        with patch.dict(
            os.environ,
            {
                "JIRA_BASE_URL": "https://test.atlassian.net",
                "JIRA_EMAIL": "test@example.com",
                "JIRA_API_TOKEN": "token123",
            },
        ):
            client_module._jira_client = None
            client = client_module.get_jira_client()
            assert client is not None
            client_module._jira_client = None

    def test_get_jira_client_missing_env_vars(self) -> None:
        import jira_mcp_server.client as client_module

        with patch.dict(os.environ, {}, clear=True):
            client_module._jira_client = None
            with pytest.raises(ValueError, match="Missing required environment variables"):
                client_module.get_jira_client()
            client_module._jira_client = None
