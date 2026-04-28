"""Jira Cloud API client and data models."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import urljoin

import httpx
from pydantic import BaseModel, Field

from .adf import extract_text


class JiraConfig(BaseModel):
    """Configuration for Jira personal API access."""

    base_url: str = Field(description="Jira base URL (e.g., https://yourcompany.atlassian.net)")
    email: str = Field(description="Your Jira account email")
    api_token: str = Field(description="Your personal Jira API token")


class JiraLinkedIssue(BaseModel):
    """A linked issue relationship."""

    key: str
    summary: str
    url: str
    link_type: str  # e.g. "blocks", "is blocked by", "relates to"


class JiraAttachment(BaseModel):
    """A file attachment on an issue."""

    filename: str
    url: str
    size: int  # bytes
    created: str


class JiraSubTask(BaseModel):
    """A sub-task reference on a parent issue."""

    key: str
    summary: str
    status: str


class JiraIssue(BaseModel):
    """A Jira issue with all fields needed to understand and work a bug."""

    key: str
    id: str
    summary: str
    status: str
    assignee: str | None = None
    reporter: str | None = None
    priority: str | None = None
    issue_type: str
    created: str
    updated: str
    description: str | None = None
    project: str
    url: str
    labels: list[str] = []
    components: list[str] = []
    environment: str | None = None
    linked_issues: list[JiraLinkedIssue] = []
    attachments: list[JiraAttachment] = []
    sub_tasks: list[JiraSubTask] = []
    parent_key: str | None = None
    comment_count: int = 0


class JiraComment(BaseModel):
    """A comment on a Jira issue."""

    id: str
    author: str
    created: str
    updated: str
    body: str


class JiraProject(BaseModel):
    """A Jira project accessible to the authenticated user."""

    key: str
    id: str
    name: str
    project_type: str
    lead: str | None = None


class JiraApiError(Exception):
    """Raised when the Jira API returns an error response."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class JiraClient:
    """Async Jira Cloud REST API v3 client."""

    def __init__(self, config: JiraConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.auth = (config.email, config.api_token)
        self.session = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            auth=self.auth,
        )

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        await self.session.aclose()

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make an authenticated request to the Jira REST API v3."""
        url = urljoin(f"{self.base_url}/", f"rest/api/3/{endpoint}")
        try:
            response = await self.session.request(method, url, **kwargs)
            response.raise_for_status()
            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()  # type: ignore[no-any-return]
        except httpx.HTTPStatusError as e:
            error_msg = f"Jira API error: {e.response.status_code}"
            try:
                detail = e.response.json()
                if "errorMessages" in detail:
                    error_msg += f" - {'; '.join(detail['errorMessages'])}"
            except Exception:
                error_msg += f" - {e.response.text}"
            raise JiraApiError(error_msg, e.response.status_code) from e
        except httpx.RequestError as e:
            msg = f"Network error: {e!s}"
            raise JiraApiError(msg) from e
        else:
            return {"result": response.text}

    async def get_issue(self, issue_key: str) -> JiraIssue:
        """Fetch a single issue with all fields needed for bug understanding."""
        data = await self._request(
            "GET",
            f"issue/{issue_key}",
            params={
                "fields": (
                    "key,id,summary,status,assignee,reporter,priority,"
                    "issuetype,created,updated,description,project,"
                    "labels,components,environment,issuelinks,attachment,"
                    "subtasks,parent,comment"
                ),
                "expand": "renderedFields",
            },
        )
        return self._parse_issue(data)

    async def search_issues(
        self, jql: str, max_results: int = 20, start_at: int = 0
    ) -> tuple[list[JiraIssue], int]:
        """Search issues by JQL. Returns (issues, total_count)."""
        data = await self._request(
            "POST",
            "search",
            json={
                "jql": jql,
                "startAt": start_at,
                "maxResults": max_results,
                "fields": [
                    "key",
                    "id",
                    "summary",
                    "status",
                    "assignee",
                    "reporter",
                    "priority",
                    "issuetype",
                    "created",
                    "updated",
                    "description",
                    "project",
                ],
            },
        )
        total: int = data.get("total", 0)
        issues = [self._parse_issue(i) for i in data.get("issues", [])]
        return issues, total

    async def get_my_work(
        self,
        status_filter: str | None = None,
        max_results: int = 20,
        start_at: int = 0,
    ) -> tuple[list[JiraIssue], int]:
        """Return issues assigned to the current user, ordered by last updated."""
        jql = "assignee = currentUser()"
        if status_filter:
            safe_status = status_filter.replace("\\", "\\\\").replace("'", "\\'")
            jql += f" AND status = '{safe_status}'"
        jql += " ORDER BY updated DESC"
        return await self.search_issues(jql, max_results=max_results, start_at=start_at)

    async def get_issue_comments(
        self, issue_key: str, max_results: int = 20, start_at: int = 0
    ) -> tuple[list[JiraComment], int]:
        """Fetch comments for an issue in chronological order. Returns (comments, total_count)."""
        data = await self._request(
            "GET",
            f"issue/{issue_key}/comment",
            params={"startAt": start_at, "maxResults": max_results},
        )
        total: int = data.get("total", 0)
        comments = [self._parse_comment(c) for c in data.get("comments", [])]
        return comments, total

    async def get_projects(self) -> list[JiraProject]:
        """Return all Jira projects accessible to the authenticated user."""
        projects: list[JiraProject] = []
        start_at = 0
        page_size = 50
        while True:
            data = await self._request(
                "GET",
                "project/search",
                params={"maxResults": page_size, "startAt": start_at},
            )
            values = data.get("values", [])
            projects.extend(self._parse_project(p) for p in values)
            total: int = data.get("total", 0)
            start_at += len(values)
            if start_at >= total or not values:
                break
        return projects

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_issue(self, issue_data: dict[str, Any]) -> JiraIssue:
        fields = issue_data.get("fields", {})

        linked_issues: list[JiraLinkedIssue] = []
        for link in fields.get("issuelinks") or []:
            link_type_obj = link.get("type", {})
            if "outwardIssue" in link:
                raw = link["outwardIssue"]
                link_type = link_type_obj.get("outward", "relates to")
            elif "inwardIssue" in link:
                raw = link["inwardIssue"]
                link_type = link_type_obj.get("inward", "relates to")
            else:
                continue
            key = raw.get("key", "")
            linked_issues.append(
                JiraLinkedIssue(
                    key=key,
                    summary=raw.get("fields", {}).get("summary", ""),
                    url=f"{self.base_url}/browse/{key}",
                    link_type=link_type,
                )
            )

        attachments = [
            JiraAttachment(
                filename=att.get("filename", ""),
                url=att.get("content", ""),
                size=att.get("size", 0),
                created=att.get("created", ""),
            )
            for att in (fields.get("attachment") or [])
        ]

        sub_tasks = [
            JiraSubTask(
                key=st.get("key", ""),
                summary=st.get("fields", {}).get("summary", ""),
                status=st.get("fields", {}).get("status", {}).get("name", ""),
            )
            for st in (fields.get("subtasks") or [])
        ]

        comment_field = fields.get("comment")
        comment_count = comment_field.get("total", 0) if isinstance(comment_field, dict) else 0

        return JiraIssue(
            key=issue_data.get("key", ""),
            id=issue_data.get("id", ""),
            summary=fields.get("summary", ""),
            status=fields.get("status", {}).get("name", ""),
            assignee=self._get_user_display_name(fields.get("assignee")),
            reporter=self._get_user_display_name(fields.get("reporter")),
            priority=(fields.get("priority", {}).get("name") if fields.get("priority") else None),
            issue_type=fields.get("issuetype", {}).get("name", ""),
            created=fields.get("created", ""),
            updated=fields.get("updated", ""),
            description=extract_text(fields.get("description")),
            project=fields.get("project", {}).get("key", ""),
            url=f"{self.base_url}/browse/{issue_data.get('key', '')}",
            labels=fields.get("labels") or [],
            components=[c.get("name", "") for c in (fields.get("components") or [])],
            environment=extract_text(fields.get("environment")),
            linked_issues=linked_issues,
            attachments=attachments,
            sub_tasks=sub_tasks,
            parent_key=(fields["parent"].get("key") if fields.get("parent") else None),
            comment_count=comment_count,
        )

    def _parse_comment(self, comment_data: dict[str, Any]) -> JiraComment:
        return JiraComment(
            id=comment_data.get("id", ""),
            author=self._get_user_display_name(comment_data.get("author")) or "Unknown",
            created=comment_data.get("created", ""),
            updated=comment_data.get("updated", ""),
            body=extract_text(comment_data.get("body")) or "",
        )

    def _parse_project(self, project_data: dict[str, Any]) -> JiraProject:
        return JiraProject(
            key=project_data.get("key", ""),
            id=project_data.get("id", ""),
            name=project_data.get("name", ""),
            project_type=project_data.get("projectTypeKey", "unknown"),
            lead=(
                self._get_user_display_name(project_data["lead"])
                if project_data.get("lead")
                else None
            ),
        )

    def _get_user_display_name(self, user_data: dict[str, Any] | None) -> str | None:
        if not user_data:
            return None
        return user_data.get("displayName") or user_data.get("emailAddress")


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

_jira_client: JiraClient | None = None


def get_jira_client() -> JiraClient:
    """Return the module-level JiraClient singleton, creating it from env vars if needed."""
    global _jira_client  # noqa: PLW0603

    if _jira_client is None:
        base_url = os.getenv("JIRA_BASE_URL")
        email = os.getenv("JIRA_EMAIL")
        api_token = os.getenv("JIRA_API_TOKEN")

        if not all([base_url, email, api_token]):
            missing = [
                var
                for var, val in [
                    ("JIRA_BASE_URL", base_url),
                    ("JIRA_EMAIL", email),
                    ("JIRA_API_TOKEN", api_token),
                ]
                if not val
            ]
            msg = (
                f"Missing required environment variables: {', '.join(missing)}\n"
                "Please set JIRA_BASE_URL, JIRA_EMAIL, and JIRA_API_TOKEN."
            )
            raise ValueError(msg)

        _jira_client = JiraClient(
            JiraConfig(
                base_url=base_url,  # type: ignore[arg-type]
                email=email,  # type: ignore[arg-type]
                api_token=api_token,  # type: ignore[arg-type]
            )
        )

    return _jira_client
