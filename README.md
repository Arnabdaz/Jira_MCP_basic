# Jira MCP Server

A Model Context Protocol (MCP) server for integrating with Jira Cloud and Confluence Cloud using personal API tokens. This server provides read-only tools for AI agents to understand Jira tickets, search issues, explore projects, and find, search and read Confluence documentation.

## Features

- **Read Jira Issues** — Full ticket detail including description, labels, components, environment, linked issues (blocks/is blocked by/relates to), attachments, sub-tasks, parent key, and comment count
- **Search Issues** — JQL queries with pagination
- **Get My Work** — Issues assigned to the current user, with optional status filter and pagination
- **Get Issue Comments** — All comments in chronological order with pagination
- **Get Projects** — List all accessible Jira projects
- **Search Confluence** — Full-text or CQL search over pages and blog posts, optionally per space
- **Read Confluence Pages** — Full page content as markdown, by page id or URL
- **Browse Confluence** — List a page's child pages to walk a documentation tree
- **Ticket → Docs** — Confluence pages linked from a Jira issue (design docs, RFCs, runbooks)
- **Personal API Access** — Secure authentication using your personal API token

Confluence uses the **same site, email and API token** as Jira — no extra configuration.

All tools are read-only (`readOnlyHint: true`).

## Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv)
- Access to Jira Cloud + personal API token

### Installation

