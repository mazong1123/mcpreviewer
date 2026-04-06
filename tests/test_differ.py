from mcpreviewer.core.differ import diff_manifests, merge_diffs
from mcpreviewer.models.types import (
    ChangeType,
    McpManifest,
    ScopeDefinition,
    ToolDefinition,
)


def _manifest(tools=None, scopes=None):
    return McpManifest(
        file_path="mcp.json",
        tools=tools or [],
        scopes=scopes or [],
    )


class TestDiffer:
    def test_added_tool(self):
        base = _manifest()
        head = _manifest(tools=[ToolDefinition(name="create_ticket")])
        result = diff_manifests(base, head)
        assert len(result.tool_changes) == 1
        assert result.tool_changes[0].change_type == ChangeType.ADDED
        assert result.tool_changes[0].tool_name == "create_ticket"

    def test_removed_tool(self):
        base = _manifest(tools=[ToolDefinition(name="old_tool")])
        head = _manifest()
        result = diff_manifests(base, head)
        assert len(result.tool_changes) == 1
        assert result.tool_changes[0].change_type == ChangeType.REMOVED

    def test_modified_tool(self):
        base = _manifest(tools=[ToolDefinition(name="t", description="old")])
        head = _manifest(tools=[ToolDefinition(name="t", description="new")])
        result = diff_manifests(base, head)
        assert len(result.tool_changes) == 1
        assert result.tool_changes[0].change_type == ChangeType.MODIFIED

    def test_description_only_change(self):
        base = _manifest(tools=[ToolDefinition(name="t", description="old")])
        head = _manifest(tools=[ToolDefinition(name="t", description="new")])
        result = diff_manifests(base, head)
        assert result.tool_changes[0].description_only is True

    def test_not_description_only(self):
        base = _manifest(tools=[ToolDefinition(name="t", description="old", input_schema={"a": 1})])
        head = _manifest(tools=[ToolDefinition(name="t", description="new", input_schema={"a": 2})])
        result = diff_manifests(base, head)
        assert result.tool_changes[0].description_only is False

    def test_scope_expansion(self):
        base = _manifest(scopes=[ScopeDefinition(name="api", access="read")])
        head = _manifest(scopes=[ScopeDefinition(name="api", access="read/write")])
        result = diff_manifests(base, head)
        assert len(result.scope_changes) == 1
        assert result.scope_changes[0].is_expansion is True
        assert result.scope_changes[0].old_access == "read"
        assert result.scope_changes[0].new_access == "read/write"

    def test_scope_no_change(self):
        base = _manifest(scopes=[ScopeDefinition(name="api", access="read")])
        head = _manifest(scopes=[ScopeDefinition(name="api", access="read")])
        result = diff_manifests(base, head)
        assert len(result.scope_changes) == 0

    def test_new_scope(self):
        base = _manifest()
        head = _manifest(scopes=[ScopeDefinition(name="api", access="write")])
        result = diff_manifests(base, head)
        assert len(result.scope_changes) == 1
        assert result.scope_changes[0].is_expansion is True

    def test_new_file(self):
        head = _manifest(tools=[ToolDefinition(name="a"), ToolDefinition(name="b")])
        result = diff_manifests(None, head)
        assert len(result.tool_changes) == 2
        assert all(tc.change_type == ChangeType.ADDED for tc in result.tool_changes)

    def test_deleted_file(self):
        base = _manifest(tools=[ToolDefinition(name="a")])
        result = diff_manifests(base, None)
        assert len(result.tool_changes) == 1
        assert result.tool_changes[0].change_type == ChangeType.REMOVED

    def test_no_changes(self):
        m = _manifest(tools=[ToolDefinition(name="a", description="d")])
        result = diff_manifests(m, m)
        assert len(result.tool_changes) == 0
        assert len(result.scope_changes) == 0

    def test_merge_diffs(self):
        d1 = diff_manifests(None, _manifest(tools=[ToolDefinition(name="a")]))
        d1.analyzed_files = ["file1.json"]
        d2 = diff_manifests(None, _manifest(tools=[ToolDefinition(name="b")]))
        d2.analyzed_files = ["file2.json"]
        merged = merge_diffs([d1, d2])
        assert len(merged.tool_changes) == 2
        assert len(merged.analyzed_files) == 2
