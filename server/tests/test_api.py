"""HTTP layer tests (no LLM calls): auth, sync merge rule, and the mounted MCP endpoint."""
import os

os.environ["QDRANT_PATH"] = ":memory:"
os.environ["LEETRECALL_API_KEY"] = "test-key"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from leetrecall_ai.main import app, store  # noqa: E402

H = {"X-API-Key": "test-key"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:  # runs the lifespan (MCP session manager)
        yield c


def test_healthz_is_open(client):
    assert client.get("/healthz").json() == {"ok": True}


@pytest.mark.parametrize("path", ["/v1/cards/sync", "/v1/cards/draft", "/mcp"])
def test_everything_else_needs_the_key(client, path):
    assert client.post(path, json={}).status_code == 401
    assert client.post(path, json={}, headers={"X-API-Key": "wrong"}).status_code == 401


def test_sync_newer_wins(client):
    cur = store.get("two-sum")
    older = cur.model_dump() | {"idea": "stale", "updatedAt": cur.updatedAt - 1}
    newer = cur.model_dump() | {"idea": "fresh", "updatedAt": cur.updatedAt + 1}
    assert client.post("/v1/cards/sync", json={"cards": {"two-sum": older}}, headers=H).json()["updated"] == 0
    assert client.post("/v1/cards/sync", json={"cards": {"two-sum": newer}}, headers=H).json()["updated"] == 1
    assert store.get("two-sum").idea == "fresh"


def test_mcp_over_http_lists_tools(client):
    r = client.post("/mcp", headers=H | {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
                    json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                          "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                     "clientInfo": {"name": "test", "version": "0"}}})
    assert r.status_code == 200, r.text
    assert r.json()["result"]["serverInfo"]["name"] == "leetrecall"
