"""LLM-based classifier for MCP tool changes.

Uses an OpenAI-compatible chat completions API to classify tool capabilities
and sensitive domains with higher accuracy than keyword matching alone.

Configuration via environment variables:
    MCPREVIEWER_LLM_API_KEY  – API key (required when using llm classifier)
    MCPREVIEWER_LLM_MODEL    – Model name (default: gpt-4o-mini)
    MCPREVIEWER_LLM_BASE_URL – Base URL (default: https://api.openai.com/v1)
"""
from __future__ import annotations

import json
import logging
import os

import httpx

from mcpreviewer.models.types import (
    Capability,
    SensitiveDomain,
    ToolChange,
)

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# System prompt – guides the LLM to produce structured output
# ------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a security reviewer for MCP (Model Context Protocol) tool configurations.

Your task: classify each MCP tool by its **capabilities** and **sensitive domains**.

## Capabilities (pick ALL that apply)

| Capability            | Description                                                      |
|-----------------------|------------------------------------------------------------------|
| Read                  | Retrieves, queries, or reads data without modifying anything     |
| Write                 | Creates, updates, or modifies data                               |
| Delete                | Removes, destroys, or purges data                                |
| Send / Notify         | Sends messages, emails, notifications, or alerts                 |
| Execute               | Runs commands, scripts, code, or triggers deployments            |
| Admin / Configuration | Manages permissions, roles, policies, or system configuration    |

If the tool's purpose is genuinely unclear from the available information,
use "Unknown". Prefer a specific capability whenever possible.

## Sensitive Domains (pick ALL that apply, or empty list if none)

| Domain                      | Examples                                           |
|-----------------------------|----------------------------------------------------|
| Email                       | SMTP, inbox, SendGrid, SES, mailbox                |
| Ticketing                   | Jira, ServiceNow, Zendesk, issue tracking          |
| Source control               | Git repos, branches, commits, pull requests         |
| Database                    | SQL, PostgreSQL, MySQL, MongoDB, Redis, DynamoDB   |
| Cloud infrastructure        | AWS, Azure, GCP, Kubernetes, Terraform, Lambda     |
| Billing / payments          | Stripe, invoicing, charges, subscriptions          |
| CRM / customer records      | Salesforce, HubSpot, customer data, leads          |
| Identity / authentication   | OAuth, IAM, SSO, SAML, tokens, credentials         |
| File storage                | S3, blob storage, file uploads, Google Drive       |

## Rules

1. Base your classification on the tool name, description, and input schema.
2. A tool may have MULTIPLE capabilities (e.g. a tool that reads and writes).
3. A tool may touch MULTIPLE sensitive domains.
4. If the tool interacts with a sensitive domain, also include the relevant
   capability (e.g. a tool that reads from a database → Read + Database).
5. Err on the side of flagging potential risk — false positives are better
   than false negatives in a security review.
6. For server-style entries that only have a name and command (no explicit
   tool descriptions), infer purpose from the server name, package name,
   and any environment variables.

## Output format

Return a JSON array with one object per tool, in the same order as the input.
Each object must have exactly these fields:
```json
{
  "tool_name": "<name>",
  "capabilities": ["<Capability>", ...],
  "sensitive_domains": ["<Domain>", ...]
}
```

