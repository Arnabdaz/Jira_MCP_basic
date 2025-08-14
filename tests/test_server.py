"""
Tests for the Jira MCP Server
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jira_mcp_server.server import JiraClient, JiraConfig


class TestJiraConfig:
    """Test JiraConfig model"""

    def test_config_creation(self):
        """Test creating a JiraConfig instance"""
        config = JiraConfig(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
        )

        assert config.base_url == "https://test.atlassian.net"
        assert config.email == "test@example.com"
        assert config.api_token == "test-token"


class TestJiraClient:
    """Test JiraClient functionality"""

    @pytest.fixture
    def config(self):
        """Create a test configuration"""
        return JiraConfig(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
        )

    @pytest.fixture
    def client(self, config):
        """Create a test client"""
        return JiraClient(config)

    def test_client_initialization(self, client):
        """Test client initialization"""
        assert client.config.base_url == "https://test.atlassian.net"
        assert client.config.email == "test@example.com"
        assert client.config.api_token == "test-token"
        assert client.base_url == "https://test.atlassian.net"

    def test_get_user_display_name(self, client):
        """Test user display name extraction"""
        # Test with display name
        user_data = {"displayName": "John Doe", "emailAddress": "john@example.com"}
        assert client._get_user_display_name(user_data) == "John Doe"

        # Test with email only
        user_data = {"emailAddress": "john@example.com"}
        assert client._get_user_display_name(user_data) == "john@example.com"

        # Test with None
        assert client._get_user_display_name(None) is None

    def test_extract_description_string(self, client):
        """Test description extraction from string"""
        assert client._extract_description("Simple text") == "Simple text"
        assert client._extract_description(None) is None

    def test_extract_description_adf(self, client):
        """Test description extraction from ADF format"""
        adf_data = {
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hello"},
                        {"type": "text", "text": "world!"},
                    ],
                }
            ]
        }

        assert client._extract_description(adf_data) == "Hello world!"

    def test_extract_adf_text(self, client):
        """Test ADF text extraction"""
        content = [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "First paragraph."}],
            },
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Second paragraph."}],
            },
        ]

        result = client._extract_adf_text(content)
        assert "First paragraph." in result
        assert "Second paragraph." in result


class TestEnvironmentVariables:
    """Test environment variable handling"""

    @patch.dict(
        os.environ,
        {
            "JIRA_BASE_URL": "https://test.atlassian.net",
            "JIRA_EMAIL": "test@example.com",
            "JIRA_API_TOKEN": "test-token",
        },
    )
    def test_get_jira_client_with_env_vars(self):
        """Test getting client with environment variables"""
        # Reset global client
        import jira_mcp_server.server
        from jira_mcp_server.server import get_jira_client

        jira_mcp_server.server._jira_client = None

        client = get_jira_client()
        assert client.config.base_url == "https://test.atlassian.net"
        assert client.config.email == "test@example.com"
        assert client.config.api_token == "test-token"

    def test_get_jira_client_missing_env_vars(self):
        """Test getting client with missing environment variables"""
        # Reset global client
        import jira_mcp_server.server
        from jira_mcp_server.server import get_jira_client

        jira_mcp_server.server._jira_client = None

        # Clear environment variables
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Missing required environment variables"):
                get_jira_client()


@pytest.mark.asyncio
class TestAsyncMethods:
    """Test async methods with mocking"""

    @pytest.fixture
    def mock_client(self):
        """Create a mocked client"""
        config = JiraConfig(
            base_url="https://test.atlassian.net",
            email="test@example.com",
            api_token="test-token",
        )
        client = JiraClient(config)
        client.session = AsyncMock()
        return client

    async def test_get_issue_success(self, mock_client):
        """Test successful issue retrieval"""
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "key": "TEST-123",
            "id": "12345",
            "fields": {
                "summary": "Test issue",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "project": {"key": "TEST"},
            },
        }
        mock_client.session.request.return_value = mock_response

        issue = await mock_client.get_issue("TEST-123")

        assert issue.key == "TEST-123"
        assert issue.summary == "Test issue"
        assert issue.status == "Open"
        assert issue.issue_type == "Bug"
        assert issue.project == "TEST"

    async def test_search_issues_success(self, mock_client):
        """Test successful issue search"""
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {
            "issues": [
                {
                    "key": "TEST-123",
                    "id": "12345",
                    "fields": {
                        "summary": "Test issue",
                        "status": {"name": "Open"},
                        "issuetype": {"name": "Bug"},
                        "project": {"key": "TEST"},
                    },
                }
            ]
        }
        mock_client.session.request.return_value = mock_response

        issues = await mock_client.search_issues("project = TEST")

        assert len(issues) == 1
        assert issues[0].key == "TEST-123"
        assert issues[0].summary == "Test issue"

    async def test_add_comment_success(self, mock_client):
        """Test successful comment addition"""
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"id": "comment-123", "body": "Test comment"}
        mock_client.session.request.return_value = mock_response

        result = await mock_client.add_comment("TEST-123", "Test comment")

        assert result["id"] == "comment-123"
        assert result["body"] == "Test comment"

        # Verify the request was made with correct ADF format
        mock_client.session.request.assert_called_once()
        call_args = mock_client.session.request.call_args
        assert call_args[0][0] == "POST"  # method
        assert "comment" in call_args[0][1]  # endpoint

        # Check JSON payload structure
        json_payload = call_args[1]["json"]
        assert "body" in json_payload
        assert json_payload["body"]["type"] == "doc"
        assert json_payload["body"]["version"] == 1
        assert len(json_payload["body"]["content"]) == 1
        assert json_payload["body"]["content"][0]["type"] == "paragraph"


if __name__ == "__main__":
    pytest.main([__file__])
