import pytest

from mcpreviewer.core.parser import parse_mcp_file
from mcpreviewer.models.types import ParseError
from tests.conftest import load_fixture


class TestParser:
    def test_parse_json_tools(self):
        content = load_fixture("mcp_simple.json")
        manifest = parse_mcp_file("mcp.json", content)
        assert len(manifest.tools) == 1
        assert manifest.tools[0].name == "get_users"
        assert "Retrieves" in manifest.tools[0].description

    def test_parse_yaml_tools(self):
        content = load_fixture("mcp_delete_tool.yaml")
        manifest = parse_mcp_file("mcp.yaml", content)
        assert len(manifest.tools) == 1
        assert manifest.tools[0].name == "delete_record"

    def test_parse_scopes_oauth(self):
        content = load_fixture("mcp_scope_expansion.json")
        manifest = parse_mcp_file("mcp.json", content)
        assert len(manifest.scopes) == 1
        assert manifest.scopes[0].access == "read/write"

    def test_parse_mcpservers_format(self):
        content = load_fixture("mcp_servers_format.json")
        manifest = parse_mcp_file("mcp.json", content)
        assert len(manifest.tools) == 1
        assert manifest.tools[0].name == "github-server"

    def test_parse_annotations(self):
        content = load_fixture("mcp_annotations.json")
        manifest = parse_mcp_file("mcp.json", content)
        assert manifest.tools[0].annotations["destructiveHint"] is True

    def test_parse_empty_file(self):
        manifest = parse_mcp_file("mcp.json", "{}")
        assert len(manifest.tools) == 0
        assert len(manifest.scopes) == 0

    def test_parse_empty_string(self):
        manifest = parse_mcp_file("mcp.json", "")
        assert len(manifest.tools) == 0

    def test_parse_malformed(self):
        content = load_fixture("mcp_malformed.json")
        with pytest.raises(ParseError):
            parse_mcp_file("mcp.json", content)

    def test_parse_missing_keys(self):
        content = '{"random": "data"}'
        manifest = parse_mcp_file("mcp.json", content)
        assert len(manifest.tools) == 0
        assert len(manifest.scopes) == 0

    def test_parse_multi_tool(self):
        content = load_fixture("mcp_multi_tool.json")
        manifest = parse_mcp_file("mcp.json", content)
        assert len(manifest.tools) == 4

    def test_parse_permissions_format(self):
        content = '{"permissions": {"pull_requests": "write", "contents": "read"}}'
        manifest = parse_mcp_file("mcp.json", content)
        assert len(manifest.scopes) == 2
        names = {s.name for s in manifest.scopes}
        assert "pull_requests" in names
        assert "contents" in names

    def test_input_schema_extracted(self):
        content = load_fixture("mcp_simple.json")
        manifest = parse_mcp_file("mcp.json", content)
        assert "properties" in manifest.tools[0].input_schema
