from __future__ import annotations

from mcpreviewer.models.types import (
    Capability,
    ReviewResult,
)


def render_comment(result: ReviewResult) -> str:
    """Render the PR comment markdown from a ReviewResult."""
    lines: list[str] = []
    lines.append("## MCP Reviewer")
    lines.append("")
    lines.append(f"**Recommendation:** {result.recommendation.value}  ")
    lines.append(f"**Risk:** {result.risk_level.value}")
    lines.append("")
    lines.append(result.summary)
    lines.append("")

    if result.tool_changes or result.scope_changes:
        lines.append("### Key Changes")
        lines.append("")
        lines.append("| Change | Detail |")
        lines.append("|---|---|")

        for tc in result.tool_changes:
            action = tc.change_type.value.title()
            lines.append(f"| {action} tool | `{tc.tool_name}` |")

            for cap in tc.capabilities:
                if cap not in (Capability.READ, Capability.SENSITIVE_SYSTEM_ACCESS):
                    lines.append(f"| New capability | {cap.value} |")

            for domain in tc.sensitive_domains:
                lines.append(f"| Sensitive domain | {domain.value} |")

        for sc in result.scope_changes:
            if sc.is_expansion:
                lines.append(
                    f"| Scope change | `{sc.scope_name}`: "
                    f"`{sc.old_access}` → `{sc.new_access}` |"
                )

        lines.append("")

    if result.reasons:
        lines.append("### Reasons")
        lines.append("")
        for r in result.reasons:
            lines.append(f"- {r}")
        lines.append("")

    lines.append("---")
    lines.append("*MCP Reviewer v1*")
    return "\n".join(lines)
