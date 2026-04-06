from __future__ import annotations

import time
import logging

import httpx
import jwt

from mcpreviewer.app.config import Settings

logger = logging.getLogger(__name__)

BOT_COMMENT_MARKER = "<!-- mcpreviewer-bot -->"


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, settings: Settings, installation_id: int) -> None:
        self._settings = settings
        self._installation_id = installation_id
        self._token: str | None = None
        self._token_expires: float = 0

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires - 60:
            return self._token

        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + 10 * 60,
            "iss": self._settings.github_app_id,
        }
        encoded = jwt.encode(payload, self._settings.github_private_key, algorithm="RS256")

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

    async def _headers(self) -> dict[str, str]:
        token = await self._get_token()
        return {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github+json",
        }

    # ------------------------------------------------------------------
    # API methods
    # ------------------------------------------------------------------

    async def get_pr_files(self, repo: str, pr_number: int) -> list[str]:
        headers = await self._headers()
        files: list[str] = []
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

    async def get_file_content(self, repo: str, path: str, ref: str) -> str | None:
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

    async def upsert_pr_comment(self, repo: str, pr_number: int, body: str) -> None:
        headers = await self._headers()
        body_with_marker = f"{BOT_COMMENT_MARKER}\n{body}"

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}/repos/{repo}/issues/{pr_number}/comments",
                headers=headers,
                params={"per_page": 100},
            )
            resp.raise_for_status()
            comments = resp.json()

            existing_id = None
            for c in comments:
                if BOT_COMMENT_MARKER in (c.get("body") or ""):
                    existing_id = c["id"]
                    break

            if existing_id:
                resp = await client.patch(
                    f"{self.BASE_URL}/repos/{repo}/issues/comments/{existing_id}",
                    headers=headers,
                    json={"body": body_with_marker},
                )
            else:
                resp = await client.post(
                    f"{self.BASE_URL}/repos/{repo}/issues/{pr_number}/comments",
                    headers=headers,
                    json={"body": body_with_marker},
                )
            resp.raise_for_status()

    async def delete_bot_comment(self, repo: str, pr_number: int) -> None:
        headers = await self._headers()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.BASE_URL}/repos/{repo}/issues/{pr_number}/comments",
                headers=headers,
                params={"per_page": 100},
            )
            resp.raise_for_status()
            for c in resp.json():
                if BOT_COMMENT_MARKER in (c.get("body") or ""):
                    await client.delete(
                        f"{self.BASE_URL}/repos/{repo}/issues/comments/{c['id']}",
                        headers=headers,
                    )
                    break
