from mcpreviewer.core.policy import load_policy
from mcpreviewer.models.types import Capability, RiskLevel, SensitiveDomain
from tests.conftest import load_fixture


class TestPolicy:
    def test_load_valid_policy(self):
        content = load_fixture("policy_strict.yml")
        policy = load_policy(content)
        assert policy.version == 1
        assert len(policy.rules) == 3
        assert policy.options.ignore_description_only is True

    def test_load_missing_file(self):
        policy = load_policy(None)
        assert policy.version == 1
        assert policy.rules == []

    def test_load_malformed_yaml(self):
        content = load_fixture("policy_malformed.yml")
        policy = load_policy(content)
        # should fall back to defaults
        assert policy.version == 1
        assert policy.rules == []

    def test_case_insensitive_enum(self):
        content = """
version: 1
rules:
  - capability: delete
    min_risk: critical
"""
        policy = load_policy(content)
        assert policy.rules[0].capability == Capability.DELETE
        assert policy.rules[0].min_risk == RiskLevel.CRITICAL

    def test_unknown_enum_value(self):
        content = """
version: 1
rules:
  - capability: nonexistent
    min_risk: High
"""
        policy = load_policy(content)
        assert policy.rules[0].capability is None

    def test_patterns_parsed(self):
        content = """
version: 1
patterns:
  - "**/mcp.json"
  - "**/custom/*.yaml"
"""
        policy = load_policy(content)
        assert len(policy.patterns) == 2

    def test_domain_rule(self):
        content = load_fixture("policy_strict.yml")
        policy = load_policy(content)
        domain_rules = [r for r in policy.rules if r.domain is not None]
        assert len(domain_rules) == 2
        domains = {r.domain for r in domain_rules}
        assert SensitiveDomain.EMAIL in domains
        assert SensitiveDomain.BILLING_PAYMENTS in domains

    def test_fail_ci_threshold(self):
        content = load_fixture("policy_strict.yml")
        policy = load_policy(content)
        assert policy.options.fail_ci_threshold == RiskLevel.HIGH

    def test_default_policy(self):
        content = load_fixture("policy_default.yml")
        policy = load_policy(content)
        assert policy.options.ignore_description_only is False
        assert len(policy.rules) == 0

    def test_non_dict_yaml(self):
        policy = load_policy("- a list\n- not a dict")
        assert policy.version == 1
        assert policy.rules == []
