from __future__ import annotations

from fnmatch import fnmatch
from pathlib import PurePosixPath

DEFAULT_PATTERNS: list[str] = [
    "**/mcp.json",
    "**/mcp.yaml",
    "**/mcp.yml",
    "**/.mcp.json",
    "**/.mcp.yaml",
    "**/.mcp.yml",
    "**/mcp-config.*",
]


def detect_mcp_files(
    changed_files: list[str],
    patterns: list[str] | None = None,
) -> list[str]:
    """Return the subset of *changed_files* that match MCP file patterns."""
    if not changed_files:
        return []

    use_patterns = patterns if patterns else DEFAULT_PATTERNS
    matched: list[str] = []

    for file_path in changed_files:
        posix = str(PurePosixPath(file_path))
        name = PurePosixPath(file_path).name
        for pattern in use_patterns:
            # fnmatch doesn't handle ** well – strip leading **/
            base_pattern = pattern
            if base_pattern.startswith("**/"):
                base_pattern = base_pattern[3:]
            if fnmatch(posix, pattern) or fnmatch(name, base_pattern) or fnmatch(posix, base_pattern):
                matched.append(file_path)
                break

    return matched
