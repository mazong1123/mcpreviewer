from __future__ import annotations

import logging

from mcpreviewer.core.classifier import classify_all
from mcpreviewer.core.detector import detect_mcp_files
from mcpreviewer.core.differ import diff_manifests, merge_diffs
from mcpreviewer.core.parser import parse_mcp_file
from mcpreviewer.core.policy import load_policy
from mcpreviewer.core.recommender import recommend
from mcpreviewer.core.scorer import score
from mcpreviewer.core.summarizer import summarize
from mcpreviewer.models.types import ParseError, ReviewResult

logger = logging.getLogger(__name__)


def analyze(
    changed_files: list[str],
    file_contents: dict[str, tuple[str | None, str | None]],
    policy_content: str | None = None,
) -> ReviewResult | None:
    """Run the full analysis pipeline.

    Args:
        changed_files: All changed file paths in the PR.
        file_contents: ``{path: (base_content, head_content)}``.
        policy_content: Raw content of the repo policy file, or ``None``.

    Returns:
        A :class:`ReviewResult`, or ``None`` when no MCP files were found.
    """
    policy = load_policy(policy_content)

    patterns = policy.patterns if policy.patterns else None
    mcp_files = detect_mcp_files(changed_files, patterns)

    if not mcp_files:
        return None

    diffs = []
    for file_path in mcp_files:
        base_content, head_content = file_contents.get(file_path, (None, None))

        base_manifest = None
        head_manifest = None

        if base_content is not None:
            try:
                base_manifest = parse_mcp_file(file_path, base_content)
            except ParseError:
                logger.warning("Could not parse base version of %s", file_path)

        if head_content is not None:
            try:
                head_manifest = parse_mcp_file(file_path, head_content)
            except ParseError:
                logger.warning("Could not parse head version of %s", file_path)

        diff = diff_manifests(base_manifest, head_manifest)
        diff.analyzed_files = [file_path]
        diffs.append(diff)

    merged = merge_diffs(diffs)
    merged.tool_changes = classify_all(merged.tool_changes)

    scoring = score(merged, policy)
    recommendation, reasons = recommend(scoring, merged)
    summary = summarize(merged, scoring, recommendation)

    return ReviewResult(
        recommendation=recommendation,
        risk_level=scoring.risk_level,
        summary=summary,
        tool_changes=merged.tool_changes,
        scope_changes=merged.scope_changes,
        reasons=reasons,
        analyzed_files=merged.analyzed_files,
        total_points=scoring.total_points,
    )
