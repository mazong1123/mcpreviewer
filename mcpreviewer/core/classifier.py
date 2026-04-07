from __future__ import annotations

from mcpreviewer.models.types import (
    Capability,
    SensitiveDomain,
    ToolChange,
)

# ------------------------------------------------------------------
# Keyword tables
# ------------------------------------------------------------------

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
        "truncate", "wipe", "delete", "remove",
    ],
    Capability.SEND_NOTIFY: [
        "send_", "notify_", "email_", "post_message", "alert_",
        "publish_", "broadcast",
        "send ", "notify ", " email", " sms", " message",
    ],
    Capability.EXECUTE: [
        "run_", "exec_", "execute_", "invoke_", "deploy_",
        "launch_", "start_", "trigger_",
        "execute", "executor", "invoke", "deploy", "spawn",
        "shell", "sudo", "bash", "powershell", "cmd.exe",
    ],
    Capability.ADMIN: [
        "configure_", "admin_", "manage_", "grant_", "revoke_",
        "assign_role", "set_permission",
        "admin", "config", "permission", "role", "policy",
    ],
}

DOMAIN_KEYWORDS: dict[SensitiveDomain, list[str]] = {
    SensitiveDomain.EMAIL: ["email", "smtp", "mailbox", "inbox", "sendgrid", "ses "],
    SensitiveDomain.TICKETING: ["ticket", "issue", "jira", "servicenow", "zendesk"],
    SensitiveDomain.SOURCE_CONTROL: [
        "repo", "repository", "branch", "commit", "git",
        "pull_request", "merge_request",
    ],
    SensitiveDomain.DATABASE: [
        "database", " db ", "_db_", "sql", "query", "table", "collection",
        "postgres", "mysql", "mongo", "redis", "dynamo",
    ],
    SensitiveDomain.CLOUD_INFRASTRUCTURE: [
        "aws", "azure", "gcp", "cloud", " vm ", "instance",
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
        "storage", " s3 ", "blob", "bucket", "file_upload",
        "drive", "upload", "download",
    ],
}


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def classify_tool_change(change: ToolChange) -> ToolChange:
    """Populate *capabilities* and *sensitive_domains* on *change*."""
    tool = change.new_tool or change.old_tool
    if tool is None:
        return change

    text = f" {tool.name} {tool.description} ".lower()
    caps: set[Capability] = set()
    domains: set[SensitiveDomain] = set()

    # 1. Annotations
    if tool.annotations:
        if tool.annotations.get("readOnlyHint") is True:
            caps.add(Capability.READ)
        if tool.annotations.get("destructiveHint") is True:
            caps.add(Capability.DELETE)

    # 2. Keywords
    caps |= _match_capabilities(text)
    domains |= _match_domains(text)

    if domains:
        caps.add(Capability.SENSITIVE_SYSTEM_ACCESS)

    # 3. Fallback
    if not caps:
        caps.add(Capability.UNKNOWN)

    change.capabilities = sorted(caps, key=lambda c: c.value)
    change.sensitive_domains = sorted(domains, key=lambda d: d.value)
    return change


def classify_all(changes: list[ToolChange]) -> list[ToolChange]:
    return [classify_tool_change(c) for c in changes]


# ------------------------------------------------------------------
# Internal
# ------------------------------------------------------------------

def _match_capabilities(text: str) -> set[Capability]:
    result: set[Capability] = set()
    for cap, keywords in CAPABILITY_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                result.add(cap)
                break
    return result


def _match_domains(text: str) -> set[SensitiveDomain]:
    result: set[SensitiveDomain] = set()
    for domain, keywords in DOMAIN_KEYWORDS.items():
        for kw in keywords:
            if kw in text:
                result.add(domain)
                break
    return result
