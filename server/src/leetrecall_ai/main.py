"""HTTP service: the extension's only entry point into the AI backend.

  GET  /healthz            liveness (no auth)
  POST /v1/cards/draft     problem id/title + the user's code -> drafted card, related cards, metrics
  POST /v1/cards/sync      push the extension's card library (same merge rule as the extension's restore)
  /mcp                     the MCP server (streamable HTTP). Agents in this process connect to it over
                           loopback; external MCP clients (Claude Desktop, Inspector) can use it too.

Every path except /healthz requires `X-API-Key`. Cloud Run is deployed --allow-unauthenticated because
a Chrome extension can't easily mint Google IAM tokens; the key (from Secret Manager) is the gate, and
max-instances + a per-instance concurrency limit cap what a leaked key could cost.

Run locally:  uv run uvicorn leetrecall_ai.main:app --port 8080
"""
from __future__ import annotations

import asyncio
import contextlib
import hmac
import os
from typing import Any

from fastapi import FastAPI, HTTPException
from google.adk.tools.mcp_tool import StreamableHTTPConnectionParams
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .agents.coordinator import generate_card
from .mcp_server import build_server, default_store
from .models import Card
from .obs.tracing import setup_tracing
from .schemas import CardDraft, ProblemInput

API_KEY = os.environ.get("LEETRECALL_API_KEY", "")
PORT = int(os.environ.get("PORT", "8080"))
MAX_CONCURRENT_DRAFTS = int(os.environ.get("LEETRECALL_MAX_CONCURRENT_DRAFTS", "2"))

setup_tracing()  # before any Claude client exists
store = default_store()  # loads the embedding model + connects to Qdrant once per instance
mcp = build_server(store)
# Stateless HTTP: any Cloud Run instance can serve any MCP request (no sticky sessions needed).
# DNS-rebinding protection guards unauthenticated localhost servers; every request here needs the key.
mcp_app = mcp.streamable_http_app(stateless_http=True, json_response=True,
                                  transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
draft_slots = asyncio.Semaphore(MAX_CONCURRENT_DRAFTS)


class ApiKeyMiddleware:
    """Pure ASGI so it also protects the mounted MCP app."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] != "/healthz":
            got = dict(scope["headers"]).get(b"x-api-key", b"").decode()
            if not API_KEY or not hmac.compare_digest(got, API_KEY):  # no key configured = locked, not open
                await JSONResponse({"detail": "missing or invalid X-API-Key"}, status_code=401)(scope, receive, send)
                return
        await self.app(scope, receive, send)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    async with mcp.session_manager.run():  # the mounted MCP app's lifespan doesn't run on its own
        yield


app = FastAPI(title="LeetRecall AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(ApiKeyMiddleware)


class DraftOptions(BaseModel):
    critic: bool = True
    max_rounds: int = Field(3, ge=1, le=3)


class DraftRequest(ProblemInput):
    options: DraftOptions = DraftOptions()


class DraftResponse(BaseModel):
    draft: CardDraft
    critic: dict[str, Any]
    metrics: dict[str, Any]
    trace_id: str


class SyncRequest(BaseModel):
    cards: dict[str, dict[str, Any]]


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True}


@app.post("/v1/cards/draft", response_model=DraftResponse)
async def draft(req: DraftRequest) -> DraftResponse:
    if draft_slots.locked():
        raise HTTPException(429, "busy: too many card drafts in progress, retry shortly")
    async with draft_slots:
        conn = StreamableHTTPConnectionParams(url=f"http://127.0.0.1:{PORT}/mcp", headers={"X-API-Key": API_KEY},
                                              timeout=30)
        r = await generate_card(ProblemInput.model_validate(req.model_dump(exclude={"options"})),
                                use_critic=req.options.critic, max_rounds=req.options.max_rounds,
                                mcp_connection=conn)
    last = r.critic.history[-1] if r.critic.history else None
    return DraftResponse(
        draft=r.draft,
        critic={"enabled": r.critic.enabled, "rounds": r.critic.rounds, "passed": r.critic.passed,
                "last_issues": (last or {}).get("verdict", {}).get("issues", []) if last and not last.get("malformed") else []},
        metrics={k: v for k, v in r.metrics.items() if k != "calls"},
        trace_id=r.trace_id,
    )


@app.post("/v1/cards/sync")
async def sync(req: SyncRequest) -> dict:
    """Newer `updatedAt` wins, the same rule the extension uses when restoring a backup."""
    incoming = [Card.model_validate(c | {"slug": slug}) for slug, c in req.cards.items()]
    changed = [c for c in incoming if (cur := store.get(c.slug)) is None or c.updatedAt > cur.updatedAt]
    def write() -> None:  # embedding is CPU-bound: keep it off the event loop
        if hasattr(store, "upsert_many"):
            store.upsert_many(changed)
        else:
            for c in changed:
                store.upsert(c)

    await asyncio.to_thread(write)
    return {"received": len(incoming), "updated": len(changed)}


app.mount("/", mcp_app)  # serves /mcp; mounted last so the routes above take precedence
