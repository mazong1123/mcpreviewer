from __future__ import annotations

from dataclasses import dataclass, field
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


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str = ""
    input_schema: dict = field(default_factory=dict)
    annotations: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ScopeDefinition:
    name: str
    access: str  # e.g. "read", "read/write", "admin"


@dataclass(frozen=True)
class McpManifest:
    file_path: str
    tools: list[ToolDefinition] = field(default_factory=list)
    scopes: list[ScopeDefinition] = field(default_factory=list)
    raw: dict = field(default_factory=dict)


@dataclass
class ToolChange:
    change_type: ChangeType
    tool_name: str
    old_tool: ToolDefinition | None = None
    new_tool: ToolDefinition | None = None
    capabilities: list[Capability] = field(default_factory=list)
    sensitive_domains: list[SensitiveDomain] = field(default_factory=list)
    description_only: bool = False


@dataclass
class ScopeChange:
    scope_name: str
    old_access: str | None = None
    new_access: str | None = None
    is_expansion: bool = False


@dataclass
class DiffResult:
    tool_changes: list[ToolChange] = field(default_factory=list)
    scope_changes: list[ScopeChange] = field(default_factory=list)
    analyzed_files: list[str] = field(default_factory=list)


@dataclass
class ScoringResult:
    total_points: int
    risk_level: RiskLevel
    point_breakdown: list[tuple[str, int]]


@dataclass
class ReviewResult:
    recommendation: Recommendation
    risk_level: RiskLevel
    summary: str
    tool_changes: list[ToolChange]
    scope_changes: list[ScopeChange]
    reasons: list[str]
    analyzed_files: list[str]
    total_points: int


# ---------------------------------------------------------------------------
# Policy models
# ---------------------------------------------------------------------------

@dataclass
class PolicyRule:
    capability: Capability | None = None
    domain: SensitiveDomain | None = None
    min_risk: RiskLevel = RiskLevel.HIGH


@dataclass
class PolicyOptions:
    ignore_description_only: bool = False
    fail_ci_threshold: RiskLevel = RiskLevel.HIGH


@dataclass
class Policy:
    version: int = 1
    patterns: list[str] = field(default_factory=list)
    rules: list[PolicyRule] = field(default_factory=list)
    options: PolicyOptions = field(default_factory=PolicyOptions)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class McpReviewerError(Exception):
    pass


class ParseError(McpReviewerError):
    def __init__(self, file_path: str, reason: str):
        self.file_path = file_path
        self.reason = reason
        super().__init__(f"Parse error in {file_path}: {reason}")


class GitHubAPIError(McpReviewerError):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(f"GitHub API error {status_code}: {message}")
