"""Tests for the LLM-based classifier."""
import json
from unittest.mock import MagicMock, patch

import pytest

from mcpreviewer.core.llm_classifier import (
    SYSTEM_PROMPT,
    _apply_classifications,
    _build_tools_description,
    _parse_response,
    llm_classify_all,
)
from mcpreviewer.models.types import (
    Capability,
    ChangeType,
    SensitiveDomain,
    ToolChange,
    ToolDefinition,
)


def _change(
    name: str,
    description: str = "",
    annotations: dict | None = None,
    raw: dict | None = None,
) -> ToolChange:
    return ToolChange(
        change_type=ChangeType.ADDED,
        tool_name=name,
        new_tool=ToolDefinition(
            name=name,
            description=description,
            annotations=annotations or {},
            raw=raw or {},
        ),
    )


# ------------------------------------------------------------------
# _build_tools_description
# ------------------------------------------------------------------

class TestBuildToolsDescription:
    def test_basic_tool(self):
        changes = [_change("get_users", "Retrieves user list")]
        desc = _build_tools_description(changes)
        assert "**get_users**" in desc
        assert "Retrieves user list" in desc

    def test_tool_with_schema(self):
        changes = [_change("create_ticket", "Creates a ticket")]
        changes[0].new_tool = ToolDefinition(
            name="create_ticket",
            description="Creates a ticket",
            input_schema={"type": "object", "properties": {"title": {"type": "string"}}},
        )
        desc = _build_tools_description(changes)
        assert "Input schema:" in desc

    def test_tool_with_raw_config(self):
        raw = {"command": "npx", "args": ["-y", "@mcp/server-weather"], "env": {}}
        changes = [_change("weather", raw=raw)]
        desc = _build_tools_description(changes)
        assert "Server config:" in desc
        assert "npx" in desc

    def test_tool_with_annotations(self):
        changes = [_change("safe_read", annotations={"readOnlyHint": True})]
        desc = _build_tools_description(changes)
        assert "readOnlyHint" in desc

    def test_no_tool_definition(self):
        tc = ToolChange(change_type=ChangeType.REMOVED, tool_name="gone")
        desc = _build_tools_description([tc])
        assert "no tool definition available" in desc

    def test_multiple_tools(self):
        changes = [
            _change("get_users", "Retrieves users"),
            _change("delete_record", "Deletes a record"),
        ]
        desc = _build_tools_description(changes)
        assert "1." in desc
        assert "2." in desc

    def test_long_schema_truncated(self):
        big_schema = {"properties": {f"field_{i}": {"type": "string"} for i in range(100)}}
        changes = [_change("big_tool")]
        changes[0].new_tool = ToolDefinition(name="big_tool", input_schema=big_schema)
        desc = _build_tools_description(changes)
        assert "..." in desc


# ------------------------------------------------------------------
# _parse_response
# ------------------------------------------------------------------

class TestParseResponse:
    def test_plain_json(self):
        raw = json.dumps([{"tool_name": "x", "capabilities": ["Read"], "sensitive_domains": []}])
        result = _parse_response(raw, [])
        assert len(result) == 1
        assert result[0]["tool_name"] == "x"

    def test_json_with_markdown_fences(self):
        raw = '```json\n[{"tool_name": "x", "capabilities": ["Read"], "sensitive_domains": []}]\n```'
        result = _parse_response(raw, [])
        assert len(result) == 1

    def test_invalid_json_raises(self):
        with pytest.raises((json.JSONDecodeError, ValueError)):
            _parse_response("not json at all", [])

    def test_non_array_raises(self):
        with pytest.raises(ValueError, match="JSON array"):
            _parse_response('{"tool_name": "x"}', [])


# ------------------------------------------------------------------
# _apply_classifications
# ------------------------------------------------------------------

