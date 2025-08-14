# Jira MCP Server

A modern Model Context Protocol (MCP) server for integrating with Jira Cloud using personal API tokens. This server provides secure tools to interact with your Jira instance, allowing you to read issues, search for tickets, manage your work, and add comments.

## ✨ Features

- **🎫 Read Jira Issues** - Get detailed information about specific tickets with rich formatting
- **🔍 Search Issues** - Use JQL (Jira Query Language) to find tickets with flexible queries
- **📋 Get My Work** - Retrieve your assigned issues with optional filtering
- **💬 Add Comments** - Post comments to Jira issues using Atlassian Document Format
- **🔒 Personal API Access** - Secure authentication using your personal API token
- **⚡ Fast Setup** - Built with modern tooling using `uv` for dependency management

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip
- Access to Jira Cloud
- Personal Jira API token

### Installation

1. **Install uv** (if not already installed):

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Clone and setup**:

   ```bash
   cd jira-mcp
   ./setup.sh
   ```

3. **Set environment variables**:

   ```bash
   export JIRA_BASE_URL="https://yourcompany.atlassian.net"
   export JIRA_EMAIL="your-email@company.com"
   export JIRA_API_TOKEN="your-personal-api-token"
   ```

4. **Test the connection**:

   ```bash
   uv run python example_usage.py
   ```

5. **Run the MCP server**:
   ```bash
   uv run python main.py
   # or
   uv run jira-mcp
   ```

### 🖥️ Claude Desktop Integration

To use with Claude Desktop, add this configuration to your `claude_desktop_config.json`:

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

Replace `/absolute/path/to/jira-mcp` with the actual path to your jira-mcp directory.

### 🔑 Creating a Personal API Token

