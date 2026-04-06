import json

from click.testing import CliRunner

from mcpreviewer.cli.main import analyze_cmd


class TestCLI:
    """Tests the CLI using Click's test runner with mocked git operations.

    Since Click's CliRunner doesn't have a real git repo, we test against
    the pipeline directly via the ``--repo`` flag pointing at a temp dir.
    For the full CLI path, we verify argument parsing.
    """

    def test_cli_help(self):
        runner = CliRunner()
        result = runner.invoke(analyze_cmd, ["--help"])
        assert result.exit_code == 0
        assert "Analyze MCP changes" in result.output

    def test_cli_no_repo(self, tmp_path):
        """When there's no git repo, git diff fails → exit 3."""
        runner = CliRunner()
        result = runner.invoke(analyze_cmd, ["--repo", str(tmp_path), "--base", "HEAD~1", "--head", "HEAD"])
        # Should exit 3 because git diff fails in a non-repo dir
        assert result.exit_code == 3