class TestApplyClassifications:
    def test_basic_read(self):
        changes = [_change("get_users", "Retrieves users")]
        classifications = [
            {"tool_name": "get_users", "capabilities": ["Read"], "sensitive_domains": []},
        ]
        result = _apply_classifications(changes, classifications)
        assert Capability.READ in result[0].capabilities

    def test_multiple_capabilities(self):
        changes = [_change("manage_records")]
        classifications = [
            {"tool_name": "manage_records", "capabilities": ["Read", "Write", "Delete"], "sensitive_domains": []},
        ]
        result = _apply_classifications(changes, classifications)
        assert Capability.READ in result[0].capabilities
        assert Capability.WRITE in result[0].capabilities
        assert Capability.DELETE in result[0].capabilities

    def test_sensitive_domain_adds_sensitive_access(self):
        changes = [_change("query_db")]
        classifications = [
            {"tool_name": "query_db", "capabilities": ["Read"], "sensitive_domains": ["Database"]},
        ]
        result = _apply_classifications(changes, classifications)
        assert Capability.READ in result[0].capabilities
        assert Capability.SENSITIVE_SYSTEM_ACCESS in result[0].capabilities
        assert SensitiveDomain.DATABASE in result[0].sensitive_domains

    def test_multiple_domains(self):
        changes = [_change("sync_crm_email")]
        classifications = [
            {
                "tool_name": "sync_crm_email",
                "capabilities": ["Write"],
                "sensitive_domains": ["Email", "CRM / customer records"],
            },
        ]
        result = _apply_classifications(changes, classifications)
        assert SensitiveDomain.EMAIL in result[0].sensitive_domains
        assert SensitiveDomain.CRM_CUSTOMER_RECORDS in result[0].sensitive_domains

    def test_unknown_fallback(self):
        changes = [_change("mysterious_thing")]
        classifications = [
            {"tool_name": "mysterious_thing", "capabilities": [], "sensitive_domains": []},
        ]
        result = _apply_classifications(changes, classifications)
        assert Capability.UNKNOWN in result[0].capabilities

    def test_missing_tool_falls_back_to_rule_based(self):
        changes = [_change("get_users", "Retrieves users")]
        classifications = []  # LLM returned nothing
        result = _apply_classifications(changes, classifications)
        # Rule-based should pick up "get_" keyword
        assert Capability.READ in result[0].capabilities

    def test_no_tool_definition(self):
        tc = ToolChange(change_type=ChangeType.REMOVED, tool_name="gone")
        result = _apply_classifications([tc], [])
        assert result[0].capabilities == []

    def test_case_insensitive_capability(self):
        changes = [_change("tool")]
        classifications = [
            {"tool_name": "tool", "capabilities": ["read", "WRITE"], "sensitive_domains": []},
        ]
        result = _apply_classifications(changes, classifications)
        assert Capability.READ in result[0].capabilities
        assert Capability.WRITE in result[0].capabilities

    def test_all_capabilities(self):
        changes = [_change("super_tool")]
        classifications = [
            {
                "tool_name": "super_tool",
                "capabilities": [
                    "Read", "Write", "Delete", "Send / Notify",
                    "Execute", "Admin / Configuration",
                ],
                "sensitive_domains": [],
            },
        ]
        result = _apply_classifications(changes, classifications)
        assert Capability.READ in result[0].capabilities
        assert Capability.WRITE in result[0].capabilities
        assert Capability.DELETE in result[0].capabilities
        assert Capability.SEND_NOTIFY in result[0].capabilities
        assert Capability.EXECUTE in result[0].capabilities
        assert Capability.ADMIN in result[0].capabilities

    def test_all_domains(self):
        changes = [_change("mega_tool")]
        classifications = [
            {
                "tool_name": "mega_tool",
                "capabilities": ["Read"],
                "sensitive_domains": [
                    "Email", "Ticketing", "Source control", "Database",
                    "Cloud infrastructure", "Billing / payments",
                    "CRM / customer records", "Identity / authentication",
                    "File storage",
                ],
            },
        ]
        result = _apply_classifications(changes, classifications)
        assert len(result[0].sensitive_domains) == 9

    def test_invalid_capability_ignored(self):
        changes = [_change("tool")]
        classifications = [
            {"tool_name": "tool", "capabilities": ["Read", "FlyToMoon"], "sensitive_domains": []},
        ]
        result = _apply_classifications(changes, classifications)
        assert Capability.READ in result[0].capabilities
        assert len(result[0].capabilities) == 1

    def test_capabilities_sorted(self):
        changes = [_change("tool")]
        classifications = [
            {"tool_name": "tool", "capabilities": ["Execute", "Read", "Write"], "sensitive_domains": []},
        ]
        result = _apply_classifications(changes, classifications)
        cap_values = [c.value for c in result[0].capabilities]
        assert cap_values == sorted(cap_values)


# ------------------------------------------------------------------
# llm_classify_all (integration with mocked HTTP)
# ------------------------------------------------------------------

