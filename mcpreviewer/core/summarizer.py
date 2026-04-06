from __future__ import annotations

from mcpreviewer.models.types import (
    Capability,
    ChangeType,
    DiffResult,
    Recommendation,
    ScoringResult,
)


def summarize(
    diff: DiffResult,
    scoring: ScoringResult,
    recommendation: Recommendation,
) -> str:
    sentences: list[str] = []

    # 1. What changed
    added = [tc for tc in diff.tool_changes if tc.change_type == ChangeType.ADDED]
    removed = [tc for tc in diff.tool_changes if tc.change_type == ChangeType.REMOVED]
    modified = [tc for tc in diff.tool_changes if tc.change_type == ChangeType.MODIFIED]

    parts: list[str] = []
    if added:
        parts.append(f"adds {_pluralize(len(added), 'new tool')}")
    if removed:
        parts.append(f"removes {_pluralize(len(removed), 'tool')}")
    if modified:
        parts.append(f"modifies {_pluralize(len(modified), 'existing tool')}")

    if parts:
        sentences.append(f"This PR {', '.join(parts)} in the MCP configuration.")
    else:
        sentences.append("This PR contains changes to the MCP configuration.")

    # 2. Notable capabilities
    write_tools = [tc for tc in diff.tool_changes if Capability.WRITE in tc.capabilities]
    delete_tools = [tc for tc in diff.tool_changes if Capability.DELETE in tc.capabilities]
    send_tools = [tc for tc in diff.tool_changes if Capability.SEND_NOTIFY in tc.capabilities]
    exec_tools = [tc for tc in diff.tool_changes if Capability.EXECUTE in tc.capabilities]

    notable: list[str] = []
    if write_tools:
        notable.append(f"{_pluralize(len(write_tools), 'tool')} can write data")
    if delete_tools:
        notable.append(f"{_pluralize(len(delete_tools), 'tool')} can delete data")
    if send_tools:
        notable.append(f"{_pluralize(len(send_tools), 'tool')} can send messages or notifications")
    if exec_tools:
        notable.append(f"{_pluralize(len(exec_tools), 'tool')} can execute commands")

    if notable:
        sentences.append("Among the changes, " + " and ".join(notable) + ".")

    # 3. Scope changes
    expansions = [sc for sc in diff.scope_changes if sc.is_expansion]
    if expansions:
        scope_desc = ", ".join(
            f"{sc.scope_name} ({sc.old_access} → {sc.new_access})" for sc in expansions
        )
        sentences.append(f"OAuth/permission scope expands: {scope_desc}.")

    # 4. Sensitive domains
    all_domains: set = set()
    for tc in diff.tool_changes:
        all_domains.update(tc.sensitive_domains)
    if all_domains:
        domain_names = ", ".join(sorted(d.value for d in all_domains))
        sentences.append(f"This affects sensitive systems: {domain_names}.")

    # 5. Conclusion
    if recommendation == Recommendation.MANUAL_APPROVAL_REQUIRED:
        sentences.append("Manual approval is required due to the scope of capability expansion.")
    elif recommendation == Recommendation.REVIEW_RECOMMENDED:
        sentences.append("Reviewer attention is recommended before merging.")
    else:
        sentences.append("No significant capability expansion was detected.")

    return " ".join(sentences[:5])


def _pluralize(count: int, word: str) -> str:
    return f"{count} {word}{'s' if count != 1 else ''}"
