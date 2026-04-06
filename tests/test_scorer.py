from mcpreviewer.core.scorer import score
from mcpreviewer.models.types import (
    Capability,
    ChangeType,
    DiffResult,
    Policy,
    PolicyOptions,
    PolicyRule,
    RiskLevel,
    ScopeChange,
    SensitiveDomain,
    ToolChange,
)


def _diff(tool_changes=None, scope_changes=None):
    return DiffResult(
        tool_changes=tool_changes or [],
        scope_changes=scope_changes or [],
    )


def _tc(name, capabilities, change_type=ChangeType.ADDED, description_only=False, domains=None):
    return ToolChange(
        change_type=change_type,
        tool_name=name,
        capabilities=capabilities,
        description_only=description_only,
        sensitive_domains=domains or [],
    )


class TestScorer:
    def test_read_only_zero_points(self):
        diff = _diff(tool_changes=[_tc("get_users", [Capability.READ])])
        result = score(diff)
        assert result.total_points == 0
        assert result.risk_level == RiskLevel.LOW

    def test_write_two_points(self):
        diff = _diff(tool_changes=[_tc("create_ticket", [Capability.WRITE])])
        result = score(diff)
        assert result.total_points == 2
        assert result.risk_level == RiskLevel.MEDIUM

    def test_delete_three_points(self):
        diff = _diff(tool_changes=[_tc("delete_record", [Capability.DELETE])])
        result = score(diff)
        assert result.total_points == 3
        assert result.risk_level == RiskLevel.MEDIUM

    def test_combined_high(self):
        diff = _diff(tool_changes=[
            _tc("create_ticket", [Capability.WRITE]),
            _tc("delete_record", [Capability.DELETE]),
        ])
        result = score(diff)
        assert result.total_points == 5
        assert result.risk_level == RiskLevel.HIGH

    def test_scope_expansion_points(self):
        diff = _diff(scope_changes=[
            ScopeChange(scope_name="api", old_access="read", new_access="read/write", is_expansion=True)
        ])
        result = score(diff)
        assert result.total_points == 3
        assert result.risk_level == RiskLevel.MEDIUM

    def test_critical_threshold(self):
        diff = _diff(tool_changes=[
            _tc("create_ticket", [Capability.WRITE]),
            _tc("delete_record", [Capability.DELETE]),
            _tc("send_email", [Capability.SEND_NOTIFY]),
        ])
        result = score(diff)
        assert result.total_points == 7
        assert result.risk_level == RiskLevel.CRITICAL

    def test_removed_tool_zero(self):
        diff = _diff(tool_changes=[
            _tc("old_tool", [Capability.DELETE], change_type=ChangeType.REMOVED)
        ])
        result = score(diff)
        assert result.total_points == 0
        assert result.risk_level == RiskLevel.LOW

    def test_description_only_zero(self):
        diff = _diff(tool_changes=[
            _tc("t", [Capability.WRITE], description_only=True)
        ])
        result = score(diff)
        assert result.total_points == 0
        assert result.risk_level == RiskLevel.LOW

    def test_policy_escalation(self):
        diff = _diff(tool_changes=[
            _tc("delete_record", [Capability.DELETE])
        ])
        policy = Policy(
            rules=[PolicyRule(capability=Capability.DELETE, min_risk=RiskLevel.CRITICAL)]
        )
        result = score(diff, policy)
        assert result.risk_level == RiskLevel.CRITICAL

    def test_policy_domain_escalation(self):
        diff = _diff(tool_changes=[
            _tc("charge", [Capability.WRITE], domains=[SensitiveDomain.BILLING_PAYMENTS])
        ])
        policy = Policy(
            rules=[PolicyRule(domain=SensitiveDomain.BILLING_PAYMENTS, min_risk=RiskLevel.CRITICAL)]
        )
        result = score(diff, policy)
        assert result.risk_level == RiskLevel.CRITICAL

    def test_ignore_description_only_policy(self):
        diff = _diff(tool_changes=[
            _tc("t", [Capability.WRITE], description_only=True)
        ])
        policy = Policy(options=PolicyOptions(ignore_description_only=True))
        result = score(diff, policy)
        assert result.total_points == 0

    def test_unknown_capability_points(self):
        diff = _diff(tool_changes=[_tc("mystery", [Capability.UNKNOWN])])
        result = score(diff)
        assert result.total_points == 2
        assert result.risk_level == RiskLevel.MEDIUM

    def test_sensitive_system_points(self):
        diff = _diff(tool_changes=[
            _tc("t", [Capability.SENSITIVE_SYSTEM_ACCESS])
        ])
        result = score(diff)
        assert result.total_points == 2
