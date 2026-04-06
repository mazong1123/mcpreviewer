from __future__ import annotations

from mcpreviewer.models.types import (
    ChangeType,
    DiffResult,
    McpManifest,
    ScopeChange,
    ToolChange,
    ToolDefinition,
)

SCOPE_ORDER = {"none": 0, "read": 1, "read/write": 2, "write": 2, "admin": 3}


def diff_manifests(
    base: McpManifest | None,
    head: McpManifest | None,
) -> DiffResult:
    """Compare *base* and *head* manifests and return all changes."""
    base_tools = {t.name: t for t in base.tools} if base else {}
    head_tools = {t.name: t for t in head.tools} if head else {}

    tool_changes: list[ToolChange] = []

    added = head_tools.keys() - base_tools.keys()
    removed = base_tools.keys() - head_tools.keys()
    common = base_tools.keys() & head_tools.keys()

    for name in sorted(added):
        tool_changes.append(
            ToolChange(change_type=ChangeType.ADDED, tool_name=name, new_tool=head_tools[name])
        )

    for name in sorted(removed):
        tool_changes.append(
            ToolChange(change_type=ChangeType.REMOVED, tool_name=name, old_tool=base_tools[name])
        )

    for name in sorted(common):
        old = base_tools[name]
        new = head_tools[name]
        if old != new:
            tool_changes.append(
                ToolChange(
                    change_type=ChangeType.MODIFIED,
                    tool_name=name,
                    old_tool=old,
                    new_tool=new,
                    description_only=_is_description_only_change(old, new),
                )
            )

    scope_changes = _diff_scopes(
        base.scopes if base else [],
        head.scopes if head else [],
    )

    return DiffResult(tool_changes=tool_changes, scope_changes=scope_changes)


def merge_diffs(diffs: list[DiffResult]) -> DiffResult:
    return DiffResult(
        tool_changes=[tc for d in diffs for tc in d.tool_changes],
        scope_changes=[sc for d in diffs for sc in d.scope_changes],
        analyzed_files=[f for d in diffs for f in d.analyzed_files],
    )


# ------------------------------------------------------------------

def _is_description_only_change(old: ToolDefinition, new: ToolDefinition) -> bool:
    return (
        old.name == new.name
        and old.input_schema == new.input_schema
        and old.annotations == new.annotations
        and old.description != new.description
    )


def _diff_scopes(
    base_scopes: list,
    head_scopes: list,
) -> list[ScopeChange]:
    base_map = {s.name: s for s in base_scopes}
    head_map = {s.name: s for s in head_scopes}
    changes: list[ScopeChange] = []

    for name, head_scope in head_map.items():
        if name not in base_map:
            changes.append(
                ScopeChange(
                    scope_name=name,
                    new_access=head_scope.access,
                    is_expansion=True,
                )
            )
        else:
            base_scope = base_map[name]
            if head_scope.access != base_scope.access:
                changes.append(
                    ScopeChange(
                        scope_name=name,
                        old_access=base_scope.access,
                        new_access=head_scope.access,
                        is_expansion=_is_scope_expansion(base_scope.access, head_scope.access),
                    )
                )

    return changes


def _is_scope_expansion(old_access: str, new_access: str) -> bool:
    old_level = SCOPE_ORDER.get(old_access.lower(), 0)
    new_level = SCOPE_ORDER.get(new_access.lower(), 0)
    return new_level > old_level
