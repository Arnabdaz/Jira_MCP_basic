"""
Jira MCP Server - A Model Context Protocol server for Jira Cloud integration.

This server provides tools to interact with Jira Cloud using personal API tokens.
It supports reading issues, searching, commenting, and managing personal work.
"""

import logging
import os
from typing import Any
from urllib.parse import urljoin

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP server
mcp = FastMCP("jira-mcp")


class JiraConfig(BaseModel):
    """Configuration for Jira personal API access"""

    base_url: str = Field(description="Jira base URL (e.g., https://cloudera.atlassian.net)")
    email: str = Field(description="Your Jira account email")
    api_token: str = Field(description="Your personal Jira API token")


class JiraIssue(BaseModel):
    """Jira issue representation"""

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


class JiraApiError(Exception):
    """Jira API specific error"""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class JiraClient:
    """Jira Cloud API client optimized for personal use"""

    def __init__(self, config: JiraConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.auth = (config.email, config.api_token)
        self.session = httpx.AsyncClient(
            timeout=httpx.Timeout(30.0),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            auth=self.auth,
        )

    async def close(self) -> None:
        """Clean up the HTTP client"""
        await self.session.aclose()

    async def _request(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        """Make authenticated request to Jira API"""
        url = urljoin(f"{self.base_url}/", f"rest/api/3/{endpoint}")

        try:
            response = await self.session.request(method, url, **kwargs)
            response.raise_for_status()

            if response.headers.get("content-type", "").startswith("application/json"):
                return response.json()
            return {"result": response.text}

        except httpx.HTTPStatusError as e:
            error_msg = f"Jira API error: {e.response.status_code}"
            try:
                error_detail = e.response.json()
                if "errorMessages" in error_detail:
                    error_msg += f" - {'; '.join(error_detail['errorMessages'])}"
            except Exception:
                error_msg += f" - {e.response.text}"

            raise JiraApiError(error_msg, e.response.status_code) from e

        except httpx.RequestError as e:
            msg = f"Network error: {e!s}"
            raise JiraApiError(msg) from e

    async def get_issue(self, issue_key: str) -> JiraIssue:
        """Retrieve a specific Jira issue"""
        endpoint = f"issue/{issue_key}"
        params = {
            "fields": (
                "key,id,summary,status,assignee,reporter,priority,"
                "issuetype,created,updated,description,project"
            ),
            "expand": "renderedFields",
        }

        data = await self._request("GET", endpoint, params=params)
        return self._parse_issue(data)

    async def search_issues(self, jql: str, max_results: int = 50) -> list[JiraIssue]:
        """Search issues using JQL"""
        endpoint = "search"
        payload = {
            "jql": jql,
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
            "expand": ["renderedFields"],
        }

        data = await self._request("POST", endpoint, json=payload)
        return [self._parse_issue(issue) for issue in data.get("issues", [])]

    async def get_my_work(self, status_filter: str | None = None) -> list[JiraIssue]:
        """Get your assigned issues"""
        jql = "assignee = currentUser()"

        if status_filter:
            jql += f" AND status = '{status_filter}'"

        jql += " ORDER BY updated DESC"

        return await self.search_issues(jql)

    async def add_comment(self, issue_key: str, comment_text: str) -> dict[str, Any]:
        """Add comment to an issue"""
        endpoint = f"issue/{issue_key}/comment"

        # Use the Atlassian Document Format (ADF)
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": comment_text}],
                    }
                ],
            }
        }

        return await self._request("POST", endpoint, json=payload)

    def _parse_issue(self, issue_data: dict[str, Any]) -> JiraIssue:
        """Parse Jira issue data into structured format"""
        fields = issue_data.get("fields", {})

        # Extract description from various formats
        description = None
        if fields.get("description"):
            description = self._extract_description(fields["description"])

        # Build issue URL
        issue_url = f"{self.base_url}/browse/{issue_data.get('key', '')}"

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
            description=description,
            project=fields.get("project", {}).get("key", ""),
            url=issue_url,
        )

    def _get_user_display_name(self, user_data: dict[str, Any] | None) -> str | None:
        """Extract user display name from user object"""
        if not user_data:
            return None
        return user_data.get("displayName") or user_data.get("emailAddress")

    def _extract_description(self, description_data: Any) -> str | None:
        """Extract text from ADF (Atlassian Document Format)"""
        if not description_data:
            return None

        if isinstance(description_data, str):
            return description_data

        if isinstance(description_data, dict):
            # Handle ADF format
            if "content" in description_data:
                return self._extract_adf_text(description_data["content"])
            # Handle simple text
            if "text" in description_data:
                return description_data["text"]

        return str(description_data)

    def _extract_adf_text(self, content: list[dict[str, Any]]) -> str:
        """Extract text from ADF content blocks"""
        text_parts = []

        for block in content:
            if block.get("type") == "paragraph":
                paragraph_content = block.get("content", [])
                for item in paragraph_content:
                    if item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
            elif block.get("type") == "text":
                text_parts.append(block.get("text", ""))

        return " ".join(text_parts).strip()


