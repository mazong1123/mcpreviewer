from __future__ import annotations

import logging

import yaml

from mcpreviewer.models.types import (
    Capability,
    Policy,
    PolicyOptions,
    PolicyRule,
    RiskLevel,
    SensitiveDomain,
)

logger = logging.getLogger(__name__)

POLICY_FILE_NAMES = [".mcpreviewer.yml", ".mcpreviewer.yaml"]


def load_policy(content: str | None) -> Policy:
    """Parse policy file content. Returns defaults when *content* is ``None`` or malformed."""
    if content is None:
        return Policy()

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        logger.warning("Malformed policy file, using defaults: %s", exc)
        return Policy()

    if not isinstance(data, dict):
        logger.warning("Policy file is not a mapping, using defaults")
        return Policy()

    return _parse_policy(data)


def _parse_policy(data: dict) -> Policy:
    policy = Policy()
    policy.version = data.get("version", 1)

    raw_patterns = data.get("patterns", [])
    if isinstance(raw_patterns, list):
        policy.patterns = [str(p) for p in raw_patterns]

    raw_rules = data.get("rules", [])
    if isinstance(raw_rules, list):
        for r in raw_rules:
            if not isinstance(r, dict):
                continue
            rule = PolicyRule()
            if "capability" in r:
                rule.capability = _safe_enum(Capability, r["capability"])
            if "domain" in r:
                rule.domain = _safe_enum(SensitiveDomain, r["domain"])
            if "min_risk" in r:
                parsed = _safe_enum(RiskLevel, r["min_risk"])
                if parsed:
                    rule.min_risk = parsed
            policy.rules.append(rule)

    raw_options = data.get("options", {})
    if isinstance(raw_options, dict):
        policy.options = PolicyOptions(
            ignore_description_only=bool(raw_options.get("ignore_description_only", False)),
            fail_ci_threshold=_safe_enum(RiskLevel, raw_options.get("fail_ci_threshold")) or RiskLevel.HIGH,
        )

    return policy


def _safe_enum(enum_cls, value):
    if value is None:
        return None
    value_lower = str(value).lower().strip()
    for member in enum_cls:
        if member.value.lower() == value_lower or member.name.lower() == value_lower:
            return member
    # Partial match: check if value is a prefix of the enum value (e.g. "billing" → "billing / payments")
    for member in enum_cls:
        if member.value.lower().startswith(value_lower):
            return member
    logger.warning("Unknown %s value: %s", enum_cls.__name__, value)
    return None
