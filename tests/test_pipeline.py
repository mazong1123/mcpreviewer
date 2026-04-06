from mcpreviewer.core.pipeline import analyze
from mcpreviewer.models.types import Recommendation, RiskLevel
from tests.conftest import load_fixture


class TestPipeline:
    def test_no_mcp_files(self):
        result = analyze(
            changed_files=["src/app.py"],
            file_contents={"src/app.py": (None, "print('hi')")},
        )
        assert result is None

    def test_full_pipeline_safe(self):
        base = load_fixture("mcp_simple.json")
        head = load_fixture("mcp_simple.json")  # no change
        result = analyze(
            changed_files=["mcp.json"],
            file_contents={"mcp.json": (base, head)},
        )
        # Same content = no changes
        assert result is not None
        assert result.recommendation == Recommendation.SAFE_TO_MERGE
        assert result.risk_level == RiskLevel.LOW

    def test_full_pipeline_write_tool(self):
        base = load_fixture("mcp_simple.json")
        head = load_fixture("mcp_write_tool.json")
        result = analyze(
            changed_files=["mcp.json"],
            file_contents={"mcp.json": (base, head)},
        )
        assert result is not None
        assert result.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)
        assert any("write" in r.lower() for r in result.reasons)

    def test_full_pipeline_new_file(self):
        head = load_fixture("mcp_write_tool.json")
        result = analyze(
            changed_files=["mcp.json"],
            file_contents={"mcp.json": (None, head)},
        )
        assert result is not None
        assert len(result.tool_changes) == 2
        assert len(result.analyzed_files) == 1

    def test_full_pipeline_delete_tool(self):
        head = load_fixture("mcp_delete_tool.yaml")
        result = analyze(
            changed_files=["mcp.yaml"],
            file_contents={"mcp.yaml": (None, head)},
        )
        assert result is not None
        assert result.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)

    def test_pipeline_with_policy(self):
        head = load_fixture("mcp_delete_tool.yaml")
        policy_content = load_fixture("policy_strict.yml")
        result = analyze(
            changed_files=["mcp.yaml"],
            file_contents={"mcp.yaml": (None, head)},
            policy_content=policy_content,
        )
        assert result is not None
        assert result.risk_level == RiskLevel.CRITICAL

    def test_scope_expansion_pipeline(self):
        base = load_fixture("mcp_scope_base.json")
        head = load_fixture("mcp_scope_expansion.json")
        result = analyze(
            changed_files=["mcp.json"],
            file_contents={"mcp.json": (base, head)},
        )
        assert result is not None
        assert any("scope" in r.lower() for r in result.reasons)

    def test_pipeline_multi_tool(self):
        head = load_fixture("mcp_multi_tool.json")
        result = analyze(
            changed_files=["mcp.json"],
            file_contents={"mcp.json": (None, head)},
        )
        assert result is not None
        assert len(result.tool_changes) == 4

    def test_pipeline_malformed_head(self):
        base = load_fixture("mcp_simple.json")
        head = load_fixture("mcp_malformed.json")
        result = analyze(
            changed_files=["mcp.json"],
            file_contents={"mcp.json": (base, head)},
        )
        # Head can't parse → treated as deleted file
        assert result is not None

    def test_pipeline_description_only_with_policy(self):
        base = load_fixture("mcp_simple.json")
        head = load_fixture("mcp_description_only.json")
        policy_content = load_fixture("policy_strict.yml")
        result = analyze(
            changed_files=["mcp.json"],
            file_contents={"mcp.json": (base, head)},
            policy_content=policy_content,
        )
        assert result is not None
        assert result.risk_level == RiskLevel.LOW

    def test_summary_present(self):
        head = load_fixture("mcp_write_tool.json")
        result = analyze(
            changed_files=["mcp.json"],
            file_contents={"mcp.json": (None, head)},
        )
        assert result is not None
        assert len(result.summary) > 20