class TestLlmClassifyAll:
    def test_empty_changes(self):
        result = llm_classify_all([])
        assert result == []

    def test_no_api_key_falls_back(self):
        changes = [_change("get_users", "Retrieves users")]
        with patch.dict("os.environ", {}, clear=False):
            # Ensure no key is set
            import os
            os.environ.pop("MCPREVIEWER_LLM_API_KEY", None)
            result = llm_classify_all(changes)
        # Should fall back to rule-based
        assert Capability.READ in result[0].capabilities

    @patch("mcpreviewer.core.llm_classifier._call_llm")
    def test_successful_classification(self, mock_call):
        mock_call.return_value = json.dumps([
            {"tool_name": "run_shell", "capabilities": ["Execute"], "sensitive_domains": []},
        ])
        changes = [_change("run_shell", "Runs shell commands")]
        result = llm_classify_all(changes, api_key="test-key")
        assert Capability.EXECUTE in result[0].capabilities
        mock_call.assert_called_once()

    @patch("mcpreviewer.core.llm_classifier._call_llm")
    def test_llm_returns_markdown_fenced_json(self, mock_call):
        mock_call.return_value = (
            '```json\n[{"tool_name": "send_email", '
            '"capabilities": ["Send / Notify"], '
            '"sensitive_domains": ["Email"]}]\n```'
        )
        changes = [_change("send_email", "Sends emails")]
        result = llm_classify_all(changes, api_key="test-key")
        assert Capability.SEND_NOTIFY in result[0].capabilities
        assert SensitiveDomain.EMAIL in result[0].sensitive_domains

    @patch("mcpreviewer.core.llm_classifier._call_llm")
    def test_llm_failure_falls_back(self, mock_call):
        mock_call.side_effect = RuntimeError("API down")
        changes = [_change("get_users", "Retrieves users")]
        result = llm_classify_all(changes, api_key="test-key")
        # Should fall back to rule-based
        assert Capability.READ in result[0].capabilities

    @patch("mcpreviewer.core.llm_classifier._call_llm")
    def test_llm_invalid_json_falls_back(self, mock_call):
        mock_call.return_value = "I can't classify these tools sorry"
        changes = [_change("get_users", "Retrieves users")]
        result = llm_classify_all(changes, api_key="test-key")
        assert Capability.READ in result[0].capabilities

    @patch("mcpreviewer.core.llm_classifier._call_llm")
    def test_multiple_tools(self, mock_call):
        mock_call.return_value = json.dumps([
            {"tool_name": "get_users", "capabilities": ["Read"], "sensitive_domains": []},
            {"tool_name": "delete_record", "capabilities": ["Delete"], "sensitive_domains": ["Database"]},
        ])
        changes = [
            _change("get_users", "Retrieves users"),
            _change("delete_record", "Deletes a database record"),
        ]
        result = llm_classify_all(changes, api_key="test-key")
        assert Capability.READ in result[0].capabilities
        assert Capability.DELETE in result[1].capabilities
        assert SensitiveDomain.DATABASE in result[1].sensitive_domains

    @patch("mcpreviewer.core.llm_classifier._call_llm")
    def test_partial_llm_response(self, mock_call):
        # LLM only returns classification for one of two tools
        mock_call.return_value = json.dumps([
            {"tool_name": "delete_record", "capabilities": ["Delete"], "sensitive_domains": []},
        ])
        changes = [
            _change("get_users", "Retrieves users"),
            _change("delete_record", "Deletes a record"),
        ]
        result = llm_classify_all(changes, api_key="test-key")
        # First tool should fall back to rule-based
        assert Capability.READ in result[0].capabilities
        # Second tool should use LLM classification
        assert Capability.DELETE in result[1].capabilities

    @patch("mcpreviewer.core.llm_classifier._call_llm")
    def test_server_style_tool(self, mock_call):
        mock_call.return_value = json.dumps([
            {
                "tool_name": "postgres-manager",
                "capabilities": ["Read", "Write", "Delete"],
                "sensitive_domains": ["Database"],
            },
        ])
        raw = {"command": "npx", "args": ["-y", "@mcp/server-postgres"], "env": {"DATABASE_URL": "postgres://..."}}
        changes = [_change("postgres-manager", raw=raw)]
        result = llm_classify_all(changes, api_key="test-key")
        assert Capability.READ in result[0].capabilities
        assert Capability.WRITE in result[0].capabilities
        assert Capability.DELETE in result[0].capabilities
        assert SensitiveDomain.DATABASE in result[0].sensitive_domains

    @patch("mcpreviewer.core.llm_classifier._call_llm")
    def test_custom_model_and_base_url(self, mock_call):
        mock_call.return_value = json.dumps([
            {"tool_name": "tool", "capabilities": ["Read"], "sensitive_domains": []},
        ])
        changes = [_change("tool")]
        llm_classify_all(
            changes,
            api_key="sk-test",
            model="claude-3-haiku-20240307",
            base_url="https://api.anthropic.com/v1",
        )
        # Verify the call was made (with correct params passed through)
        mock_call.assert_called_once()
        args = mock_call.call_args
        assert args[0][0] == "sk-test"  # api_key
        assert args[0][1] == "claude-3-haiku-20240307"  # model
        assert args[0][2] == "https://api.anthropic.com/v1"  # base_url


# ------------------------------------------------------------------
# System prompt quality checks
# ------------------------------------------------------------------

class TestSystemPrompt:
    def test_all_capabilities_mentioned(self):
        for cap in ["Read", "Write", "Delete", "Send / Notify", "Execute", "Admin / Configuration"]:
            assert cap in SYSTEM_PROMPT

    def test_all_domains_mentioned(self):
        for domain in [
            "Email", "Ticketing", "Source control", "Database",
            "Cloud infrastructure", "Billing / payments",
            "CRM / customer records", "Identity / authentication",
            "File storage",
        ]:
            assert domain in SYSTEM_PROMPT

    def test_json_output_format_specified(self):
        assert "JSON array" in SYSTEM_PROMPT
        assert "tool_name" in SYSTEM_PROMPT
        assert "capabilities" in SYSTEM_PROMPT
        assert "sensitive_domains" in SYSTEM_PROMPT
