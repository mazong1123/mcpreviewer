from mcpreviewer.core.comment_renderer import render_comment
from mcpreviewer.models.types import (
    Capability,
    ChangeType,
    Recommendation,
    ReviewResult,
    RiskLevel,
    ScopeChange,
    SensitiveDomain,
    ToolChange,
)


class TestCommentRenderer:
    def test_basic_render(self):
        result = ReviewResult(
            recommendation=Recommendation.SAFE_TO_MERGE,
            risk_level=RiskLevel.LOW,
            summary="No significant capability expansion was detected.",
            tool_changes=[],
            scope_changes=[],
            reasons=["No new capabilities or scope expansion detected"],
            analyzed_files=["mcp.json"],
            total_points=0,
        )
        comment = render_comment(result)
        assert "## MCP Reviewer" in comment
        assert "Safe to merge" in comment
        assert "Low" in comment

    def test_render_with_changes(self):
        result = ReviewResult(
            recommendation=Recommendation.MANUAL_APPROVAL_REQUIRED,
            risk_level=RiskLevel.HIGH,
            summary="Manual approval is required.",
            tool_changes=[
                ToolChange(
                    change_type=ChangeType.ADDED,
                    tool_name="create_ticket",
                    capabilities=[Capability.WRITE],
                    sensitive_domains=[SensitiveDomain.TICKETING],
                ),
            ],
            scope_changes=[
                ScopeChange(
                    scope_name="api",
                    old_access="read",
                    new_access="read/write",
                    is_expansion=True,
                ),
            ],
            reasons=["Introduces write access", "Affects sensitive systems: Ticketing"],
            analyzed_files=["mcp.json"],
            total_points=7,
        )
        comment = render_comment(result)
        assert "Manual approval required" in comment
        assert "High" in comment
        assert "`create_ticket`" in comment
        assert "Write" in comment
        assert "Ticketing" in comment
        assert "Scope change" in comment
        assert "Introduces write access" in comment

    def test_render_has_reasons_section(self):
        result = ReviewResult(
            recommendation=Recommendation.REVIEW_RECOMMENDED,
            risk_level=RiskLevel.MEDIUM,
            summary="Reviewer attention is recommended.",
            tool_changes=[],
            scope_changes=[],
            reasons=["Introduces write access"],
            analyzed_files=["mcp.json"],
            total_points=2,
        )
        comment = render_comment(result)
        assert "### Reasons" in comment
        assert "- Introduces write access" in comment

    def test_render_footer(self):
        result = ReviewResult(
            recommendation=Recommendation.SAFE_TO_MERGE,
            risk_level=RiskLevel.LOW,
            summary="Safe.",
            tool_changes=[],
            scope_changes=[],
            reasons=["No new capabilities or scope expansion detected"],
            analyzed_files=["mcp.json"],
            total_points=0,
        )
        comment = render_comment(result)
        assert "*MCP Reviewer v1*" in comment
