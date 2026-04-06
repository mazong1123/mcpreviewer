# MCP Reviewer — Detail Design

**Status:** Draft  
**Version:** V1  
**Owner:** Founder (Solo)  
**Parent Documents:** Requirement.txt, HighLevelDesign.md

---

## Table of Contents

1. [Overview](#1-overview)
2. [Project Structure](#2-project-structure)
3. [Data Models](#3-data-models)
4. [Core Engine — Detailed Module Design](#4-core-engine--detailed-module-design)
5. [GitHub App — Detailed Design](#5-github-app--detailed-design)
6. [CLI — Detailed Design](#6-cli--detailed-design)
7. [Policy File — Detailed Specification](#7-policy-file--detailed-specification)
8. [PR Comment Rendering](#8-pr-comment-rendering)
9. [Error Handling](#9-error-handling)
10. [Configuration & Environment](#10-configuration--environment)
11. [Logging](#11-logging)
12. [Testing — Detailed Plan](#12-testing--detailed-plan)
13. [Packaging & Deployment](#13-packaging--deployment)
14. [API Reference (Internal)](#14-api-reference-internal)

---

## 1. Overview

This document describes the implementation-level design for MCP Reviewer V1. It covers every module's interface, data flow, algorithms, edge cases, and error paths. A solo developer should be able to build V1 from this document alone.

Refer to:
- **Requirement.txt** for product requirements and acceptance criteria.
- **HighLevelDesign.md** for architecture-level decisions and rationale.

---

## 2. Project Structure

```
mcpreviewer/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app factory, lifespan, routes
│   ├── github_client.py        # GitHub API wrapper
│   ├── webhook_handler.py      # Event parsing, signature verification, orchestration
│   └── config.py               # App-level settings (env vars)
├── core/
│   ├── __init__.py
│   ├── detector.py             # MCP file detection
│   ├── parser.py               # MCP file parsing → normalized models
│   ├── differ.py               # Old vs new capability diff
│   ├── classifier.py           # Capability classification
│   ├── scorer.py               # Risk scoring
│   ├── recommender.py          # Recommendation logic
│   ├── summarizer.py           # Plain-English summary generation
│   ├── policy.py               # Policy file loading
│   └── pipeline.py             # Orchestrates core modules end-to-end
├── cli/
│   ├── __init__.py
│   └── main.py                 # Click CLI entrypoint
├── models/
│   ├── __init__.py
│   └── types.py                # All dataclasses and enums
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # Shared fixtures
│   ├── test_detector.py
│   ├── test_parser.py
│   ├── test_differ.py
│   ├── test_classifier.py
│   ├── test_scorer.py
│   ├── test_recommender.py
│   ├── test_summarizer.py
│   ├── test_policy.py
│   ├── test_pipeline.py
│   ├── test_webhook_handler.py
│   ├── test_cli.py
│   └── fixtures/
│       ├── mcp_simple.json
│       ├── mcp_write_tool.json
│       ├── mcp_delete_tool.yaml
│       ├── mcp_scope_expansion.json
│       ├── mcp_unknown_tool.json
│       ├── mcp_description_only.json
│       ├── mcp_multi_tool.json
│       ├── mcp_sensitive_domain.json
│       ├── mcp_malformed.json
│       ├── policy_default.yml
│       ├── policy_strict.yml
│       ├── policy_malformed.yml
│       └── webhook_pr_opened.json
├── Dockerfile
├── pyproject.toml
├── README.md
└── .mcpreviewer.yml.example
```

---

## 3. Data Models

All shared data structures live in `models/types.py`.

### 3.1 Enums

```python
from enum import Enum

class Capability(str, Enum):
    READ = "Read"
    WRITE = "Write"
    DELETE = "Delete"
    SEND_NOTIFY = "Send / Notify"
    EXECUTE = "Execute"
    ADMIN = "Admin / Configuration"
    SENSITIVE_SYSTEM_ACCESS = "Sensitive System Access"
    UNKNOWN = "Unknown"

class SensitiveDomain(str, Enum):
    EMAIL = "Email"
    TICKETING = "Ticketing"
    SOURCE_CONTROL = "Source control"
    DATABASE = "Database"
    CLOUD_INFRASTRUCTURE = "Cloud infrastructure"
    BILLING_PAYMENTS = "Billing / payments"
    CRM_CUSTOMER_RECORDS = "CRM / customer records"
    IDENTITY_AUTH = "Identity / authentication"
    FILE_STORAGE = "File storage"

class RiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"

class Recommendation(str, Enum):
    SAFE_TO_MERGE = "Safe to merge"
    REVIEW_RECOMMENDED = "Review recommended"
    MANUAL_APPROVAL_REQUIRED = "Manual approval required"

class ChangeType(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
```

### 3.2 Dataclasses

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class ToolDefinition:
    """A single tool parsed from an MCP file."""
    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)
    annotations: dict = field(default_factory=dict)   # e.g., readOnlyHint, destructiveHint
    raw: dict = field(default_factory=dict)            # original unparsed dict

@dataclass(frozen=True)
class ScopeDefinition:
    """OAuth or permission scope declared in an MCP config."""
    name: str
    access: str  # e.g., "read", "read/write", "admin"

@dataclass(frozen=True)
class McpManifest:
    """Normalized representation of a single MCP configuration file."""
    file_path: str
    tools: list[ToolDefinition] = field(default_factory=list)
    scopes: list[ScopeDefinition] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

@dataclass
class ToolChange:
    """A single detected change to a tool."""
    change_type: ChangeType             # added, removed, modified
    tool_name: str
    old_tool: ToolDefinition | None = None
    new_tool: ToolDefinition | None = None
    capabilities: list[Capability] = field(default_factory=list)
    sensitive_domains: list[SensitiveDomain] = field(default_factory=list)
    description_only: bool = False      # True if only description text changed

@dataclass
class ScopeChange:
    """A detected change to OAuth/permission scopes."""
    scope_name: str
    old_access: str | None = None
    new_access: str | None = None
    is_expansion: bool = False

@dataclass
class DiffResult:
    """Output of the differ: all changes in this PR."""
    tool_changes: list[ToolChange] = field(default_factory=list)
    scope_changes: list[ScopeChange] = field(default_factory=list)
    analyzed_files: list[str] = field(default_factory=list)

@dataclass
class ScoringResult:
    """Output of the scorer."""
    total_points: int
    risk_level: RiskLevel
    point_breakdown: list[tuple[str, int]]  # (reason_string, points)

@dataclass
class ReviewResult:
    """Final output of the full pipeline."""
    recommendation: Recommendation
    risk_level: RiskLevel
    summary: str                            # 2–5 sentence plain-English
    tool_changes: list[ToolChange]
    scope_changes: list[ScopeChange]
    reasons: list[str]
    analyzed_files: list[str]
    total_points: int
```

### 3.3 Policy Models

```python
@dataclass
class PolicyRule:
    """A single override rule from the policy file."""
    capability: Capability | None = None
    domain: SensitiveDomain | None = None
    min_risk: RiskLevel = RiskLevel.HIGH

@dataclass
class PolicyOptions:
    """Global options from the policy file."""
    ignore_description_only: bool = False
    fail_ci_threshold: RiskLevel = RiskLevel.HIGH

@dataclass
class Policy:
    """Parsed repo policy."""
    version: int = 1
    patterns: list[str] = field(default_factory=list)
    rules: list[PolicyRule] = field(default_factory=list)
    options: PolicyOptions = field(default_factory=PolicyOptions)
```

---

## 4. Core Engine — Detailed Module Design

### 4.1 detector.py — MCP File Detection

**Purpose:** Filter a list of changed file paths to only those that are MCP-relevant.

**Interface:**

```python
def detect_mcp_files(
    changed_files: list[str],
    patterns: list[str] | None = None,
) -> list[str]:
    """
    Return the subset of changed_files that match MCP file patterns.

    Args:
        changed_files: List of file paths from the PR diff.
        patterns: Glob patterns. If None, use DEFAULT_PATTERNS.

    Returns:
        List of matching file paths.
    """
```

**Default patterns:**

```python
DEFAULT_PATTERNS: list[str] = [
    "**/mcp.json",
    "**/mcp.yaml",
    "**/mcp.yml",
    "**/.mcp.json",
    "**/.mcp.yaml",
    "**/.mcp.yml",
    "**/mcp-config.*",
]
```

**Algorithm:**
1. For each `changed_file`, check if it matches any pattern using `fnmatch.fnmatch`.
2. Matching is case-insensitive on Windows, case-sensitive otherwise. Use `PurePosixPath` for consistency.
3. Return all matching paths, preserving order.

**Edge cases:**
- Empty `changed_files` → return `[]`.
- No matches → return `[]`.
- Policy overrides patterns → caller passes the policy patterns.

---

### 4.2 parser.py — MCP File Parsing

**Purpose:** Parse raw MCP file content (JSON or YAML) into a normalized `McpManifest`.

**Interface:**

```python
def parse_mcp_file(
    file_path: str,
    content: str,
) -> McpManifest:
    """
    Parse a single MCP file into a normalized manifest.

    Args:
        file_path: Path of the file (used for format detection and error messages).
        content: Raw file content as a string.

    Returns:
        McpManifest with tools and scopes extracted.

    Raises:
        ParseError: If the file cannot be parsed at all.
    """
```

**Format detection:**
- `.json` → `json.loads(content)`
- `.yaml` / `.yml` → `yaml.safe_load(content)`
- Other extensions → attempt JSON first, then YAML. If both fail, raise `ParseError`.

**Tool extraction logic:**

The parser must handle multiple MCP config formats. V1 supports:

**Format A — mcpServers style (VS Code / Claude Desktop):**
```json
{
  "mcpServers": {
    "server-name": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "..." }
    }
  }
}
```
In this format, tools are not explicitly listed in the config. The parser extracts:
- Server name as identifier
- Environment variables as scope signals (e.g., `GITHUB_TOKEN` → Source control domain)
- `command` + `args` for context

**Format B — Tool manifest style (tool list with schemas):**
```json
{
  "tools": [
    {
      "name": "create_ticket",
      "description": "Creates a new ticket in the ticketing system",
      "inputSchema": {
        "type": "object",
        "properties": { "title": { "type": "string" } }
      }
    }
  ]
}
```
Direct extraction into `ToolDefinition` objects.

**Format C — MCP tool annotations style:**
```json
{
  "tools": [
    {
      "name": "delete_record",
      "description": "Deletes a database record",
      "annotations": {
        "readOnlyHint": false,
        "destructiveHint": true
      }
    }
  ]
}
```
Annotations are preserved and used by the classifier.

**Scope extraction:**
Look for keys: `scopes`, `oauth`, `permissions`, `auth`. Normalize into `ScopeDefinition` objects.

```python
# Example scope sources
# { "scopes": ["read", "write"] }
# { "oauth": { "scopes": ["repo", "user:email"] } }
# { "permissions": { "pull_requests": "write", "contents": "read" } }
```

**Robustness rules:**
- Missing keys → skip, do not fail.
- Extra keys → ignore.
- Empty file → return empty `McpManifest` (not an error).
- Partial parse → extract what is possible, skip what is not.

---

### 4.3 differ.py — Capability Diffing

**Purpose:** Compare two `McpManifest` objects (base vs head) and produce a `DiffResult`.

**Interface:**

```python
def diff_manifests(
    base: McpManifest | None,
    head: McpManifest | None,
) -> DiffResult:
    """
    Compare base and head manifests.

    Args:
        base: The manifest from the base branch (None if file is new).
        head: The manifest from the head branch (None if file is deleted).

    Returns:
        DiffResult with all tool and scope changes.
    """
```

**Algorithm:**

```
base_tools = {t.name: t for t in base.tools} if base else {}
head_tools = {t.name: t for t in head.tools} if head else {}

added = head_tools.keys() - base_tools.keys()
removed = base_tools.keys() - head_tools.keys()
common = base_tools.keys() & head_tools.keys()

For each name in added:
    → ToolChange(ADDED, name, new_tool=head_tools[name])

For each name in removed:
    → ToolChange(REMOVED, name, old_tool=base_tools[name])

For each name in common:
    old = base_tools[name]
    new = head_tools[name]
    if old != new:
        is_desc_only = _is_description_only_change(old, new)
        → ToolChange(MODIFIED, name, old_tool=old, new_tool=new, description_only=is_desc_only)
```

**Description-only change detection:**

```python
def _is_description_only_change(old: ToolDefinition, new: ToolDefinition) -> bool:
    """True if only the description field differs."""
    return (
        old.name == new.name
        and old.input_schema == new.input_schema
        and old.annotations == new.annotations
        and old.description != new.description
    )
```

**Scope diffing:**

```
base_scopes = {s.name: s for s in base.scopes} if base else {}
head_scopes = {s.name: s for s in head.scopes} if head else {}

For each scope in head_scopes:
    if scope not in base_scopes:
        → ScopeChange(scope, new_access=..., is_expansion=True)
    elif head_scopes[scope].access != base_scopes[scope].access:
        → ScopeChange(scope, old=..., new=..., is_expansion=_is_scope_expansion(...))
```

**Scope expansion detection:**

```python
SCOPE_ORDER = {"none": 0, "read": 1, "read/write": 2, "write": 2, "admin": 3}

def _is_scope_expansion(old_access: str, new_access: str) -> bool:
    old_level = SCOPE_ORDER.get(old_access.lower(), 0)
    new_level = SCOPE_ORDER.get(new_access.lower(), 0)
    return new_level > old_level
```

**Multi-file handling:**

When a PR contains multiple MCP files, the pipeline calls `diff_manifests` per file and merges all `DiffResult` objects:

```python
def merge_diffs(diffs: list[DiffResult]) -> DiffResult:
    return DiffResult(
        tool_changes=[tc for d in diffs for tc in d.tool_changes],
        scope_changes=[sc for d in diffs for sc in d.scope_changes],
        analyzed_files=[f for d in diffs for f in d.analyzed_files],
    )
```

---

### 4.4 classifier.py — Capability Classification

**Purpose:** For each `ToolChange`, assign `Capability` labels and `SensitiveDomain` labels.

**Interface:**

```python
def classify_tool_change(change: ToolChange) -> ToolChange:
    """
    Mutates and returns the ToolChange with capabilities and sensitive_domains populated.
    """
```

**Algorithm:**

The classifier examines three text signals from the tool:
1. `name` (the tool name)
2. `description` (the tool description)
3. `annotations` (structured hints)

```python
def classify_tool_change(change: ToolChange) -> ToolChange:
    tool = change.new_tool or change.old_tool
    if tool is None:
        return change

    text = f"{tool.name} {tool.description}".lower()
    caps = set()
    domains = set()

    # 1. Check annotations first (highest confidence)
    if tool.annotations:
        if tool.annotations.get("readOnlyHint") is True:
            caps.add(Capability.READ)
        if tool.annotations.get("destructiveHint") is True:
            caps.add(Capability.DELETE)

    # 2. Keyword matching on name + description
    caps |= _match_capabilities(text)
    domains |= _match_domains(text)

    # 3. If capabilities detected include a sensitive domain, add the flag
    if domains:
        caps.add(Capability.SENSITIVE_SYSTEM_ACCESS)

    # 4. If no capabilities detected, mark Unknown
    if not caps:
        caps.add(Capability.UNKNOWN)

    change.capabilities = sorted(caps, key=lambda c: c.value)
    change.sensitive_domains = sorted(domains, key=lambda d: d.value)
    return change
```

**Keyword tables:**

```python
CAPABILITY_KEYWORDS: dict[Capability, list[str]] = {
    Capability.READ: [
        "get_", "list_", "fetch_", "read_", "search_", "find_",
        "retrieve", "query", "lookup", "describe",
    ],
    Capability.WRITE: [
        "create_", "update_", "set_", "put_", "add_", "insert_",
        "write", "modify", "patch", "edit", "upsert",
    ],
    Capability.DELETE: [
        "delete_", "remove_", "drop_", "destroy_", "purge_",
        "truncate", "wipe",
    ],
    Capability.SEND_NOTIFY: [
        "send_", "notify_", "email_", "post_message", "alert_",
        "publish_", "broadcast",
        "send", "notify", "email", "sms", "message",
    ],
    Capability.EXECUTE: [
        "run_", "exec_", "execute_", "invoke_", "deploy_",
        "launch_", "start_", "trigger_",
        "execute", "invoke", "deploy", "spawn",
    ],
    Capability.ADMIN: [
        "configure_", "admin_", "manage_", "grant_", "revoke_",
        "assign_role", "set_permission",
        "admin", "config", "permission", "role", "policy",
    ],
}

DOMAIN_KEYWORDS: dict[SensitiveDomain, list[str]] = {
    SensitiveDomain.EMAIL: ["email", "smtp", "mailbox", "inbox", "sendgrid", "ses"],
    SensitiveDomain.TICKETING: ["ticket", "issue", "jira", "servicenow", "zendesk"],
    SensitiveDomain.SOURCE_CONTROL: [
        "repo", "repository", "branch", "commit", "git",
        "pull_request", "merge",
    ],
    SensitiveDomain.DATABASE: [
        "database", "db", "sql", "query", "table", "collection",
        "postgres", "mysql", "mongo", "redis", "dynamo",
    ],
    SensitiveDomain.CLOUD_INFRASTRUCTURE: [
        "aws", "azure", "gcp", "cloud", "vm", "instance",
        "cluster", "k8s", "kubernetes", "terraform", "lambda",
    ],
    SensitiveDomain.BILLING_PAYMENTS: [
        "billing", "payment", "invoice", "charge", "stripe",
        "subscription", "refund",
    ],
    SensitiveDomain.CRM_CUSTOMER_RECORDS: [
        "customer", "crm", "contact", "salesforce", "hubspot",
        "lead", "account",
    ],
    SensitiveDomain.IDENTITY_AUTH: [
        "auth", "oauth", "token", "identity", "iam", "saml",
        "sso", "credential", "login", "password", "secret",
    ],
    SensitiveDomain.FILE_STORAGE: [
        "storage", "s3", "blob", "bucket", "file", "drive",
        "upload", "download",
    ],
}
```

**Matching function:**

```python
def _match_capabilities(text: str) -> set[Capability]:
    result = set()
    for cap, keywords in CAPABILITY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                result.add(cap)
                break
    return result

def _match_domains(text: str) -> set[SensitiveDomain]:
    result = set()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                result.add(domain)
                break
    return result
```

**Batch interface (convenience):**

```python
def classify_all(changes: list[ToolChange]) -> list[ToolChange]:
    return [classify_tool_change(c) for c in changes]
```

---

### 4.5 scorer.py — Risk Scoring

**Purpose:** Compute a deterministic risk score from classified changes.

**Interface:**

```python
def score(
    diff: DiffResult,
    policy: Policy | None = None,
) -> ScoringResult:
    """
    Compute risk score from classified diff result.

    Args:
        diff: DiffResult with capabilities already populated.
        policy: Optional policy overrides.

    Returns:
        ScoringResult with total points, risk level, and breakdown.
    """
```

**Point table (constants):**

```python
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
```

**Algorithm:**

```python
def score(diff: DiffResult, policy: Policy | None = None) -> ScoringResult:
    points = 0
    breakdown = []
    ignore_desc = policy.options.ignore_description_only if policy else False

    for tc in diff.tool_changes:
        if tc.change_type == ChangeType.REMOVED:
            breakdown.append((f"Removed tool: {tc.tool_name}", 0))
            continue

        if tc.description_only and ignore_desc:
            breakdown.append((f"Description-only change: {tc.tool_name} (ignored)", 0))
            continue

        if tc.description_only and not ignore_desc:
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

    # Apply policy escalation rules
    if policy:
        risk_level = _apply_policy_escalation(risk_level, diff, policy)

    return ScoringResult(
        total_points=points,
        risk_level=risk_level,
        point_breakdown=breakdown,
    )
```

**Points → Risk mapping:**

```python
def _points_to_risk(points: int) -> RiskLevel:
    if points == 0:
        return RiskLevel.LOW
    elif points <= 3:
        return RiskLevel.MEDIUM
    elif points <= 6:
        return RiskLevel.HIGH
    else:
        return RiskLevel.CRITICAL
```

**Policy escalation:**

```python
def _apply_policy_escalation(
    current: RiskLevel, diff: DiffResult, policy: Policy
) -> RiskLevel:
    """Escalate risk level if any policy rule demands a higher floor."""
    RISK_ORDER = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2, RiskLevel.CRITICAL: 3}
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
```

---

### 4.6 recommender.py — Approval Recommendation

**Purpose:** Map `ScoringResult` to a final `Recommendation` with reason strings.

**Interface:**

```python
def recommend(
    scoring: ScoringResult,
    diff: DiffResult,
) -> tuple[Recommendation, list[str]]:
    """
    Returns:
        (recommendation, list_of_reason_strings)
    """
```

**Mapping:**

```python
RISK_TO_RECOMMENDATION = {
    RiskLevel.LOW: Recommendation.SAFE_TO_MERGE,
    RiskLevel.MEDIUM: Recommendation.REVIEW_RECOMMENDED,
    RiskLevel.HIGH: Recommendation.MANUAL_APPROVAL_REQUIRED,
    RiskLevel.CRITICAL: Recommendation.MANUAL_APPROVAL_REQUIRED,
}
```

**Reason generation:**

```python
def _build_reasons(scoring: ScoringResult, diff: DiffResult) -> list[str]:
    reasons = []

    # Collect unique capability reasons
    cap_set = set()
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

    # Scope reasons
    expansions = [sc for sc in diff.scope_changes if sc.is_expansion]
    if expansions:
        reasons.append("Expands authentication/authorization scope")

    # Domain reasons
    domain_set = set()
    for tc in diff.tool_changes:
        domain_set.update(tc.sensitive_domains)
    if domain_set:
        domain_names = ", ".join(sorted(d.value for d in domain_set))
        reasons.append(f"Affects sensitive systems: {domain_names}")

    # Fallback for safe
    if not reasons:
        reasons.append("No new capabilities or scope expansion detected")

    return reasons
```

---

### 4.7 summarizer.py — Plain-English Summary

**Purpose:** Generate a 2–5 sentence human-readable summary from the diff and recommendation.

**Interface:**

```python
def summarize(
    diff: DiffResult,
    scoring: ScoringResult,
    recommendation: Recommendation,
) -> str:
    """
    Generate a plain-English blast radius summary.

    Returns:
        A string of 2–5 sentences.
    """
```

**Algorithm — Template-based construction:**

The summarizer builds sentences from structured data rather than using an LLM.

```python
def summarize(diff, scoring, recommendation):
    sentences = []

    # Sentence 1: What changed
    added = [tc for tc in diff.tool_changes if tc.change_type == ChangeType.ADDED]
    removed = [tc for tc in diff.tool_changes if tc.change_type == ChangeType.REMOVED]
    modified = [tc for tc in diff.tool_changes if tc.change_type == ChangeType.MODIFIED]

    parts = []
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

    # Sentence 2: Notable capabilities
    write_tools = [tc for tc in diff.tool_changes if Capability.WRITE in tc.capabilities]
    delete_tools = [tc for tc in diff.tool_changes if Capability.DELETE in tc.capabilities]
    send_tools = [tc for tc in diff.tool_changes if Capability.SEND_NOTIFY in tc.capabilities]
    exec_tools = [tc for tc in diff.tool_changes if Capability.EXECUTE in tc.capabilities]

    notable = []
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

    # Sentence 3: Scope changes
    expansions = [sc for sc in diff.scope_changes if sc.is_expansion]
    if expansions:
        scope_desc = ", ".join(
            f"{sc.scope_name} ({sc.old_access} → {sc.new_access})" for sc in expansions
        )
        sentences.append(f"OAuth/permission scope expands: {scope_desc}.")

    # Sentence 4: Sensitive domains
    all_domains = set()
    for tc in diff.tool_changes:
        all_domains.update(tc.sensitive_domains)
    if all_domains:
        domain_names = ", ".join(sorted(d.value for d in all_domains))
        sentences.append(f"This affects sensitive systems: {domain_names}.")

    # Sentence 5: Conclusion tied to recommendation
    if recommendation == Recommendation.MANUAL_APPROVAL_REQUIRED:
        sentences.append("Manual approval is required due to the scope of capability expansion.")
    elif recommendation == Recommendation.REVIEW_RECOMMENDED:
        sentences.append("Reviewer attention is recommended before merging.")
    else:
        sentences.append("No significant capability expansion was detected.")

    return " ".join(sentences[:5])


def _pluralize(count: int, word: str) -> str:
    return f"{count} {word}{'s' if count != 1 else ''}"
```

---

### 4.8 policy.py — Policy File Loading

**Purpose:** Load and parse the `.mcpreviewer.yml` file from a repo.

**Interface:**

```python
def load_policy(content: str | None) -> Policy:
    """
    Parse policy file content into a Policy object.

    Args:
        content: Raw YAML string, or None if file not found.

    Returns:
        Policy object (defaults if content is None or malformed).
    """
```

**Implementation:**

```python
import yaml
import logging

logger = logging.getLogger(__name__)

POLICY_FILE_NAMES = [".mcpreviewer.yml", ".mcpreviewer.yaml"]

def load_policy(content: str | None) -> Policy:
    if content is None:
        return Policy()

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as e:
        logger.warning(f"Malformed policy file, using defaults: {e}")
        return Policy()

    if not isinstance(data, dict):
        logger.warning("Policy file is not a mapping, using defaults")
        return Policy()

    return _parse_policy(data)


def _parse_policy(data: dict) -> Policy:
    policy = Policy()
    policy.version = data.get("version", 1)

    # Patterns
    raw_patterns = data.get("patterns", [])
    if isinstance(raw_patterns, list):
        policy.patterns = [str(p) for p in raw_patterns]

    # Rules
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

    # Options
    raw_options = data.get("options", {})
    if isinstance(raw_options, dict):
        policy.options.ignore_description_only = bool(
            raw_options.get("ignore_description_only", False)
        )
        threshold = raw_options.get("fail_ci_threshold")
        if threshold:
            parsed = _safe_enum(RiskLevel, threshold)
            if parsed:
                policy.options.fail_ci_threshold = parsed

    return policy


def _safe_enum(enum_cls, value):
    """Case-insensitive enum lookup. Returns None on failure."""
    if value is None:
        return None
    value_lower = str(value).lower()
    for member in enum_cls:
        if member.value.lower() == value_lower or member.name.lower() == value_lower:
            return member
    logger.warning(f"Unknown {enum_cls.__name__} value: {value}")
    return None
```

---

### 4.9 pipeline.py — Orchestrator

**Purpose:** Wire all core modules together. Single entry point used by both the GitHub App and CLI.

**Interface:**

```python
def analyze(
    changed_files: list[str],
    file_contents: dict[str, tuple[str | None, str | None]],
    policy_content: str | None = None,
) -> ReviewResult | None:
    """
    Run the full analysis pipeline.

    Args:
        changed_files: List of all changed file paths in the PR.
        file_contents: Mapping of file_path → (base_content, head_content).
                       base_content is None if file is new.
                       head_content is None if file is deleted.
        policy_content: Raw content of the repo policy file, or None.

    Returns:
        ReviewResult, or None if no MCP files were found.
    """
```

**Implementation:**

```python
def analyze(changed_files, file_contents, policy_content=None):
    # 1. Load policy
    policy = load_policy(policy_content)

    # 2. Detect MCP files
    patterns = policy.patterns if policy.patterns else None
    mcp_files = detect_mcp_files(changed_files, patterns)

    if not mcp_files:
        return None  # No MCP files → no analysis

    # 3. Parse and diff each file
    diffs = []
    for file_path in mcp_files:
        base_content, head_content = file_contents.get(file_path, (None, None))

        base_manifest = None
        head_manifest = None

        if base_content is not None:
            try:
                base_manifest = parse_mcp_file(file_path, base_content)
            except ParseError:
                logger.warning(f"Could not parse base version of {file_path}")

        if head_content is not None:
            try:
                head_manifest = parse_mcp_file(file_path, head_content)
            except ParseError:
                logger.warning(f"Could not parse head version of {file_path}")

        diff = diff_manifests(base_manifest, head_manifest)
        diff.analyzed_files = [file_path]
        diffs.append(diff)

    # 4. Merge all diffs
    merged = merge_diffs(diffs)

    # 5. Classify
    merged.tool_changes = classify_all(merged.tool_changes)

    # 6. Score
    scoring = score(merged, policy)

    # 7. Recommend
    recommendation, reasons = recommend(scoring, merged)

    # 8. Summarize
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
```

---

## 5. GitHub App — Detailed Design

### 5.1 app/config.py — Settings

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    github_app_id: int
    github_private_key: str          # PEM-encoded, multi-line
    github_webhook_secret: str
    log_level: str = "INFO"

    class Config:
        env_prefix = ""
        env_file = ".env"
```

### 5.2 app/main.py — FastAPI Application

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
import logging

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=settings.log_level)
    yield

app = FastAPI(title="MCP Reviewer", lifespan=lifespan)

@app.get("/")
async def health():
    return {"status": "ok"}

@app.post("/webhook")
async def webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    event = request.headers.get("X-GitHub-Event", "")

    if not verify_signature(body, signature, settings.github_webhook_secret):
        return Response(status_code=401, content="Invalid signature")

    if event != "pull_request":
        return Response(status_code=200, content="Ignored event")

    payload = await request.json()
    action = payload.get("action")

    if action not in ("opened", "synchronize", "reopened"):
        return Response(status_code=200, content="Ignored action")

    # Process in background to respond quickly
    import asyncio
    asyncio.create_task(_handle_pr(payload))

    return Response(status_code=200, content="Processing")
```

### 5.3 app/webhook_handler.py — Signature Verification & Orchestration

**Signature verification:**

```python
import hashlib
import hmac

def verify_signature(payload_body: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    if not signature.startswith("sha256="):
        return False
    expected = hmac.new(
        secret.encode("utf-8"),
        payload_body,
        hashlib.sha256,
    ).hexdigest()
    received = signature[len("sha256="):]
    return hmac.compare_digest(expected, received)
```

**PR handler orchestration:**

```python
async def _handle_pr(payload: dict):
    """Full PR analysis orchestration."""
    try:
        installation_id = payload["installation"]["id"]
        repo_full_name = payload["repository"]["full_name"]
        pr_number = payload["pull_request"]["number"]
        base_sha = payload["pull_request"]["base"]["sha"]
        head_sha = payload["pull_request"]["head"]["sha"]

        client = GitHubClient(settings, installation_id)

        # 1. Get changed files
        changed_files = await client.get_pr_files(repo_full_name, pr_number)

        # 2. Fetch base and head content for each file
        file_contents = {}
        for file_path in changed_files:
            base_content = await client.get_file_content(
                repo_full_name, file_path, base_sha
            )
            head_content = await client.get_file_content(
                repo_full_name, file_path, head_sha
            )
            file_contents[file_path] = (base_content, head_content)

        # 3. Fetch policy file
        policy_content = await client.get_file_content(
            repo_full_name, ".mcpreviewer.yml", head_sha
        )
        if policy_content is None:
            policy_content = await client.get_file_content(
                repo_full_name, ".mcpreviewer.yaml", head_sha
            )

        # 4. Run analysis
        result = analyze(changed_files, file_contents, policy_content)

        # 5. Post or update comment
        if result is not None:
            comment_body = render_comment(result)
            await client.upsert_pr_comment(repo_full_name, pr_number, comment_body)
        else:
            # No MCP files found — optionally delete stale comment
            await client.delete_bot_comment(repo_full_name, pr_number)

    except Exception:
        logger.exception(f"Error processing PR #{pr_number} in {repo_full_name}")
```

### 5.4 app/github_client.py — GitHub API Wrapper

```python
import jwt
import time
import httpx

class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, settings: Settings, installation_id: int):
        self._settings = settings
        self._installation_id = installation_id
        self._token: str | None = None
        self._token_expires: float = 0

    async def _get_token(self) -> str:
        """Get or refresh the installation access token."""
        if self._token and time.time() < self._token_expires - 60:
            return self._token

        # Generate JWT
        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + (10 * 60),
            "iss": self._settings.github_app_id,
        }
        encoded = jwt.encode(payload, self._settings.github_private_key, algorithm="RS256")

        # Exchange JWT for installation token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.BASE_URL}/app/installations/{self._installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {encoded}",
                    "Accept": "application/vnd.github+json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["token"]
            self._token_expires = time.time() + 3600
            return self._token

    async def _headers(self) -> dict:
        token = await self._get_token()
        return {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        }

    async def get_pr_files(self, repo: str, pr_number: int) -> list[str]:
        """Return list of file paths changed in the PR."""
        headers = await self._headers()
        files = []
        page = 1
        async with httpx.AsyncClient() as client:
            while True:
                resp = await client.get(
                    f"{self.BASE_URL}/repos/{repo}/pulls/{pr_number}/files",
                    headers=headers,
                    params={"per_page": 100, "page": page},
                )
                resp.raise_for_status()
                data = resp.json()
                if not data:
                    break
                files.extend(f["filename"] for f in data)
                page += 1
        return files

    async def get_file_content(
        self, repo: str, path: str, ref: str
    ) -> str | None:
        """Fetch file content at a specific ref. Returns None if not found."""
        headers = await self._headers()
        headers["Accept"] = "application/vnd.github.raw+json"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}/repos/{repo}/contents/{path}",
                headers=headers,
                params={"ref": ref},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text

    async def upsert_pr_comment(
        self, repo: str, pr_number: int, body: str
    ):
        """Create or update the bot's PR comment."""
        headers = await self._headers()
        marker = "<!-- mcpreviewer-bot -->"
        body_with_marker = f"{marker}\n{body}"

        async with httpx.AsyncClient() as client:
            # Search for existing comment with marker
            resp = await client.get(
                f"{self.BASE_URL}/repos/{repo}/issues/{pr_number}/comments",
                headers=headers,
                params={"per_page": 100},
            )
            resp.raise_for_status()
            comments = resp.json()

            existing_id = None
            for c in comments:
                if marker in (c.get("body") or ""):
                    existing_id = c["id"]
                    break

            if existing_id:
                # Update existing
                resp = await client.patch(
                    f"{self.BASE_URL}/repos/{repo}/issues/comments/{existing_id}",
                    headers=headers,
                    json={"body": body_with_marker},
                )
            else:
                # Create new
                resp = await client.post(
                    f"{self.BASE_URL}/repos/{repo}/issues/{pr_number}/comments",
                    headers=headers,
                    json={"body": body_with_marker},
                )
            resp.raise_for_status()

    async def delete_bot_comment(self, repo: str, pr_number: int):
        """Delete the bot's existing comment if present."""
        headers = await self._headers()
        marker = "<!-- mcpreviewer-bot -->"

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}/repos/{repo}/issues/{pr_number}/comments",
                headers=headers,
                params={"per_page": 100},
            )
            resp.raise_for_status()
            for c in resp.json():
                if marker in (c.get("body") or ""):
                    await client.delete(
                        f"{self.BASE_URL}/repos/{repo}/issues/comments/{c['id']}",
                        headers=headers,
                    )
                    break
```

**Hidden marker strategy:** The comment includes `<!-- mcpreviewer-bot -->` as an HTML comment to identify the bot's own comments for update/delete operations.

---

## 6. CLI — Detailed Design

### 6.1 cli/main.py

```python
import click
import json
import subprocess
import sys
from pathlib import Path

@click.command()
@click.option("--base", default="origin/main", help="Base git ref")
@click.option("--head", default="HEAD", help="Head git ref")
@click.option("--repo", default=".", type=click.Path(exists=True), help="Repo path")
@click.option("--format", "output_format", default="text",
              type=click.Choice(["text", "json"]))
@click.option("--policy", default=None, type=click.Path(), help="Policy file path")
@click.option("--fail-on", default=None,
              type=click.Choice(["low", "medium", "high", "critical"]))
def analyze_cmd(base, head, repo, output_format, policy, fail_on):
    """Analyze MCP changes between two git refs."""
    repo_path = Path(repo).resolve()

    # 1. Get changed files via git diff
    changed_files = _git_changed_files(repo_path, base, head)
    if not changed_files:
        click.echo("No changed files found.")
        sys.exit(0)

    # 2. Read file contents at base and head
    file_contents = {}
    for fp in changed_files:
        base_content = _git_show(repo_path, base, fp)
        head_content = _git_show(repo_path, head, fp)
        file_contents[fp] = (base_content, head_content)

    # 3. Load policy
    policy_content = None
    if policy:
        policy_path = Path(policy)
        if policy_path.exists():
            policy_content = policy_path.read_text(encoding="utf-8")
    else:
        for name in POLICY_FILE_NAMES:
            p = repo_path / name
            if p.exists():
                policy_content = p.read_text(encoding="utf-8")
                break

    # 4. Run pipeline
    result = pipeline_analyze(changed_files, file_contents, policy_content)

    if result is None:
        click.echo("No MCP-related changes detected.")
        sys.exit(0)

    # 5. Output
    if output_format == "json":
        click.echo(json.dumps(_result_to_dict(result), indent=2))
    else:
        click.echo(_render_text(result))

    # 6. Exit code
    if fail_on:
        threshold = _parse_risk_level(fail_on)
        if _risk_meets_threshold(result.risk_level, threshold):
            sys.exit(2 if result.recommendation == Recommendation.MANUAL_APPROVAL_REQUIRED else 1)

    sys.exit(0)


def _git_changed_files(repo: Path, base: str, head: str) -> list[str]:
    """Get list of changed files between two refs."""
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # Fallback: try without triple-dot (for cases where base is not a branch)
        result = subprocess.run(
            ["git", "diff", "--name-only", base, head],
            cwd=repo,
            capture_output=True,
            text=True,
        )
    return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]


def _git_show(repo: Path, ref: str, file_path: str) -> str | None:
    """Get file content at a specific ref. Returns None if file doesn't exist."""
    result = subprocess.run(
        ["git", "show", f"{ref}:{file_path}"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return result.stdout
```

### 6.2 CLI Text Output Format

```python
def _render_text(result: ReviewResult) -> str:
    lines = []
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
```

### 6.3 CLI JSON Output Schema

```json
{
  "recommendation": "Manual approval required",
  "risk_level": "High",
  "total_points": 5,
  "summary": "This PR adds 1 new tool...",
  "tool_changes": [
    {
      "change_type": "added",
      "tool_name": "create_ticket",
      "capabilities": ["Write", "Sensitive System Access"],
      "sensitive_domains": ["Ticketing"],
      "description_only": false
    }
  ],
  "scope_changes": [
    {
      "scope_name": "api",
      "old_access": "read",
      "new_access": "read/write",
      "is_expansion": true
    }
  ],
  "reasons": [
    "Introduces write access",
    "Affects sensitive systems: Ticketing"
  ],
  "analyzed_files": ["mcp.json"]
}
```

---

## 7. Policy File — Detailed Specification

### 7.1 File Location

Searched in order from repo root:
1. `.mcpreviewer.yml`
2. `.mcpreviewer.yaml`

If neither exists, defaults are used.

### 7.2 Full Schema

```yaml
# .mcpreviewer.yml
version: 1                          # Required. Only version 1 supported in V1.

patterns:                           # Optional. Override MCP file detection patterns.
  - "**/mcp.json"
  - "**/tools/**"

rules:                              # Optional. Escalation rules.
  - capability: Delete              # Capability name (case-insensitive)
    min_risk: Critical              # Floor risk level when this capability is present
  - capability: Send
    min_risk: High
  - domain: Email                   # Sensitive domain name (case-insensitive)
    min_risk: High
  - domain: Billing
    min_risk: Critical

options:                            # Optional. Global behavior flags.
  ignore_description_only: true     # Skip description-only changes in scoring
  fail_ci_threshold: High           # CLI --fail-on default when not specified
```

### 7.3 Validation Rules

| Field | Type | Default | Notes |
|---|---|---|---|
| `version` | int | 1 | Must be 1. Other values → warning, use defaults. |
| `patterns` | list[str] | `[]` (use built-in) | Each entry is a glob string. |
| `rules` | list[object] | `[]` | Each must have at least `capability` or `domain`. |
| `rules[].capability` | string | - | Must match a `Capability` enum value. |
| `rules[].domain` | string | - | Must match a `SensitiveDomain` enum value. |
| `rules[].min_risk` | string | `"High"` | Must match a `RiskLevel` enum value. |
| `options.ignore_description_only` | bool | `false` | - |
| `options.fail_ci_threshold` | string | `"High"` | Must match a `RiskLevel` enum value. |

---

## 8. PR Comment Rendering

### 8.1 comment_renderer.py

```python
def render_comment(result: ReviewResult) -> str:
    """Render the PR comment markdown from a ReviewResult."""
    lines = []
    lines.append("## MCP Reviewer")
    lines.append("")
    lines.append(f"**Recommendation:** {result.recommendation.value}  ")
    lines.append(f"**Risk:** {result.risk_level.value}")
    lines.append("")
    lines.append(result.summary)
    lines.append("")

    # Key Changes table
    if result.tool_changes or result.scope_changes:
        lines.append("### Key Changes")
        lines.append("")
        lines.append("| Change | Detail |")
        lines.append("|---|---|")

        for tc in result.tool_changes:
            action = tc.change_type.value.title()
            lines.append(f"| {action} tool | `{tc.tool_name}` |")

            for cap in tc.capabilities:
                if cap != Capability.READ and cap != Capability.SENSITIVE_SYSTEM_ACCESS:
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

    # Reasons
    if result.reasons:
        lines.append("### Reasons")
        lines.append("")
        for r in result.reasons:
            lines.append(f"- {r}")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append("*MCP Reviewer v1*")

    return "\n".join(lines)
```

### 8.2 Example Rendered Output

```markdown
## MCP Reviewer

**Recommendation:** Manual approval required  
**Risk:** High

This PR adds 1 new tool in the MCP configuration. Among the changes, 1 tool can write data. OAuth/permission scope expands: api (read → read/write). This affects sensitive systems: Ticketing. Manual approval is required due to the scope of capability expansion.

### Key Changes

| Change | Detail |
|---|---|
| Added tool | `create_ticket` |
| New capability | Write |
| Sensitive domain | Ticketing |
| Scope change | `api`: `read` → `read/write` |

### Reasons

- Introduces write access
- Expands authentication/authorization scope
- Affects sensitive systems: Ticketing

---
*MCP Reviewer v1*
```

---

## 9. Error Handling

### 9.1 Error Strategy

| Scenario | Behavior |
|---|---|
| Webhook signature invalid | Return 401. Do not process. |
| GitHub API rate limited | Log warning. Retry with exponential backoff (max 3 retries). |
| GitHub API 500 | Log error. Retry once. If still failing, skip this event. |
| MCP file parse error (base) | Log warning. Treat base as empty (all tools are "new"). |
| MCP file parse error (head) | Log warning. Treat head as empty (all tools are "removed"). Conservative. |
| Both base and head parse fail | Log error. Post a comment saying analysis could not be completed. |
| Policy file malformed | Log warning. Use default policy. |
| Unknown tool capability | Mark as `Unknown`. Score conservatively (+2 points). |
| Exception in pipeline | Log full traceback. Do not post partial results. |
| CLI git command fails | Print error to stderr. Exit code 3. |

### 9.2 Custom Exception Classes

```python
class McpReviewerError(Exception):
    """Base exception."""

class ParseError(McpReviewerError):
    """Failed to parse an MCP file."""
    def __init__(self, file_path: str, reason: str):
        self.file_path = file_path
        self.reason = reason
        super().__init__(f"Parse error in {file_path}: {reason}")

class GitHubAPIError(McpReviewerError):
    """GitHub API call failed."""
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"GitHub API error {status_code}: {message}")
```

---

## 10. Configuration & Environment

### 10.1 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GITHUB_APP_ID` | Yes | GitHub App ID (integer) |
| `GITHUB_PRIVATE_KEY` | Yes | PEM-encoded private key (multi-line string) |
| `GITHUB_WEBHOOK_SECRET` | Yes | Webhook secret for HMAC verification |
| `LOG_LEVEL` | No | Logging level (default: `INFO`) |
| `PORT` | No | Server port (default: `8000`) |

### 10.2 Local Development

Create a `.env` file (gitignored):

```
GITHUB_APP_ID=12345
GITHUB_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----"
GITHUB_WEBHOOK_SECRET=your_secret_here
LOG_LEVEL=DEBUG
```

---

## 11. Logging

### 11.1 Format

```
%(asctime)s %(levelname)s %(name)s %(message)s
```

All logs go to stdout. The hosting platform captures them.

### 11.2 Log Points

| Module | Level | Event |
|---|---|---|
| webhook_handler | INFO | PR event received: `{repo}#{pr_number} ({action})` |
| webhook_handler | INFO | Analysis complete: `{recommendation}` for `{repo}#{pr_number}` |
| webhook_handler | WARNING | No MCP files found for `{repo}#{pr_number}` |
| webhook_handler | ERROR | Processing failed for `{repo}#{pr_number}` |
| github_client | DEBUG | API call: `{method} {url}` |
| github_client | WARNING | Rate limit approaching: `{remaining}/{limit}` |
| parser | WARNING | Parse error in `{file_path}`: `{reason}` |
| policy | WARNING | Malformed policy file, using defaults |
| detector | DEBUG | Detected MCP files: `{count}` from `{total}` changed files |
| scorer | DEBUG | Scoring: `{total_points}` points → `{risk_level}` |

---

## 12. Testing — Detailed Plan

### 12.1 Test Fixtures

Located in `tests/fixtures/`. Each fixture represents a realistic MCP config scenario.

| Fixture | Purpose |
|---|---|
| `mcp_simple.json` | Single read-only tool. Expect: Low risk, Safe to merge. |
| `mcp_write_tool.json` | One read tool + one write tool. Expect: Medium risk. |
| `mcp_delete_tool.yaml` | Tool with delete capability. Expect: High risk. |
| `mcp_scope_expansion.json` | OAuth scope goes from read to read/write. Expect: Medium+. |
| `mcp_unknown_tool.json` | Tool with no recognizable capability keywords. Expect: Unknown, +2 pts. |
| `mcp_description_only.json` | Only tool description differs. Expect: 0 points (with ignore flag). |
| `mcp_multi_tool.json` | Multiple tools with mixed capabilities. Tests aggregation. |
| `mcp_sensitive_domain.json` | Tool targeting billing system. Expect: Sensitive System Access. |
| `mcp_malformed.json` | Invalid JSON. Expect: ParseError, conservative handling. |
| `mcp_empty.json` | Valid JSON, no tools. Expect: empty manifest, no changes. |
| `mcp_annotations.json` | Tool with `destructiveHint: true`. Expect: Delete classification. |
| `mcp_servers_format.json` | mcpServers config style. Expect: server name extraction. |
| `policy_default.yml` | No overrides. Tests default behavior. |
| `policy_strict.yml` | Delete → Critical, Email → High. Tests escalation. |
| `policy_malformed.yml` | Bad YAML. Tests fallback to defaults. |
| `webhook_pr_opened.json` | Recorded GitHub PR webhook payload. |

### 12.2 Unit Test Specifications

**test_detector.py:**
- `test_matches_mcp_json` — `mcp.json` matches default patterns.
- `test_matches_nested_path` — `services/auth/mcp.yaml` matches `**/mcp.yaml`.
- `test_ignores_unrelated` — `src/app.py` does not match.
- `test_empty_input` — empty list returns empty list.
- `test_custom_patterns` — custom patterns override defaults.

**test_parser.py:**
- `test_parse_json_tools` — parses tool list from JSON.
- `test_parse_yaml_tools` — parses tool list from YAML.
- `test_parse_scopes` — extracts scopes from various formats.
- `test_parse_mcpservers_format` — handles mcpServers config style.
- `test_parse_annotations` — preserves tool annotations.
- `test_parse_empty_file` — returns empty manifest.
- `test_parse_malformed` — raises ParseError.
- `test_parse_missing_keys` — gracefully skips missing keys.

**test_differ.py:**
- `test_added_tool` — new tool detected as ADDED.
- `test_removed_tool` — missing tool detected as REMOVED.
- `test_modified_tool` — changed tool detected as MODIFIED.
- `test_description_only_change` — `description_only` flag set correctly.
- `test_scope_expansion` — scope change from read to read/write is expansion.
- `test_scope_no_change` — same scope not flagged.
- `test_new_file` — base is None, all tools are ADDED.
- `test_deleted_file` — head is None, all tools are REMOVED.
- `test_no_changes` — identical manifests produce empty diff.

**test_classifier.py:**
- `test_read_tool` — `get_users` classified as Read.
- `test_write_tool` — `create_ticket` classified as Write.
- `test_delete_tool` — `delete_record` classified as Delete.
- `test_send_tool` — `send_email` classified as Send/Notify.
- `test_execute_tool` — `run_query` classified as Execute.
- `test_admin_tool` — `configure_permissions` classified as Admin.
- `test_unknown_tool` — `do_something` classified as Unknown.
- `test_sensitive_domain_email` — tool mentioning "smtp" gets Email domain.
- `test_sensitive_domain_billing` — tool mentioning "stripe" gets Billing domain.
- `test_annotation_destructive` — `destructiveHint: true` → Delete.
- `test_annotation_readonly` — `readOnlyHint: true` → Read.
- `test_multi_capability` — tool matching write + delete gets both.

**test_scorer.py:**
- `test_read_only_zero_points` — only Read tools → 0 points, Low.
- `test_write_two_points` — one Write tool → 2 points, Medium.
- `test_delete_three_points` — one Delete tool → 3 points, Medium.
- `test_combined_high` — Write + Delete → 5 points, High.
- `test_scope_expansion_points` — scope expansion → +3 points.
- `test_critical_threshold` — 7+ points → Critical.
- `test_policy_escalation` — Delete with policy floor Critical → Critical even if points low.
- `test_ignore_description_only` — with policy flag, description-only → 0 points.

**test_recommender.py:**
- `test_low_safe` — Low → Safe to merge.
- `test_medium_review` — Medium → Review recommended.
- `test_high_manual` — High → Manual approval required.
- `test_critical_manual` — Critical → Manual approval required.
- `test_reasons_include_capabilities` — reasons list non-read capabilities.
- `test_reasons_include_domains` — reasons mention sensitive domains.

**test_summarizer.py:**
- `test_summary_length` — output is 2–5 sentences.
- `test_summary_mentions_added_tools` — mentions new tool count.
- `test_summary_mentions_capabilities` — mentions write/delete if present.
- `test_summary_mentions_domains` — mentions sensitive domains.
- `test_summary_safe_conclusion` — safe PR has appropriate conclusion.

**test_policy.py:**
- `test_load_valid_policy` — parses all fields.
- `test_load_missing_file` — None input returns defaults.
- `test_load_malformed_yaml` — returns defaults, logs warning.
- `test_case_insensitive_enum` — "delete" matches Delete.
- `test_unknown_enum_value` — ignores unknown, logs warning.

**test_pipeline.py:**
- `test_full_pipeline_safe` — read-only change → Safe to merge.
- `test_full_pipeline_high` — write + sensitive domain → Manual approval required.
- `test_no_mcp_files` — returns None.
- `test_pipeline_with_policy` — policy escalation applied.

### 12.3 Integration Tests

**test_webhook_handler.py:**
- `test_valid_signature_accepted` — valid HMAC passes.
- `test_invalid_signature_rejected` — invalid HMAC returns 401.
- `test_non_pr_event_ignored` — push event returns 200 without processing.
- `test_irrelevant_action_ignored` — `closed` action not processed.

**test_cli.py:**
- `test_cli_text_output` — CLI produces readable text for a sample diff.
- `test_cli_json_output` — CLI produces valid JSON matching schema.
- `test_cli_exit_code_safe` — exit 0 for safe PR.
- `test_cli_exit_code_fail_on` — exit 1/2 when `--fail-on` threshold exceeded.
- `test_cli_no_mcp_files` — prints message, exit 0.

---

## 13. Packaging & Deployment

### 13.1 pyproject.toml

```toml
[project]
name = "mcpreviewer"
version = "0.1.0"
description = "MCP Reviewer — PR review bot for MCP capability changes"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "httpx>=0.27",
    "PyJWT[crypto]>=2.8",
    "PyYAML>=6.0",
    "click>=8.1",
    "pydantic-settings>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx",  # for TestClient
    "pip-audit",
]

[project.scripts]
mcpreviewer = "mcpreviewer.cli.main:analyze_cmd"
```

### 13.2 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "mcpreviewer.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 13.3 Deployment Checklist

1. Build Docker image.
2. Deploy to hosting platform (Fly.io / Railway).
3. Set environment variables (`GITHUB_APP_ID`, `GITHUB_PRIVATE_KEY`, `GITHUB_WEBHOOK_SECRET`).
4. Register GitHub App on github.com/settings/apps.
5. Set webhook URL to `https://<your-domain>/webhook`.
6. Set webhook secret to match `GITHUB_WEBHOOK_SECRET`.
7. Set permissions: `pull_requests: write`, `contents: read`.
8. Subscribe to `pull_request` events.
9. Install the app on target repositories.
10. Open a test PR with MCP file changes and verify the comment.

---

## 14. API Reference (Internal)

Summary of all public module interfaces for developer reference.

| Module | Function | Input | Output |
|---|---|---|---|
| `core.detector` | `detect_mcp_files(changed_files, patterns?)` | `list[str], list[str]\|None` | `list[str]` |
| `core.parser` | `parse_mcp_file(file_path, content)` | `str, str` | `McpManifest` |
| `core.differ` | `diff_manifests(base?, head?)` | `McpManifest\|None, McpManifest\|None` | `DiffResult` |
| `core.differ` | `merge_diffs(diffs)` | `list[DiffResult]` | `DiffResult` |
| `core.classifier` | `classify_tool_change(change)` | `ToolChange` | `ToolChange` |
| `core.classifier` | `classify_all(changes)` | `list[ToolChange]` | `list[ToolChange]` |
| `core.scorer` | `score(diff, policy?)` | `DiffResult, Policy\|None` | `ScoringResult` |
| `core.recommender` | `recommend(scoring, diff)` | `ScoringResult, DiffResult` | `(Recommendation, list[str])` |
| `core.summarizer` | `summarize(diff, scoring, recommendation)` | `DiffResult, ScoringResult, Recommendation` | `str` |
| `core.policy` | `load_policy(content?)` | `str\|None` | `Policy` |
| `core.pipeline` | `analyze(changed_files, file_contents, policy_content?)` | `list[str], dict, str\|None` | `ReviewResult\|None` |
| `app.github_client` | `GitHubClient.get_pr_files(repo, pr)` | `str, int` | `list[str]` |
| `app.github_client` | `GitHubClient.get_file_content(repo, path, ref)` | `str, str, str` | `str\|None` |
| `app.github_client` | `GitHubClient.upsert_pr_comment(repo, pr, body)` | `str, int, str` | `None` |
| `app.webhook_handler` | `verify_signature(body, signature, secret)` | `bytes, str, str` | `bool` |