# Global client
_jira_client: JiraClient | None = None


def get_jira_client() -> JiraClient:
    """Get or create Jira client instance"""
    global _jira_client

    if _jira_client is None:
        # Load configuration from environment
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
                "Please set these environment variables for personal API access."
            )
            raise ValueError(msg)

        config = JiraConfig(base_url=base_url, email=email, api_token=api_token)
        _jira_client = JiraClient(config)

    return _jira_client


@mcp.tool()
async def read_jira_issue(issue_key: str) -> dict[str, Any]:
    """Read a specific Jira issue by key (e.g., PROJ-123)"""
    try:
        client = get_jira_client()
        issue = await client.get_issue(issue_key)

        result = f"""# 🎫 {issue.key}: {issue.summary}

**🔗 Link:** {issue.url}
**📊 Status:** {issue.status}
**🏷️ Type:** {issue.issue_type}
**📁 Project:** {issue.project}
**⚡ Priority:** {issue.priority or 'Not set'}
**👤 Assignee:** {issue.assignee or 'Unassigned'}
**📝 Reporter:** {issue.reporter or 'Unknown'}
**📅 Created:** {issue.created}
**🔄 Updated:** {issue.updated}

## 📄 Description
{issue.description or '*No description provided*'}
"""
        return {"result": result}
    except Exception as e:
        return {"error": f"❌ Error reading issue: {e!s}"}


@mcp.tool()
async def search_jira_issues(jql: str, max_results: int = 50) -> dict[str, Any]:
    """Search for Jira issues using JQL (Jira Query Language)"""
    try:
        # Validate max_results
        validated_max_results = max_results
        MAX_RESULTS_LIMIT = 100
        if validated_max_results < 1 or validated_max_results > MAX_RESULTS_LIMIT:
            validated_max_results = 50

        client = get_jira_client()
        issues = await client.search_issues(jql, validated_max_results)

        if not issues:
            return {"result": "🔍 No issues found matching the search criteria"}

        result = f"# 🔍 Search Results ({len(issues)} issues)\n\n"
        result += f"**JQL:** `{jql}`\n\n"

        for issue in issues:
            result += f"## 🎫 {issue.key}: {issue.summary}\n"
            result += f"**🔗 Link:** {issue.url}\n"
            result += f"**📊 Status:** {issue.status} | **🏷️ Type:** {issue.issue_type}\n"
            result += (
                f"**📁 Project:** {issue.project} | "
                f"**⚡ Priority:** {issue.priority or 'Not set'}\n"
            )
            result += f"**👤 Assignee:** {issue.assignee or 'Unassigned'}\n"
            result += f"**🔄 Updated:** {issue.updated}\n\n"

        return {"result": result}
    except Exception as e:
        return {"error": f"❌ Error searching issues: {e!s}"}


@mcp.tool()
async def get_my_work(status_filter: str | None = None) -> dict[str, Any]:
    """Get issues assigned to you (personal work queue)"""
    try:
        client = get_jira_client()
        issues = await client.get_my_work(status_filter)

        if not issues:
            status_msg = f" with status '{status_filter}'" if status_filter else ""
            return {"result": f"🎉 No assigned issues found{status_msg}"}

        result = f"# 👤 My Work ({len(issues)} issues)\n\n"
        if status_filter:
            result += f"**Status Filter:** {status_filter}\n\n"

        for issue in issues:
            result += f"## 🎫 {issue.key}: {issue.summary}\n"
            result += f"**🔗 Link:** {issue.url}\n"
            result += f"**📊 Status:** {issue.status} | **🏷️ Type:** {issue.issue_type}\n"
            result += (
                f"**📁 Project:** {issue.project} | "
                f"**⚡ Priority:** {issue.priority or 'Not set'}\n"
            )
            result += f"**🔄 Updated:** {issue.updated}\n\n"

        return {"result": result}
    except Exception as e:
        return {"error": f"❌ Error getting your work: {e!s}"}


@mcp.tool()
async def add_jira_comment(issue_key: str, comment: str) -> dict[str, Any]:
    """Add a comment to a Jira issue"""
    try:
        client = get_jira_client()
        await client.add_comment(issue_key, comment)

        return {"result": f"✅ Comment added successfully to {issue_key}"}
    except Exception as e:
        return {"error": f"❌ Error adding comment: {e!s}"}


def main() -> None:
    """Main entry point for the MCP server"""
    import argparse

    parser = argparse.ArgumentParser(description="Jira MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport mechanism (default: stdio)",
    )

    args = parser.parse_args()

    logger.info(f"Starting Jira MCP Server with {args.transport} transport")
    mcp.run(transport=args.transport)


def cli_main() -> None:
    """Console script entry point"""
    main()


if __name__ == "__main__":
    cli_main()
