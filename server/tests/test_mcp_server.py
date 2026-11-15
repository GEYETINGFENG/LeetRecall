"""MCP server tests through a real MCP client (in-process, plus one stdio end-to-end run)."""
import json
import os
import re
from datetime import datetime
from pathlib import Path

import pytest
from mcp.client import Client

from leetrecall_ai.mcp_server import build_server
from leetrecall_ai.models import PATTERN_PRESETS
from leetrecall_ai.store import SEED_BACKUP, JsonCardStore

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 11, 10, 12, 0).timestamp()
REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def store(tmp_path):
    return JsonCardStore(tmp_path / "cards.json")


@pytest.fixture
async def client(store):
    async with Client(build_server(store, now=lambda: NOW)) as c:
        yield c


async def call(client, tool, **args):
    r = await client.call_tool(tool, args)
    return r


async def test_lists_four_tools_with_annotations(client):
    tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {"search_cards", "get_card", "get_review_history", "save_card"}
    assert tools["get_card"].annotations.read_only_hint is True
    assert tools["save_card"].annotations.read_only_hint is False
    assert tools["save_card"].annotations.destructive_hint is False


async def test_search_by_pattern_and_keyword(client):
    r = await call(client, "search_cards", pattern="单调栈")
    assert [i["slug"] for i in r.structured_content["items"]] == ["daily-temperatures"]
    r = await call(client, "search_cards", query="lru")
    assert r.structured_content["items"][0]["slug"] == "lru-cache"
    r = await call(client, "search_cards", limit=3)
    assert r.structured_content["total"] == 35 and len(r.structured_content["items"]) == 3


async def test_get_card_and_unknown_slug_is_tool_error(client):
    r = await call(client, "get_card", slug="two-sum", include_code=False)
    assert r.structured_content["patterns"] == ["哈希表"] and r.structured_content["code"] is None
    r = await call(client, "get_card", slug="no-such-problem")
    assert r.is_error and "search_cards" in r.content[0].text  # error tells the agent how to recover


async def test_review_history_matches_fsrs_state(client):
    seed = json.loads(SEED_BACKUP.read_text())["cards"]["daily-temperatures"]
    r = (await call(client, "get_review_history", slug="daily-temperatures")).structured_content
    assert len(r["events"]) == len(seed["history"])
    assert r["events"][0]["mode"] == "solve"
    assert r["reps"] == seed["sched"]["reps"]
    assert 0 < r["retrievability"] <= 1


async def test_save_rejects_unknown_pattern(client):
    r = await call(client, "save_card", slug="two-sum", patterns=["Monotonic Stack"])
    assert r.is_error and "Allowed" in r.content[0].text


async def test_save_updates_content_but_never_scheduling(client, store, tmp_path):
    before = store.get("two-sum")
    r = await call(client, "save_card", slug="two-sum", idea="新思路", hints=["想想补数", "能 O(1) 查到吗"])
    assert r.structured_content == {"slug": "two-sum", "created": False, "updated_fields": ["hints", "idea"]}
    reloaded = JsonCardStore(tmp_path / "cards.json").get("two-sum")  # persisted to disk
    assert reloaded.idea == "新思路" and reloaded.hints == ["想想补数", "能 O(1) 查到吗"]
    assert reloaded.sched == before.sched and reloaded.history == before.history
    assert reloaded.code == before.code


async def test_save_creates_new_card(client, store):
    r = await call(client, "save_card", slug="jump-game-ii", title="Jump Game II", patterns=["贪心"])
    assert r.structured_content["created"] is True
    assert store.get("jump-game-ii").sched.state == "new"


def test_pattern_presets_match_extension():
    js = (REPO / "src" / "store.js").read_text()
    block = re.search(r"PATTERN_PRESETS = \[(.*?)\];", js, re.S).group(1)
    assert tuple(re.findall(r'"([^"]+)"', block)) == PATTERN_PRESETS


async def test_stdio_end_to_end(tmp_path):
    """Spawn the real server as a subprocess, exactly how an agent will connect to it."""
    from mcp.client.stdio import StdioServerParameters

    params = StdioServerParameters(
        command="uv", args=["run", "--quiet", "leetrecall-mcp"],
        cwd=str(REPO / "server"), env={**os.environ, "LEETRECALL_STORE": str(tmp_path / "cards.json")},
    )
    async with Client(params) as c:
        r = await c.call_tool("search_cards", {"pattern": "并查集"})
        assert r.structured_content["items"][0]["slug"] == "number-of-provinces"
