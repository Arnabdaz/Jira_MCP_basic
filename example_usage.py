#!/usr/bin/env python3
"""
Example usage script for the Jira MCP Server.
This script demonstrates how to use the server tools with personal API access.
"""

import os
import asyncio
from jira_mcp_server.server import get_jira_client


async def test_jira_connection():
    """Test basic Jira connection and functionality with personal API access."""

    # Check if environment variables are set
    required_vars = ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print(f"❌ Missing environment variables: {', '.join(missing_vars)}")
        print("\nPlease set these environment variables for personal API access:")
        print("export JIRA_BASE_URL='https://cloudera.atlassian.net'")
        print("export JIRA_EMAIL='your-email@company.com'")
        print("export JIRA_API_TOKEN='your-personal-api-token'")
        print("\n🔑 Get your personal API token at:")
        print("   https://id.atlassian.com/manage-profile/security/api-tokens")
        return

    print("🔧 Configuration:")
    print(f"   Base URL: {os.getenv('JIRA_BASE_URL')}")
    print(f"   Email: {os.getenv('JIRA_EMAIL')}")
    print(f"   API Token: {'*' * 8}...")
    print()

    try:
        # Initialize client
        client = get_jira_client()
        print("✅ Jira client initialized successfully")

        # Test getting user's work
        print("\n📋 Testing 'get_my_work' functionality...")
        issues = await client.get_my_work()
        print(f"Found {len(issues)} issues assigned to you")

        if issues:
            print("\nYour top 3 issues:")
            for i, issue in enumerate(issues[:3]):
                print(f"  {i+1}. {issue.key}: {issue.summary}")
                print(f"     📊 Status: {issue.status}")
                print(f"     🏷️ Type: {issue.issue_type}")
                print(f"     ⚡ Priority: {issue.priority or 'Not set'}")
                print(f"     🔗 URL: {issue.url}")
                print()

        # Test search functionality
        print("🔍 Testing search functionality...")
        search_results = await client.search_issues(
            "assignee = currentUser()", max_results=5
        )
        print(f"Search returned {len(search_results)} results")

        if search_results:
            print("\nSearch results:")
            for issue in search_results:
                print(f"  • {issue.key}: {issue.summary}")
                print(f"    Status: {issue.status}")

        # Test reading a specific issue
        if issues:
            test_issue = issues[0]
            print(f"\n📖 Testing 'get_issue' with {test_issue.key}...")
            full_issue = await client.get_issue(test_issue.key)
            print(f"Successfully read issue: {full_issue.key}")
            print(f"Summary: {full_issue.summary}")
            print(f"Description length: {len(full_issue.description or '')} characters")

        # Test some useful JQL queries
        print("\n🧪 Testing useful JQL queries...")

        # Recent issues
        recent_issues = await client.search_issues(
            "assignee = currentUser() AND updated >= -7d ORDER BY updated DESC",
            max_results=3,
        )
        print(f"Issues updated in last 7 days: {len(recent_issues)}")

        # Issues by status
        for status in ["To Do", "In Progress", "Done"]:
            try:
                status_issues = await client.search_issues(
                    f"assignee = currentUser() AND status = '{status}'", max_results=1
                )
                print(f"Issues in '{status}': {len(status_issues)}")
            except Exception as e:
                print(f"Could not query '{status}' status: {e}")

        print("\n✅ All tests completed successfully!")
        print("\n🎉 Your Jira MCP server is working perfectly!")

    except Exception as e:
        print(f"❌ Error: {str(e)}")
        print("\n💡 Troubleshooting tips:")
        print("1. Check your API token is valid")
        print("2. Verify your email address is correct")
        print("3. Make sure you have access to the Jira instance")
        print("4. Try accessing the Jira web interface manually")
        return

    finally:
        # Clean up
        if "_jira_client" in locals() and hasattr(client, "close"):
            await client.close()


if __name__ == "__main__":
    asyncio.run(test_jira_connection())
