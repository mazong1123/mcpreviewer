from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response

from mcpreviewer.app.config import Settings
from mcpreviewer.app.webhook_handler import handle_pr, verify_signature

settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
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

    asyncio.create_task(handle_pr(payload, settings))

    return Response(status_code=200, content="Processing")