1. Go to [Atlassian Account Settings](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Click **"Create API token"**
3. Give it a descriptive name (e.g., "MCP Jira Integration")
4. Copy the token and use it as `JIRA_API_TOKEN`

> **Important**: Keep your API token secure and never commit it to version control!

## 📋 Configuration

The server requires three environment variables:

| Variable         | Description             | Example                             |
| ---------------- | ----------------------- | ----------------------------------- |
| `JIRA_BASE_URL`  | Your Jira instance URL  | `https://yourcompany.atlassian.net` |
| `JIRA_EMAIL`     | Your Jira account email | `john.doe@company.com`              |
| `JIRA_API_TOKEN` | Your personal API token | `ATATT3xFfGF0T...`                  |

### Making Environment Variables Persistent

Add these to your shell configuration (`~/.bashrc`, `~/.zshrc`, etc.):

```bash
# Jira MCP Server Configuration
export JIRA_BASE_URL="https://yourcompany.atlassian.net"
export JIRA_EMAIL="your-email@company.com"
export JIRA_API_TOKEN="your-personal-api-token"
```

## 🛠️ Available Tools

### 1. `read_jira_issue`

Read a specific Jira issue by its key with rich formatting and direct links.

**Parameters:**

- `issue_key` (string): The Jira issue key (e.g., "PROJ-123")

**Example:**

```json
{
  "tool": "read_jira_issue",
  "arguments": {
    "issue_key": "PROJ-123"
  }
}
```

### 2. `search_jira_issues`

Search for Jira issues using JQL with comprehensive results.

**Parameters:**

- `jql` (string): JQL query string
- `max_results` (integer, optional): Maximum results (1-100, default: 50)

**Examples:**

```json
{
  "tool": "search_jira_issues",
  "arguments": {
    "jql": "project = PROJ AND status IN ('Open', 'In Progress')",
    "max_results": 25
  }
}
```

### 3. `get_my_work`

Get your assigned issues with optional status filtering.

**Parameters:**

- `status_filter` (string, optional): Filter by status

**Examples:**

```json
{
  "tool": "get_my_work",
  "arguments": {
    "status_filter": "In Progress"
  }
}
```

### 4. `add_jira_comment`

Add a comment to a Jira issue using Atlassian Document Format.

**Parameters:**

- `issue_key` (string): The Jira issue key
- `comment` (string): Comment text

**Example:**

```json
{
  "tool": "add_jira_comment",
  "arguments": {
    "issue_key": "PROJ-123",
    "comment": "This issue has been reviewed and approved for development."
  }
}
```

## 🔍 JQL Query Examples

### Basic Queries

```jql
project = PROJ                           # All issues in project PROJ
status = "In Progress"                   # All in-progress issues
priority = High                          # All high priority issues
assignee = currentUser()                 # Issues assigned to you
```

### Advanced Queries

```jql
project = PROJ AND status IN ("Open", "In Progress")
assignee = currentUser() AND updated >= -7d
reporter = currentUser() AND created >= -30d
text ~ "bug" AND priority = High
```

### Date-based Queries

```jql
created >= -1w                           # Issues created in the last week
updated >= startOfDay()                  # Issues updated today
resolved >= -1M                          # Issues resolved in the last month
assignee = currentUser() AND updated >= -7d ORDER BY updated DESC
```

## 🏗️ Development

### Using uv (Recommended)

```bash
# Install dependencies
uv sync

# Run the server
uv run python main.py

# Run tests
uv run pytest

# Run specific test file
uv run pytest tests/test_server.py

# Format code
uv run black .
uv run ruff check . --fix
```

### Using pip (Alternative)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e .

# Run the server
python main.py
```

### Project Structure

```
jira-mcp/
├── pyproject.toml                       # Project config with uv support
├── uv.lock                              # Lock file for reproducible builds
├── main.py                              # Entry point
├── setup.sh                             # Setup script
├── example_usage.py                     # Usage examples and testing
├── claude_desktop_config.json           # Claude Desktop configuration example
├── README.md                            # This file
├── src/
│   └── jira_mcp_server/
│       ├── __init__.py                  # Package initialization
│       └── server.py                    # Main server implementation
└── tests/
    └── test_server.py                   # Unit tests
```

## 🔒 Security Best Practices

1. **Never commit API tokens** - Use environment variables
2. **Use personal tokens** - Don't share tokens between users
3. **Rotate tokens regularly** - Create new tokens periodically
4. **Limit token scope** - Only grant necessary permissions
5. **Monitor token usage** - Check Atlassian account for unusual activity

## 🐛 Troubleshooting

### Common Issues

**"Missing environment variables"**

- Check that all three environment variables are set
- Verify spelling of variable names
- Ensure no extra spaces in values

**"Jira API error: 401"**

- Verify your API token is correct
- Check that your email address is correct
- Ensure you have access to the Jira instance

**"No issues found"**

- Check your JQL syntax
- Verify you have access to the projects you're querying
- Try simpler queries first (e.g., `assignee = currentUser()`)

### Debug Mode

Run with debug logging:

```bash
export PYTHONPATH=.
export MCP_LOG_LEVEL=DEBUG
uv run python main.py
```

## 📊 Performance

- **Optimized HTTP client** - Uses `httpx` with connection pooling
- **Efficient queries** - Fetches only necessary fields
- **Smart pagination** - Configurable result limits
- **Resource cleanup** - Proper connection management

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Format code with `black` and `ruff`
6. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- [Model Context Protocol](https://github.com/modelcontextprotocol/python-sdk) for the MCP framework
- [Atlassian](https://developer.atlassian.com/cloud/jira/platform/rest/v3/) for the Jira REST API
- [uv](https://github.com/astral-sh/uv) for modern Python package management

## 📞 Support

If you encounter any issues or have questions:

1. Check the troubleshooting section above
2. Run `uv run python example_usage.py` to test your setup
3. Create an issue in the project repository with:
   - Your environment details
   - Error messages
   - Steps to reproduce

---

**Happy Jira automation!** 🎉
