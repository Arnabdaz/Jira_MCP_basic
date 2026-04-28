# Jira MCP Server

A Model Context Protocol (MCP) server for integrating with Jira Cloud using personal API tokens. This server provides read-only tools for AI agents to understand Jira tickets, search issues, and explore projects.

## Features

- **Read Jira Issues** — Full ticket detail including description, labels, components, environment, linked issues (blocks/is blocked by/relates to), attachments, sub-tasks, parent key, and comment count
- **Search Issues** — JQL queries with pagination
- **Get My Work** — Issues assigned to the current user, with optional status filter and pagination
- **Get Issue Comments** — All comments in chronological order with pagination
- **Get Projects** — List all accessible Jira projects
- **Personal API Access** — Secure authentication using your personal API token

All tools are read-only (`readOnlyHint: true`).

## Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv)
- Access to Jira Cloud + personal API token

### Installation

1. **Clone and setup**:

   ```bash
   cd jira-mcp
   ./setup.sh
   ```

2. **Set environment variables**:

   ```bash
   export JIRA_BASE_URL="https://yourcompany.atlassian.net"
   export JIRA_EMAIL="your-email@company.com"
   export JIRA_API_TOKEN="your-personal-api-token"
   ```

3. **Test the connection**:

   ```bash
   uv run python example_usage.py
   ```

4. **Run the MCP server**:
   ```bash
   uv run jira-mcp
   ```

### Claude Desktop / Claude Code Integration

Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "jira-mcp": {
      "command": "uv",
      "args": ["run", "jira-mcp"],
      "cwd": "/absolute/path/to/jira-mcp",
      "env": {
        "JIRA_BASE_URL": "https://yourcompany.atlassian.net",
        "JIRA_EMAIL": "your-email@company.com",
        "JIRA_API_TOKEN": "your-personal-api-token"
      }
    }
  }
}
```

### Creating a Personal API Token

1. Go to [Atlassian Account Settings](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **"Create API token"**
3. Copy the token and use it as `JIRA_API_TOKEN`

> Never commit your API token to version control.

## Configuration

| Variable         | Description             | Example                             |
| ---------------- | ----------------------- | ----------------------------------- |
| `JIRA_BASE_URL`  | Your Jira instance URL  | `https://yourcompany.atlassian.net` |
| `JIRA_EMAIL`     | Your Jira account email | `john.doe@company.com`              |
| `JIRA_API_TOKEN` | Your personal API token | `ATATT3xFfGF0T...`                  |

## Available Tools

### `read_jira_issue`

Fetch a Jira issue in full detail for bug understanding and resolution.

Returns: summary, status, type, priority, assignee, reporter, description, labels, components, environment, linked issues, attachment list, sub-tasks, parent key, and comment count.

```json
{ "tool": "read_jira_issue", "arguments": { "issue_key": "PROJ-123" } }
```

### `search_jira_issues`

Search using JQL with pagination.

```json
{
  "tool": "search_jira_issues",
  "arguments": {
    "jql": "project = PROJ AND status = 'In Progress'",
    "max_results": 20,
    "start_at": 0
  }
}
```

### `get_my_work`

Issues assigned to the authenticated user, ordered by last updated.

```json
{
  "tool": "get_my_work",
  "arguments": { "status_filter": "In Progress", "max_results": 20, "start_at": 0 }
}
```

### `get_issue_comments`

Comments in chronological order (oldest first) with pagination.

```json
{
  "tool": "get_issue_comments",
  "arguments": { "issue_key": "PROJ-123", "max_results": 20, "start_at": 0 }
}
```

### `get_projects`

List all accessible Jira projects (key, name, type, lead).

```json
{ "tool": "get_projects", "arguments": {} }
```

## Pagination

`search_jira_issues`, `get_my_work`, and `get_issue_comments` all support `start_at` for pagination. When there are more results, the response includes:

```
More results available. Call again with `start_at=20` to get the next page.
```

## JQL Examples

```jql
project = PROJ AND status = "In Progress"
assignee = currentUser() AND priority = High
text ~ "login error" AND created >= -7d
assignee = currentUser() AND updated >= -7d ORDER BY updated DESC
```

## Project Structure

```
jira-mcp/
├── pyproject.toml
├── uv.lock
├── main.py
├── example_usage.py
├── src/
│   └── jira_mcp_server/
│       ├── __init__.py
│       ├── server.py        # Entry point
│       ├── app.py           # FastMCP instance
│       ├── tools.py         # MCP tool definitions
│       ├── client.py        # JiraClient + data models
│       └── adf.py           # ADF → markdown converter
└── tests/
    ├── test_adf.py
    ├── test_client.py
    └── test_tools.py
```

## Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Lint
uv run ruff check src/ tests/
```

## Troubleshooting

**"Missing environment variables"** — Check all three env vars are set with correct names.

**"Jira API error: 401"** — Verify your API token and email are correct.

**"No issues found"** — Check your JQL syntax; try `assignee = currentUser()` first.

## License

MIT
