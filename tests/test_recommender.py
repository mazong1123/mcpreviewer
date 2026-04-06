from mcpreviewer.core.recommender import recommend
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


class TestRecommender:
    def test_low_safe(self):
        rec, _ = recommend(_scoring(RiskLevel.LOW), _diff())
        assert rec == Recommendation.SAFE_TO_MERGE

    def test_medium_review(self):
        rec, _ = recommend(_scoring(RiskLevel.MEDIUM), _diff())
        assert rec == Recommendation.REVIEW_RECOMMENDED

    def test_high_manual(self):
        rec, _ = recommend(_scoring(RiskLevel.HIGH), _diff())
        assert rec == Recommendation.MANUAL_APPROVAL_REQUIRED

    def test_critical_manual(self):
        rec, _ = recommend(_scoring(RiskLevel.CRITICAL), _diff())
        assert rec == Recommendation.MANUAL_APPROVAL_REQUIRED

    def test_reasons_include_write(self):
        diff = _diff(tool_changes=[
            ToolChange(
                change_type=ChangeType.ADDED,
                tool_name="t",
                capabilities=[Capability.WRITE],
            )
        ])
        _, reasons = recommend(_scoring(RiskLevel.MEDIUM), diff)
        assert any("write" in r.lower() for r in reasons)

    def test_reasons_include_delete(self):
        diff = _diff(tool_changes=[
            ToolChange(
                change_type=ChangeType.ADDED,
                tool_name="t",
                capabilities=[Capability.DELETE],
            )
        ])
        _, reasons = recommend(_scoring(RiskLevel.HIGH), diff)
        assert any("delete" in r.lower() for r in reasons)

    def test_reasons_include_domains(self):
        diff = _diff(tool_changes=[
            ToolChange(
                change_type=ChangeType.ADDED,
                tool_name="t",
                capabilities=[Capability.WRITE],
                sensitive_domains=[SensitiveDomain.BILLING_PAYMENTS],
            )
        ])
        _, reasons = recommend(_scoring(RiskLevel.HIGH), diff)
        assert any("billing" in r.lower() for r in reasons)

    def test_reasons_scope_expansion(self):
        diff = _diff(scope_changes=[
            ScopeChange(scope_name="api", old_access="read", new_access="write", is_expansion=True)
        ])
        _, reasons = recommend(_scoring(RiskLevel.MEDIUM), diff)
        assert any("scope" in r.lower() for r in reasons)

    def test_reasons_fallback_safe(self):
        _, reasons = recommend(_scoring(RiskLevel.LOW), _diff())
        assert any("no new" in r.lower() for r in reasons)

    def test_reasons_unknown(self):
        diff = _diff(tool_changes=[
            ToolChange(
                change_type=ChangeType.ADDED,
                tool_name="t",
                capabilities=[Capability.UNKNOWN],
            )
        ])
        _, reasons = recommend(_scoring(RiskLevel.MEDIUM), diff)
        assert any("unknown" in r.lower() for r in reasons)