Use the EXACT capability and domain strings from the tables above.
Return ONLY the JSON array, no markdown fences, no explanation.\
"""


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def llm_classify_all(
    changes: list[ToolChange],
    *,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> list[ToolChange]:
    """Classify tool changes using an LLM.

    Falls back to the rule-based classifier for any tool the LLM fails on.
    """
    from mcpreviewer.core.classifier import classify_tool_change as rule_classify

    if not changes:
        return changes

    api_key = api_key or os.environ.get("MCPREVIEWER_LLM_API_KEY", "")
    model = model or os.environ.get("MCPREVIEWER_LLM_MODEL", "gpt-4o-mini")
    base_url = base_url or os.environ.get(
        "MCPREVIEWER_LLM_BASE_URL", "https://api.openai.com/v1"
    )

    if not api_key:
        logger.warning("No LLM API key configured; falling back to rule-based classifier")
        return [rule_classify(c) for c in changes]

    # Build the user prompt describing each tool
    tools_desc = _build_tools_description(changes)
    user_prompt = (
        "Classify the following MCP tools:\n\n" + tools_desc
    )

    try:
        raw_response = _call_llm(api_key, model, base_url, user_prompt)
        classifications = _parse_response(raw_response, changes)
        return _apply_classifications(changes, classifications)
    except Exception:
        logger.exception("LLM classification failed; falling back to rule-based")
        return [rule_classify(c) for c in changes]


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _build_tools_description(changes: list[ToolChange]) -> str:
    """Format tool information for the LLM prompt."""
    parts: list[str] = []
    for i, change in enumerate(changes, 1):
        tool = change.new_tool or change.old_tool
        if tool is None:
            parts.append(f"{i}. **{change.tool_name}** — (no tool definition available)")
            continue

        lines = [f"{i}. **{tool.name}**"]
        if tool.description:
            lines.append(f"   Description: {tool.description}")
        if tool.input_schema:
            # Compact schema to avoid token bloat
            schema_str = json.dumps(tool.input_schema, separators=(",", ":"))
            if len(schema_str) > 500:
                schema_str = schema_str[:500] + "..."
            lines.append(f"   Input schema: {schema_str}")
        if tool.annotations:
            lines.append(f"   Annotations: {json.dumps(tool.annotations)}")
        if tool.raw:
            # Include command/args/env for server-style entries
            raw_info = {}
            for key in ("command", "args", "env", "type", "url"):
                if key in tool.raw:
                    raw_info[key] = tool.raw[key]
            if raw_info:
                lines.append(f"   Server config: {json.dumps(raw_info, separators=(',', ':'))}")

        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def _call_llm(api_key: str, model: str, base_url: str, user_prompt: str) -> str:
    """Call the OpenAI-compatible chat completions endpoint."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    }

    with httpx.Client(timeout=60.0) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    return data["choices"][0]["message"]["content"]


_CAPABILITY_MAP: dict[str, Capability] = {
    "read": Capability.READ,
    "write": Capability.WRITE,
    "delete": Capability.DELETE,
    "send / notify": Capability.SEND_NOTIFY,
    "execute": Capability.EXECUTE,
    "admin / configuration": Capability.ADMIN,
    "unknown": Capability.UNKNOWN,
}

_DOMAIN_MAP: dict[str, SensitiveDomain] = {
    "email": SensitiveDomain.EMAIL,
    "ticketing": SensitiveDomain.TICKETING,
    "source control": SensitiveDomain.SOURCE_CONTROL,
    "database": SensitiveDomain.DATABASE,
    "cloud infrastructure": SensitiveDomain.CLOUD_INFRASTRUCTURE,
    "billing / payments": SensitiveDomain.BILLING_PAYMENTS,
    "crm / customer records": SensitiveDomain.CRM_CUSTOMER_RECORDS,
    "identity / authentication": SensitiveDomain.IDENTITY_AUTH,
    "file storage": SensitiveDomain.FILE_STORAGE,
}


def _parse_response(
    raw: str, changes: list[ToolChange]
) -> list[dict]:
    """Parse the LLM JSON response into a list of classification dicts."""
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    items = json.loads(text)
    if not isinstance(items, list):
        raise ValueError("Expected a JSON array from LLM")
    return items


def _apply_classifications(
    changes: list[ToolChange],
    classifications: list[dict],
) -> list[ToolChange]:
    """Apply parsed LLM classifications to ToolChange objects."""
    from mcpreviewer.core.classifier import classify_tool_change as rule_classify

    # Build lookup by tool_name for resilience against ordering issues
    by_name: dict[str, dict] = {}
    for item in classifications:
        name = item.get("tool_name", "")
        if name:
            by_name[name] = item

    result: list[ToolChange] = []
    for change in changes:
        tool = change.new_tool or change.old_tool
        if tool is None:
            result.append(change)
            continue

        item = by_name.get(tool.name) or by_name.get(change.tool_name)
        if item is None:
            # LLM missed this tool, fall back
            result.append(rule_classify(change))
            continue

        # Parse capabilities
        caps: set[Capability] = set()
        for cap_str in item.get("capabilities", []):
            cap = _CAPABILITY_MAP.get(cap_str.lower())
            if cap:
                caps.add(cap)

        # Parse domains
        domains: set[SensitiveDomain] = set()
        for dom_str in item.get("sensitive_domains", []):
            dom = _DOMAIN_MAP.get(dom_str.lower())
            if dom:
                domains.add(dom)

        if domains:
            caps.add(Capability.SENSITIVE_SYSTEM_ACCESS)

        if not caps:
            caps.add(Capability.UNKNOWN)

        change.capabilities = sorted(caps, key=lambda c: c.value)
        change.sensitive_domains = sorted(domains, key=lambda d: d.value)
        result.append(change)

    return result
