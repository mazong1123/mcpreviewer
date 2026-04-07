"""MCP Server for MCP Reviewer.

Exposes MCP Reviewer's analysis capabilities as MCP tools so that AI agents
can review MCP configuration changes via the Model Context Protocol.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from mcpreviewer.core.comment_renderer import render_comment
from mcpreviewer.core.pipeline import analyze

mcp = FastMCP(
    "MCP Reviewer",
    instructions="Analyzes MCP configuration changes and recommends whether they are safe to merge.",
)


def _result_to_dict(result) -> dict:
    return {
        "recommendation": result.recommendation.value,
        "risk_level": result.risk_level.value,
        "total_points": result.total_points,
        "summary": result.summary,
        "tool_changes": [
            {
                "change_type": tc.change_type.value,
                "tool_name": tc.tool_name,
                "capabilities": [c.value for c in tc.capabilities],
                "sensitive_domains": [d.value for d in tc.sensitive_domains],
                "description_only": tc.description_only,
            }
            for tc in result.tool_changes
        ],
        "scope_changes": [
            {
                "scope_name": sc.scope_name,
                "old_access": sc.old_access,
                "new_access": sc.new_access,
                "is_expansion": sc.is_expansion,
            }
            for sc in result.scope_changes
        ],
        "reasons": result.reasons,
        "analyzed_files": result.analyzed_files,
    }


@mcp.tool()
def analyze_mcp_change(
    file_path: str,
    base_content: str = "",
    head_content: str = "",
    policy_content: str = "",
    classifier: str = "rule-based",
) -> str:
    """Analyze an MCP configuration change and return a review recommendation.

    Compares the base (old) and head (new) versions of an MCP config file
    and produces a risk assessment with a recommendation:
    Safe to merge, Review recommended, or Manual approval required.

    Args:
        file_path: Path to the MCP file being changed (e.g. "mcp.json").
        base_content: Content of the file BEFORE the change. Empty string if the file is new.
        head_content: Content of the file AFTER the change. Empty string if the file is deleted.
        policy_content: Optional repo policy YAML content to customize thresholds.
        classifier: Classification strategy: "rule-based" (default) or "llm".

    Returns:
        JSON string with recommendation, risk level, summary, tool changes, and reasons.
    """
    base = base_content if base_content else None
    head = head_content if head_content else None
    policy = policy_content if policy_content else None

    result = analyze(
        changed_files=[file_path],
        file_contents={file_path: (base, head)},
        policy_content=policy,
        classifier=classifier,
    )

    if result is None:
        return json.dumps({"message": "No MCP-related changes detected in the provided file."})

    return json.dumps(_result_to_dict(result), indent=2)


@mcp.tool()
def render_review_comment(
    file_path: str,
    base_content: str = "",
    head_content: str = "",
    policy_content: str = "",
    classifier: str = "rule-based",
) -> str:
    """Analyze an MCP change and return a formatted Markdown PR comment.

    Same analysis as analyze_mcp_change, but returns the output as a
    ready-to-post GitHub PR comment in Markdown format.

    Args:
        file_path: Path to the MCP file being changed (e.g. "mcp.json").
        base_content: Content of the file BEFORE the change. Empty string if new.
        head_content: Content of the file AFTER the change. Empty string if deleted.
        policy_content: Optional repo policy YAML content.
        classifier: Classification strategy: "rule-based" (default) or "llm".

    Returns:
        Markdown-formatted review comment, or a message if no MCP changes found.
    """
    base = base_content if base_content else None
    head = head_content if head_content else None
    policy = policy_content if policy_content else None

    result = analyze(
        changed_files=[file_path],
        file_contents={file_path: (base, head)},
        policy_content=policy,
        classifier=classifier,
    )

    if result is None:
        return "No MCP-related changes detected in the provided file."

    return render_comment(result)


@mcp.tool()
def analyze_git_diff(
    repo_path: str = ".",
    base_ref: str = "HEAD~1",
    head_ref: str = "HEAD",
    classifier: str = "rule-based",
) -> str:
    """Analyze MCP changes between two git refs in a local repository.

    Runs git diff between base_ref and head_ref, finds MCP files,
    and produces a review recommendation.

    Args:
        repo_path: Path to the git repository (default: current directory).
        base_ref: Base git reference (default: HEAD~1).
        head_ref: Head git reference (default: HEAD).
        classifier: Classification strategy: "rule-based" (default) or "llm".

    Returns:
        JSON string with the review result, or a message if no MCP changes found.
    """
    repo = Path(repo_path).resolve()

    # Get changed files
    result = subprocess.run(
        ["git", "diff", "--name-only", base_ref, head_ref],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return json.dumps({"error": f"git diff failed: {result.stderr.strip()}"})

    changed_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    if not changed_files:
        return json.dumps({"message": "No changed files found between the given refs."})

    # Read file contents at each ref
    file_contents: dict[str, tuple[str | None, str | None]] = {}
    for fp in changed_files:
        base_content = _git_show(repo, base_ref, fp)
        head_content = _git_show(repo, head_ref, fp)
        file_contents[fp] = (base_content, head_content)

    # Load policy if present
    policy_content = _git_show(repo, head_ref, ".mcpreviewer.yml")
    if policy_content is None:
        policy_content = _git_show(repo, head_ref, ".mcpreviewer.yaml")

    analysis = analyze(
        changed_files=changed_files,
        file_contents=file_contents,
        policy_content=policy_content,
        classifier=classifier,
    )

    if analysis is None:
        return json.dumps({"message": "No MCP-related changes detected in the diff."})

    return json.dumps(_result_to_dict(analysis), indent=2)


def _git_show(repo: Path, ref: str, file_path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{ref}:{file_path}"],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return None
    return result.stdout


def main():
    mcp.run()


if __name__ == "__main__":
    main()
