from __future__ import annotations

import json
import logging

import yaml

from mcpreviewer.models.types import (
    McpManifest,
    ParseError,
    ScopeDefinition,
    ToolDefinition,
)

logger = logging.getLogger(__name__)


def parse_mcp_file(file_path: str, content: str) -> McpManifest:
    """Parse a single MCP file into a normalised manifest."""
    if not content or not content.strip():
        return McpManifest(file_path=file_path)

    data = _load_data(file_path, content)
    tools = _extract_tools(data)
    scopes = _extract_scopes(data)

    return McpManifest(file_path=file_path, tools=tools, scopes=scopes, raw=data)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _load_data(file_path: str, content: str) -> dict:
    lower = file_path.lower()
    if lower.endswith(".json"):
        return _parse_json(file_path, content)
    if lower.endswith((".yaml", ".yml")):
        return _parse_yaml(file_path, content)
    # Unknown extension – try JSON first, then YAML
    try:
        return _parse_json(file_path, content)
    except ParseError:
        return _parse_yaml(file_path, content)


def _parse_json(file_path: str, content: str) -> dict:
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ParseError(file_path, str(exc)) from exc
    if not isinstance(data, dict):
        raise ParseError(file_path, "Top-level value is not an object")
    return data


def _parse_yaml(file_path: str, content: str) -> dict:
    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ParseError(file_path, str(exc)) from exc
    if not isinstance(data, dict):
        raise ParseError(file_path, "Top-level value is not a mapping")
    return data


# ------------------------------------------------------------------
# Tool extraction
# ------------------------------------------------------------------

def _extract_tools(data: dict) -> list[ToolDefinition]:
    tools: list[ToolDefinition] = []

    # Format B / C – explicit tool list
    raw_tools = data.get("tools")
    if isinstance(raw_tools, list):
        for entry in raw_tools:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name", "")
            if not name:
                continue
            tools.append(
                ToolDefinition(
                    name=str(name),
                    description=str(entry.get("description", "")),
                    input_schema=entry.get("inputSchema") or entry.get("input_schema") or {},
                    annotations=entry.get("annotations") or {},
                    raw=entry,
                )
            )
        return tools

    # Format A – mcpServers style
    servers = data.get("mcpServers")
    if isinstance(servers, dict):
        for server_name, server_cfg in servers.items():
            if not isinstance(server_cfg, dict):
                continue
            desc_parts: list[str] = []
            cmd = server_cfg.get("command", "")
            args = server_cfg.get("args", [])
            if cmd:
                desc_parts.append(f"command={cmd}")
            if args:
                desc_parts.append(f"args={args}")
            env_keys = list((server_cfg.get("env") or {}).keys())
            if env_keys:
                desc_parts.append(f"env_keys={env_keys}")
            tools.append(
                ToolDefinition(
                    name=str(server_name),
                    description=" ".join(desc_parts),
                    raw=server_cfg,
                )
            )

    return tools


# ------------------------------------------------------------------
# Scope extraction
# ------------------------------------------------------------------

def _extract_scopes(data: dict) -> list[ScopeDefinition]:
    scopes: list[ScopeDefinition] = []

    # { "scopes": ["read", "write"] }
    raw_scopes = data.get("scopes")
    if isinstance(raw_scopes, list):
        for s in raw_scopes:
            scopes.append(ScopeDefinition(name=str(s), access=str(s)))
        return scopes

    # { "oauth": { "scopes": [...] } }
    oauth = data.get("oauth")
    if isinstance(oauth, dict):
        oauth_scopes = oauth.get("scopes")
        if isinstance(oauth_scopes, list):
            for s in oauth_scopes:
                scopes.append(ScopeDefinition(name=str(s), access=str(s)))
            return scopes

    # { "permissions": { "pull_requests": "write", "contents": "read" } }
    perms = data.get("permissions")
    if isinstance(perms, dict):
        for perm_name, perm_val in perms.items():
            scopes.append(ScopeDefinition(name=str(perm_name), access=str(perm_val)))
        return scopes

    return scopes
