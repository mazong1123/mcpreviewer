from mcpreviewer.core.summarizer import summarize
from mcpreviewer.models.types import (
    Capability,
    ChangeType,
    DiffResult,
    Recommendation,
    RiskLevel,
    ScopeChange,
    ScoringResult,
    SensitiveDomain,
    ToolChange,
)


def _scoring(risk: RiskLevel, points: int = 0):
    return ScoringResult(total_points=points, risk_level=risk, point_breakdown=[])


def _diff(tool_changes=None, scope_changes=None):
    return DiffResult(tool_changes=tool_changes or [], scope_changes=scope_changes or [])


class TestSummarizer:
    def test_summary_length(self):
        diff = _diff(tool_changes=[
            ToolChange(change_type=ChangeType.ADDED, tool_name="create_ticket",
                       capabilities=[Capability.WRITE]),
        ])
        summary = summarize(diff, _scoring(RiskLevel.MEDIUM), Recommendation.REVIEW_RECOMMENDED)
        sentences = [s.strip() for s in summary.split(".") if s.strip()]
        assert 2 <= len(sentences) <= 5

    def test_summary_mentions_added_tools(self):
        diff = _diff(tool_changes=[
            ToolChange(change_type=ChangeType.ADDED, tool_name="a",
                       capabilities=[Capability.READ]),
            ToolChange(change_type=ChangeType.ADDED, tool_name="b",
                       capabilities=[Capability.READ]),
        ])
        summary = summarize(diff, _scoring(RiskLevel.LOW), Recommendation.SAFE_TO_MERGE)
        assert "2 new tools" in summary

    def test_summary_mentions_write(self):
        diff = _diff(tool_changes=[
            ToolChange(change_type=ChangeType.ADDED, tool_name="create_x",
                       capabilities=[Capability.WRITE]),
        ])
        summary = summarize(diff, _scoring(RiskLevel.MEDIUM), Recommendation.REVIEW_RECOMMENDED)
        assert "write" in summary.lower()

    def test_summary_mentions_delete(self):
        diff = _diff(tool_changes=[
            ToolChange(change_type=ChangeType.ADDED, tool_name="del",
                       capabilities=[Capability.DELETE]),
        ])
        summary = summarize(diff, _scoring(RiskLevel.HIGH), Recommendation.MANUAL_APPROVAL_REQUIRED)
        assert "delete" in summary.lower()

    def test_summary_mentions_domains(self):
        diff = _diff(tool_changes=[
            ToolChange(change_type=ChangeType.ADDED, tool_name="t",
                       capabilities=[Capability.WRITE],
                       sensitive_domains=[SensitiveDomain.TICKETING]),
        ])
        summary = summarize(diff, _scoring(RiskLevel.HIGH), Recommendation.MANUAL_APPROVAL_REQUIRED)
        assert "ticketing" in summary.lower()

    def test_summary_safe_conclusion(self):
        diff = _diff(tool_changes=[
            ToolChange(change_type=ChangeType.ADDED, tool_name="get_x",
                       capabilities=[Capability.READ]),
        ])
        summary = summarize(diff, _scoring(RiskLevel.LOW), Recommendation.SAFE_TO_MERGE)
        assert "no significant" in summary.lower()

    def test_summary_scope_expansion(self):
        diff = _diff(scope_changes=[
            ScopeChange(scope_name="api", old_access="read", new_access="write", is_expansion=True)
        ])
        summary = summarize(diff, _scoring(RiskLevel.MEDIUM), Recommendation.REVIEW_RECOMMENDED)
        assert "scope" in summary.lower()

    def test_summary_manual_conclusion(self):
        diff = _diff(tool_changes=[
            ToolChange(change_type=ChangeType.ADDED, tool_name="del",
                       capabilities=[Capability.DELETE]),
        ])
        summary = summarize(diff, _scoring(RiskLevel.HIGH), Recommendation.MANUAL_APPROVAL_REQUIRED)
        assert "manual approval" in summary.lower()
