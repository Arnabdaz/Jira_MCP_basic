#!/usr/bin/env python3
"""
Example usage script for the Jira MCP Server.
This script demonstrates how to use the JiraClient directly with personal API access.
"""

import asyncio
import os

from jira_mcp_server.client import get_jira_client


async def test_jira_connection() -> None:
    """Test basic Jira connection and functionality with personal API access."""

    # Check if environment variables are set
    required_vars = ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print(f"Missing environment variables: {', '.join(missing_vars)}")
        print("\nPlease set these environment variables for personal API access:")
        print("export JIRA_BASE_URL='https://yourcompany.atlassian.net'")
        print("export JIRA_EMAIL='your-email@company.com'")
        print("export JIRA_API_TOKEN='your-personal-api-token'")
        print("\nGet your personal API token at:")
        print("   https://id.atlassian.com/manage-profile/security/api-tokens")
        return

    print("Configuration:")
    print(f"   Base URL: {os.getenv('JIRA_BASE_URL')}")
    print(f"   Email: {os.getenv('JIRA_EMAIL')}")
    print(f"   API Token: {'*' * 8}...")
    print()

    client = get_jira_client()
    try:
        print("Jira client initialized successfully")

        # Test getting user's work (returns tuple: issues, total)
        print("\nTesting 'get_my_work' functionality...")
        issues, total = await client.get_my_work()
        print(f"Found {total} issues assigned to you (showing {len(issues)})")

        if issues:
            print("\nYour top 3 issues:")
            for i, issue in enumerate(issues[:3]):
                print(f"  {i + 1}. {issue.key}: {issue.summary}")
                print(f"     Status: {issue.status}")
                print(f"     Type: {issue.issue_type}")
                print(f"     Priority: {issue.priority or 'Not set'}")
                print(f"     Labels: {', '.join(issue.labels) or 'None'}")
                print(f"     URL: {issue.url}")
                print()

        # Test search functionality (returns tuple: issues, total)
        print("Testing search functionality...")
        search_results, search_total = await client.search_issues(
            "assignee = currentUser()", max_results=5
        )
        print(f"Search returned {search_total} total results (showing {len(search_results)})")

        # Test reading a specific issue with full detail
        if issues:
            test_issue = issues[0]
            print(f"\nTesting 'get_issue' with {test_issue.key}...")
            full_issue = await client.get_issue(test_issue.key)
            print(f"Successfully read issue: {full_issue.key}")
            print(f"Summary: {full_issue.summary}")
            print(f"Labels: {full_issue.labels}")
            print(f"Components: {full_issue.components}")
            print(f"Linked issues: {len(full_issue.linked_issues)}")
            print(f"Sub-tasks: {len(full_issue.sub_tasks)}")
            print(f"Comments: {full_issue.comment_count}")
            print(f"Description length: {len(full_issue.description or '')} characters")

            # Test fetching comments if any exist
            if full_issue.comment_count > 0:
                print(f"\nFetching comments for {test_issue.key}...")
                comments, comment_total = await client.get_issue_comments(test_issue.key)
                print(f"Got {len(comments)} of {comment_total} comments")
                if comments:
                    print(f"Latest comment by: {comments[-1].author}")

        # Test listing projects
        print("\nTesting 'get_projects'...")
        projects = await client.get_projects()
        print(f"Found {len(projects)} accessible projects")
        for project in projects[:3]:
            print(f"  - {project.key}: {project.name} ({project.project_type})")

        print("\nAll tests completed successfully!")

    except Exception as e:
        print(f"Error: {e!s}")
        print("\nTroubleshooting tips:")
        print("1. Check your API token is valid")
        print("2. Verify your email address is correct")
        print("3. Make sure you have access to the Jira instance")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(test_jira_connection())
