import hashlib
import hmac

from mcpreviewer.app.webhook_handler import verify_signature


class TestWebhookHandler:
    def test_valid_signature_accepted(self):
        secret = "test-secret"
        body = b'{"action": "opened"}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert verify_signature(body, sig, secret) is True

    def test_invalid_signature_rejected(self):
        assert verify_signature(b"body", "sha256=bad", "secret") is False

    def test_missing_prefix_rejected(self):
        assert verify_signature(b"body", "nope", "secret") is False

    def test_empty_signature_rejected(self):
        assert verify_signature(b"body", "", "secret") is False
