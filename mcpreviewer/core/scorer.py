from __future__ import annotations

from mcpreviewer.models.types import (
    Capability,
    ChangeType,
    DiffResult,
    Policy,
    RiskLevel,
    ScoringResult,
)

CAPABILITY_POINTS: dict[Capability, int] = {
    Capability.READ: 0,
    Capability.WRITE: 2,
    Capability.DELETE: 3,
    Capability.SEND_NOTIFY: 2,
    Capability.EXECUTE: 3,
    Capability.ADMIN: 3,
    Capability.SENSITIVE_SYSTEM_ACCESS: 2,
    Capability.UNKNOWN: 2,
}

SCOPE_EXPANSION_POINTS: int = 3

RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


def score(diff: DiffResult, policy: Policy | None = None) -> ScoringResult:
    points = 0
    breakdown: list[tuple[str, int]] = []
    ignore_desc = policy.options.ignore_description_only if policy else False

    for tc in diff.tool_changes:
        if tc.change_type == ChangeType.REMOVED:
            breakdown.append((f"Removed tool: {tc.tool_name}", 0))
            continue

        if tc.description_only:
            if ignore_desc:
                breakdown.append((f"Description-only change: {tc.tool_name} (ignored)", 0))
            else:
                breakdown.append((f"Description-only change: {tc.tool_name}", 0))
            continue

        for cap in tc.capabilities:
            cap_points = CAPABILITY_POINTS.get(cap, 0)
            if cap_points > 0:
                points += cap_points
                breakdown.append(
                    (f"{tc.change_type.value.title()} tool '{tc.tool_name}': {cap.value}", cap_points)
                )

    for sc in diff.scope_changes:
        if sc.is_expansion:
            points += SCOPE_EXPANSION_POINTS
            breakdown.append(
                (f"Scope expansion: {sc.scope_name} ({sc.old_access} → {sc.new_access})",
                 SCOPE_EXPANSION_POINTS)
            )

    risk_level = _points_to_risk(points)

    if policy:
        risk_level = _apply_policy_escalation(risk_level, diff, policy)

    return ScoringResult(total_points=points, risk_level=risk_level, point_breakdown=breakdown)


# ------------------------------------------------------------------

def _points_to_risk(points: int) -> RiskLevel:
    if points == 0:
        return RiskLevel.LOW
    if points <= 3:
        return RiskLevel.MEDIUM
    if points <= 6:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


def _apply_policy_escalation(
    current: RiskLevel,
    diff: DiffResult,
    policy: Policy,
) -> RiskLevel:
    max_risk = RISK_ORDER[current]

    for rule in policy.rules:
        for tc in diff.tool_changes:
            if rule.capability and rule.capability in tc.capabilities:
                max_risk = max(max_risk, RISK_ORDER[rule.min_risk])
            if rule.domain:
                for d in tc.sensitive_domains:
                    if d == rule.domain:
                        max_risk = max(max_risk, RISK_ORDER[rule.min_risk])

    for level, order in RISK_ORDER.items():
        if order == max_risk:
            return level
    return current
