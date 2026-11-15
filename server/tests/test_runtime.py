from leetrecall_ai.agents.runtime import RunTrace, ToolCall, seen_slugs


def test_seen_slugs_only_counts_successful_tool_results():
    t = RunTrace(tool_calls=[
        ToolCall("a", "search_cards", {}, response={"structuredContent": {"items": [{"slug": "daily-temperatures"}, {"slug": "lru-cache"}]}}),
        ToolCall("a", "get_card", {}, is_error=True, response={"slug": "hallucinated"}),
    ])
    assert seen_slugs(t) == {"daily-temperatures", "lru-cache"}
