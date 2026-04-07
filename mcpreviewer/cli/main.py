from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import click

from mcpreviewer.core.pipeline import analyze
from mcpreviewer.core.policy import POLICY_FILE_NAMES
from mcpreviewer.models.types import Recommendation, RiskLevel

RISK_ORDER = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


@click.command("analyze")
@click.option("--base", default="origin/main", help="Base git ref")
@click.option("--head", default="HEAD", help="Head git ref")
@click.option("--repo", default=".", type=click.Path(exists=True), help="Repo path")
@click.option("--format", "output_format", default="text", type=click.Choice(["text", "json"]))
@click.option("--policy", "policy_path", default=None, type=click.Path(), help="Policy file path")
@click.option(
    "--fail-on",
    "fail_on",
    default=None,
    type=click.Choice(["low", "medium", "high", "critical"]),
    help="Exit non-zero at this risk level or above",
)
def analyze_cmd(base: str, head: str, repo: str, output_format: str, policy_path: str | None, fail_on: str | None):
    """Analyze MCP changes between two git refs."""
    repo_path = Path(repo).resolve()

    changed_files = _git_changed_files(repo_path, base, head)
    if not changed_files:
        click.echo("No changed files found.")
        sys.exit(0)

    file_contents: dict[str, tuple[str | None, str | None]] = {}
    for fp in changed_files:
        base_content = _git_show(repo_path, base, fp)
        head_content = _git_show(repo_path, head, fp)
        file_contents[fp] = (base_content, head_content)

    policy_content: str | None = None
    if policy_path:
        p = Path(policy_path)
        if p.exists():
            policy_content = p.read_text(encoding="utf-8")
    else:
        for name in POLICY_FILE_NAMES:
            p = repo_path / name
            if p.exists():
                policy_content = p.read_text(encoding="utf-8")
                break

    result = analyze(changed_files, file_contents, policy_content)

    if result is None:
        click.echo("No MCP-related changes detected.")
        sys.exit(0)

    if output_format == "json":
        click.echo(json.dumps(_result_to_dict(result), indent=2))
    else:
        click.echo(_render_text(result))

    if fail_on:
        threshold = _parse_risk_level(fail_on)
        if _risk_meets_threshold(result.risk_level, threshold):
            sys.exit(2 if result.recommendation == Recommendation.MANUAL_APPROVAL_REQUIRED else 1)

    sys.exit(0)


# ------------------------------------------------------------------
# Git helpers
# ------------------------------------------------------------------

def _git_changed_files(repo: Path, base: str, head: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=repo,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        result = subprocess.run(
            ["git", "diff", "--name-only", base, head],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    if result.returncode != 0:
        click.echo(f"Error running git diff: {result.stderr}", err=True)
        sys.exit(3)
    return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]


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


# ------------------------------------------------------------------
# Output
# ------------------------------------------------------------------

def _render_text(result) -> str:
    lines: list[str] = []
    lines.append(f"Recommendation: {result.recommendation.value}")
    lines.append(f"Risk: {result.risk_level.value}")
    lines.append("")
    lines.append(result.summary)
    lines.append("")

    if result.tool_changes:
        lines.append("Key Changes:")
        for tc in result.tool_changes:
            caps = ", ".join(c.value for c in tc.capabilities)
            domains = ", ".join(d.value for d in tc.sensitive_domains)
            line = f"  {tc.change_type.value.upper()} {tc.tool_name}"
            if caps:
                line += f"  [{caps}]"
            if domains:
                line += f"  (domain: {domains})"
            lines.append(line)

    if result.scope_changes:
        for sc in result.scope_changes:
            lines.append(f"  SCOPE {sc.scope_name}: {sc.old_access} → {sc.new_access}")

    lines.append("")
    lines.append("Reasons:")
    for r in result.reasons:
        lines.append(f"  - {r}")

    lines.append("")
    lines.append(f"Analyzed files: {', '.join(result.analyzed_files)}")
    return "\n".join(lines)


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


def _parse_risk_level(value: str) -> RiskLevel:
    return {
        "low": RiskLevel.LOW,
        "medium": RiskLevel.MEDIUM,
        "high": RiskLevel.HIGH,
        "critical": RiskLevel.CRITICAL,
    }[value.lower()]


def _risk_meets_threshold(actual: RiskLevel, threshold: RiskLevel) -> bool:
    return RISK_ORDER[actual] >= RISK_ORDER[threshold]


if __name__ == "__main__":
    analyze_cmd()
