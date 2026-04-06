from __future__ import annotations

import hashlib
import hmac
import logging

from mcpreviewer.app.config import Settings
from mcpreviewer.app.github_client import GitHubClient
from mcpreviewer.core.comment_renderer import render_comment
from mcpreviewer.core.pipeline import analyze
from mcpreviewer.core.policy import POLICY_FILE_NAMES

logger = logging.getLogger(__name__)


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


async def handle_pr(payload: dict, settings: Settings) -> None:
    """Full PR analysis orchestration."""
    installation_id = payload["installation"]["id"]
    repo_full_name = payload["repository"]["full_name"]
    pr_number = payload["pull_request"]["number"]
    base_sha = payload["pull_request"]["base"]["sha"]
    head_sha = payload["pull_request"]["head"]["sha"]

    logger.info("PR event received: %s#%s", repo_full_name, pr_number)

    client = GitHubClient(settings, installation_id)

    try:
        changed_files = await client.get_pr_files(repo_full_name, pr_number)

        file_contents: dict[str, tuple[str | None, str | None]] = {}
        for file_path in changed_files:
            base_content = await client.get_file_content(repo_full_name, file_path, base_sha)
            head_content = await client.get_file_content(repo_full_name, file_path, head_sha)
            file_contents[file_path] = (base_content, head_content)

        policy_content: str | None = None
        for name in POLICY_FILE_NAMES:
            policy_content = await client.get_file_content(repo_full_name, name, head_sha)
            if policy_content is not None:
                break

        result = analyze(changed_files, file_contents, policy_content)

        if result is not None:
            comment_body = render_comment(result)
            await client.upsert_pr_comment(repo_full_name, pr_number, comment_body)
            logger.info("Analysis complete: %s for %s#%s", result.recommendation.value, repo_full_name, pr_number)
        else:
            await client.delete_bot_comment(repo_full_name, pr_number)
            logger.info("No MCP files found for %s#%s", repo_full_name, pr_number)

    except Exception:
        logger.exception("Error processing PR #%s in %s", pr_number, repo_full_name)
