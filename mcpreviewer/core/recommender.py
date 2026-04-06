from __future__ import annotations

from mcpreviewer.models.types import (
    Capability,
    DiffResult,
    Recommendation,
    RiskLevel,
    ScoringResult,
)

RISK_TO_RECOMMENDATION: dict[RiskLevel, Recommendation] = {
    RiskLevel.LOW: Recommendation.SAFE_TO_MERGE,
    RiskLevel.MEDIUM: Recommendation.REVIEW_RECOMMENDED,
    RiskLevel.HIGH: Recommendation.MANUAL_APPROVAL_REQUIRED,
    RiskLevel.CRITICAL: Recommendation.MANUAL_APPROVAL_REQUIRED,
}


def recommend(
    scoring: ScoringResult,
    diff: DiffResult,
) -> tuple[Recommendation, list[str]]:
    rec = RISK_TO_RECOMMENDATION[scoring.risk_level]
    reasons = _build_reasons(diff)
    return rec, reasons


def _build_reasons(diff: DiffResult) -> list[str]:
    reasons: list[str] = []

    cap_set: set[Capability] = set()
    for tc in diff.tool_changes:
        for cap in tc.capabilities:
            if cap != Capability.READ:
                cap_set.add(cap)

    if Capability.WRITE in cap_set:
        reasons.append("Introduces write access")
    if Capability.DELETE in cap_set:
        reasons.append("Introduces delete capability")
    if Capability.SEND_NOTIFY in cap_set:
        reasons.append("Introduces send/notify capability")
    if Capability.EXECUTE in cap_set:
        reasons.append("Introduces execute capability")
    if Capability.ADMIN in cap_set:
        reasons.append("Introduces admin/configuration capability")
    if Capability.UNKNOWN in cap_set:
        reasons.append("Contains unknown or ambiguous capability")

    expansions = [sc for sc in diff.scope_changes if sc.is_expansion]
    if expansions:
        reasons.append("Expands authentication/authorization scope")

    domain_set = set()
    for tc in diff.tool_changes:
        domain_set.update(tc.sensitive_domains)
    if domain_set:
        domain_names = ", ".join(sorted(d.value for d in domain_set))
        reasons.append(f"Affects sensitive systems: {domain_names}")

    if not reasons:
        reasons.append("No new capabilities or scope expansion detected")

    return reasons