1. **Clone and setup**:

   ```bash
   git clone https://github.com/Arnabdaz/Jira_MCP_basic.git jira-mcp
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
   uv run jira-mcp                        # stdio (default)
   uv run jira-mcp --transport sse        # SSE
   uv run jira-mcp --transport streamable-http  # Streamable HTTP
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

Search using JQL with pagination. The JQL must be **bounded** (include at least
one search restriction, e.g. `project = PROJ`); a bare `ORDER BY created DESC` is
rejected by Jira.

```json
{
  "tool": "search_jira_issues",
  "arguments": {
    "jql": "project = PROJ AND status = 'In Progress'",
    "max_results": 20
  }
}
```

### `get_my_work`

Issues assigned to the authenticated user, ordered by last updated.

```json
{
  "tool": "get_my_work",
  "arguments": { "status_filter": "In Progress", "max_results": 20 }
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

### `search_confluence`

Full-text search over Confluence pages and blog posts, optionally limited to a
space. Pass `cql` instead of `query` for a raw
[CQL](https://developer.atlassian.com/cloud/confluence/advanced-searching-using-cql/)
expression. Results include page ids, space, last-modified time and a highlighted excerpt.

```json
{ "tool": "search_confluence", "arguments": { "query": "token exchange", "space_key": "ENG" } }
{ "tool": "search_confluence", "arguments": { "cql": "title ~ \"RFC\" AND label = \"design\"" } }
```

### `read_confluence_page`

Page content as markdown (headings, lists, tables, code, links, panels, status
labels, task lists; body-less macros appear as `[macro: name]`). Accepts a page id
or full page URL.

**Long pages don't flood the context.** Pages up to `max_chars` (default 15000,
about 4k tokens) are returned whole. Longer pages return a numbered **outline**
with section sizes plus the intro, and the agent then reads only what it needs:

| Argument | Returns |
|----------|---------|
| `section="2.1"` or `section="Troubleshooting"` | Just that section (with its subsections). If it is still too long, its own outline. Ambiguous titles list up to 20 matches. |
| `find="token exchange"` | The 5 best-matching sections, each with its number and a snippet. Add `section=` to search only within that section. |
| `part=2`, `3`, … | Pages through text without headings, or a single huge section (with `section=`). In outline mode `part=1` is the outline and `part=2…` page through a long intro. |

The outline numbers the first three heading levels by nesting (a lone title heading
at the top isn't numbered) and stays within `max_chars`, collapsing to fewer levels
for very large pages. `#` lines inside code blocks are ignored. Agents that support
sub-agents are told to delegate long-doc reading to one, so only the needed facts
reach the main conversation.

```json
{
  "tool": "read_confluence_page",
  "arguments": { "page": "https://acme.atlassian.net/wiki/spaces/ENG/pages/12345/Setup+Guide" }
}
{ "tool": "read_confluence_page", "arguments": { "page": "12345", "section": "3.2" } }
{ "tool": "read_confluence_page", "arguments": { "page": "12345", "find": "audience claim" } }
```

### `get_confluence_page_children`

Direct children (pages, folders) of a page, with cursor pagination.

```json
{ "tool": "get_confluence_page_children", "arguments": { "page": "12345" } }
```

### `get_issue_confluence_pages`

Confluence pages linked from a Jira issue.

```json
{ "tool": "get_issue_confluence_pages", "arguments": { "issue_key": "PROJ-123" } }
```

## Pagination

`search_jira_issues` and `get_my_work` use Jira's enhanced search
(`POST /rest/api/3/search/jql`), which paginates with an opaque token. When there
are more results, the response ends with the exact token to pass back:

```
More results available. Call again with `page_token="<token>"` to get the next page.
```

The first page also shows an approximate total (from
`POST /rest/api/3/search/approximate-count`). Tokens expire after 7 days.

`get_issue_comments` still uses offset pagination via `start_at`:

```
More results available. Call again with `start_at=20` to get the next page.
```

### Jira API endpoints used

All calls go to Jira Cloud REST API v3:

| Tool | Endpoint |
|------|----------|
| `read_jira_issue` | `GET /rest/api/3/issue/{key}` |
| `search_jira_issues`, `get_my_work` | `POST /rest/api/3/search/jql`, `POST /rest/api/3/search/approximate-count` |
| `get_issue_comments` | `GET /rest/api/3/issue/{key}/comment` |
| `get_projects` | `GET /rest/api/3/project/search` |
| `get_issue_confluence_pages` | `GET /rest/api/3/issue/{key}/remotelink` |

`search_confluence` and `get_confluence_page_children` paginate with a `cursor`
value, given in the response when more results exist.

### Confluence API endpoints used

| Tool | Endpoint |
|------|----------|
| `search_confluence` | `GET /wiki/rest/api/search` (REST v1 — Confluence v2 has no search) |
| `read_confluence_page` | `GET /wiki/api/v2/pages/{id}?body-format=atlas_doc_format`, `GET /wiki/api/v2/spaces/{id}` |
| `get_confluence_page_children` | `GET /wiki/api/v2/pages/{id}/direct-children` |

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
├── example_usage.py
├── src/
│   └── jira_mcp_server/
│       ├── __init__.py
│       ├── __main__.py      # python -m jira_mcp_server support
│       ├── server.py        # Entry point + CLI argument parsing
│       ├── app.py           # FastMCP instance + lifespan hook
│       ├── tools.py             # Jira MCP tool definitions
│       ├── confluence_tools.py  # Confluence MCP tool definitions
│       ├── client.py            # JiraClient + data models (shared HTTP session)
│       ├── confluence.py        # ConfluenceClient (reuses JiraClient session/auth)
│       ├── sections.py          # Outline/section/search navigation for long pages
│       └── adf.py               # ADF → markdown converter (Jira + Confluence)
└── tests/
    ├── test_adf.py
    ├── test_client.py
    ├── test_confluence.py
    ├── test_confluence_tools.py
    ├── test_sections.py
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

# Type check
uv run mypy src/

# Format
uv run black src/ tests/
```

## Troubleshooting

**"Missing environment variables"** — Check all three env vars are set with correct names.

**"Jira API error: 401"** — Verify your API token and email are correct. Atlassian
API tokens expire (at most one year), so an old token may need regenerating. Use a
regular API token: tokens created "with scopes" don't work with the site URL.

**"No issues found" when you expect results** — Check your JQL syntax; try
`assignee = currentUser()` first. If credentials are invalid, Jira may answer some
requests anonymously (empty results, or "issue does not exist") instead of failing
with 401 — so if a ticket you can open in the browser comes back missing, regenerate
the API token.

**"Current user not permitted to use Confluence" (403)** — Your Atlassian account
has no Confluence access on this site, or the token is invalid.

**"Not Found" (404) reading a page** — The page id is wrong, or you lack permission
to view it (Confluence reports restricted pages as not found).

**Short links** — `/wiki/x/...` links are not supported; open the page and copy its
full URL, or use the numeric page id.

## License

MIT
