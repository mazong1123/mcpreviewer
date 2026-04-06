from mcpreviewer.core.classifier import classify_tool_change, classify_all
from mcpreviewer.models.types import (
    Capability,
    ChangeType,
    SensitiveDomain,
    ToolChange,
    ToolDefinition,
)


def _change(name: str, description: str = "", annotations: dict | None = None) -> ToolChange:
    return ToolChange(
        change_type=ChangeType.ADDED,
        tool_name=name,
        new_tool=ToolDefinition(
            name=name,
            description=description,
            annotations=annotations or {},
        ),
    )


class TestClassifier:
    def test_read_tool(self):
        tc = classify_tool_change(_change("get_users", "Retrieves users"))
        assert Capability.READ in tc.capabilities

    def test_write_tool(self):
        tc = classify_tool_change(_change("create_ticket", "Creates a new ticket"))
        assert Capability.WRITE in tc.capabilities

    def test_delete_tool(self):
        tc = classify_tool_change(_change("delete_record", "Deletes a record"))
        assert Capability.DELETE in tc.capabilities

    def test_send_tool(self):
        tc = classify_tool_change(_change("send_email", "Sends an email notification"))
        assert Capability.SEND_NOTIFY in tc.capabilities

    def test_execute_tool(self):
        tc = classify_tool_change(_change("run_query", "Executes a database query"))
        assert Capability.EXECUTE in tc.capabilities

    def test_admin_tool(self):
        tc = classify_tool_change(_change("configure_permissions", "Sets up admin roles"))
        assert Capability.ADMIN in tc.capabilities

    def test_unknown_tool(self):
        tc = classify_tool_change(_change("do_something", "Performs an action"))
        assert Capability.UNKNOWN in tc.capabilities

    def test_sensitive_domain_email(self):
        tc = classify_tool_change(_change("send_smtp", "Sends via smtp server"))
        assert SensitiveDomain.EMAIL in tc.sensitive_domains
        assert Capability.SENSITIVE_SYSTEM_ACCESS in tc.capabilities

    def test_sensitive_domain_billing(self):
        tc = classify_tool_change(_change("charge_customer", "Charges via stripe"))
        assert SensitiveDomain.BILLING_PAYMENTS in tc.sensitive_domains

    def test_sensitive_domain_ticketing(self):
        tc = classify_tool_change(_change("create_ticket", "Creates a Jira ticket"))
        assert SensitiveDomain.TICKETING in tc.sensitive_domains

    def test_annotation_destructive(self):
        tc = classify_tool_change(_change("remove_it", "Removes something", {"destructiveHint": True}))
        assert Capability.DELETE in tc.capabilities

    def test_annotation_readonly(self):
        tc = classify_tool_change(_change("safe_read", "Safe operation", {"readOnlyHint": True}))
        assert Capability.READ in tc.capabilities

    def test_multi_capability(self):
        tc = classify_tool_change(_change("create_and_delete", "Creates and deletes records"))
        assert Capability.WRITE in tc.capabilities
        assert Capability.DELETE in tc.capabilities

    def test_classify_all(self):
        changes = [
            _change("get_users", "Retrieves users"),
            _change("create_ticket", "Creates a ticket"),
        ]
        result = classify_all(changes)
        assert len(result) == 2
        assert Capability.READ in result[0].capabilities
        assert Capability.WRITE in result[1].capabilities

    def test_no_tool(self):
        tc = ToolChange(change_type=ChangeType.REMOVED, tool_name="gone")
        result = classify_tool_change(tc)
        assert result.capabilities == []
