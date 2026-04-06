from mcpreviewer.core.detector import detect_mcp_files


class TestDetector:
    def test_matches_mcp_json(self):
        files = ["mcp.json", "src/app.py"]
        assert detect_mcp_files(files) == ["mcp.json"]

    def test_matches_nested_path(self):
        files = ["services/auth/mcp.yaml"]
        assert detect_mcp_files(files) == ["services/auth/mcp.yaml"]

    def test_matches_hidden_mcp_file(self):
        files = [".mcp.json", "readme.md"]
        assert detect_mcp_files(files) == [".mcp.json"]

    def test_matches_mcp_config(self):
        files = ["mcp-config.json", "mcp-config.yaml"]
        assert detect_mcp_files(files) == ["mcp-config.json", "mcp-config.yaml"]

    def test_ignores_unrelated(self):
        files = ["src/app.py", "README.md", "package.json"]
        assert detect_mcp_files(files) == []

    def test_empty_input(self):
        assert detect_mcp_files([]) == []

    def test_custom_patterns(self):
        files = ["custom/tools.json", "mcp.json"]
        result = detect_mcp_files(files, patterns=["**/tools.json"])
        assert result == ["custom/tools.json"]

    def test_multiple_matches(self):
        files = ["mcp.json", "services/mcp.yaml", "other/mcp.yml"]
        result = detect_mcp_files(files)
        assert len(result) == 3

    def test_yml_extension(self):
        files = ["config/mcp.yml"]
        assert detect_mcp_files(files) == ["config/mcp.yml"]
