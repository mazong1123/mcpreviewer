"""Quick smoke test for the MCP server tools."""
import json
from mcpreviewer.mcp_server import analyze_mcp_change, render_review_comment, analyze_git_diff

# Test 1: Analyze a new write tool
print("=== Test 1: analyze_mcp_change (new write tool) ===")
result = analyze_mcp_change(
    file_path="mcp.json",
    base_content="",
    head_content=json.dumps({
        "tools": [
            {"name": "create_ticket", "description": "Creates a ticket in Jira"}
        ]
    }),
)
data = json.loads(result)
print(f"Recommendation: {data['recommendation']}")
print(f"Risk: {data['risk_level']}")
print(f"Reasons: {data['reasons']}")
assert data["recommendation"] != "Safe to merge"
print("PASS\n")

# Test 2: Safe read-only tool
print("=== Test 2: analyze_mcp_change (read-only tool) ===")
result2 = analyze_mcp_change(
    file_path="mcp.json",
    base_content="",
    head_content=json.dumps({
        "tools": [
            {"name": "get_users", "description": "Retrieves a list of users"}
        ]
    }),
)
data2 = json.loads(result2)
print(f"Recommendation: {data2['recommendation']}")
assert data2["recommendation"] == "Safe to merge"
print("PASS\n")

# Test 3: Render comment
print("=== Test 3: render_review_comment ===")
comment = render_review_comment(
    file_path="mcp.json",
    base_content="",
    head_content=json.dumps({
        "tools": [
            {"name": "delete_record", "description": "Deletes a database record"}
        ]
    }),
)
assert "## MCP Reviewer" in comment
assert "Manual approval required" in comment or "Review recommended" in comment
print(comment[:300])
print("...\nPASS\n")

# Test 4: Non-MCP file
print("=== Test 4: analyze_mcp_change (non-MCP file) ===")
result4 = analyze_mcp_change(
    file_path="app.py",
    head_content="print('hello')",
)
data4 = json.loads(result4)
assert "No MCP" in data4.get("message", "")
print(f"Message: {data4['message']}")
print("PASS\n")

# Test 5: analyze_git_diff on current repo
print("=== Test 5: analyze_git_diff (current repo) ===")
result5 = analyze_git_diff(repo_path=".", base_ref="HEAD~1", head_ref="HEAD")
data5 = json.loads(result5)
print(f"Result: {list(data5.keys())}")
print("PASS\n")

print("All MCP server tool tests passed!")
