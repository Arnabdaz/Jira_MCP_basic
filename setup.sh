#!/bin/bash
# Setup script for Jira MCP Server (using uv)

echo "🚀 Setting up Jira MCP Server with uv..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install uv first:"
    echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "   or visit: https://github.com/astral-sh/uv"
    exit 1
fi

# Install dependencies with uv
echo "📥 Installing dependencies with uv..."
uv sync

echo "✅ Setup complete!"
echo ""
echo "📋 Next steps:"
echo "1. Set your environment variables for personal API access:"
echo "   export JIRA_BASE_URL='https://yourcompany.atlassian.net'"
echo "   export JIRA_EMAIL='your-email@company.com'"
echo "   export JIRA_API_TOKEN='your-personal-api-token'"
echo ""
echo "2. Test the connection:"
echo "   uv run python example_usage.py"
echo ""
echo "3. Run the MCP server:"
echo "   uv run jira-mcp"
echo ""
echo "🔑 To get your personal API token:"
echo "   1. Go to: https://id.atlassian.com/manage-profile/security/api-tokens"
echo "   2. Click 'Create API token'"
echo "   3. Give it a name like 'MCP Jira Integration'"
echo "   4. Copy the token and use it as JIRA_API_TOKEN"
echo ""
echo "💡 Pro tip: Add these exports to your ~/.bashrc or ~/.zshrc for convenience!" 