"""Pattern Analyzer: classify the code's pattern and retrieve the user's related cards via MCP.

The only agent with tools — and only read tools.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.mcp_tool import McpToolset

from .. import config
from ..models import PATTERN_PRESETS
from ..schemas import PatternAnalysis
from .common import ANALYSIS, DATA_NOT_INSTRUCTIONS, PROBLEM, render_problem

READ_TOOLS = ["find_similar_cards", "search_cards", "get_card", "get_review_history"]


def _instruction(ctx: ReadonlyContext) -> str:
    return f"""\
You are the Pattern Analyzer in a pipeline that writes LeetCode "idea cards" for one user.
You see the problem id/title and the user's accepted code, NOT the problem statement.

1. Decide which algorithm pattern THIS code uses (not what other solutions might use).
   Allowed labels: {", ".join(PATTERN_PRESETS)}
2. Find problems the user solved before with a similar IDEA:
   a. Write a 1-2 sentence description of the solution idea in Chinese, the way the user's idea
      cards are written (what is maintained, what is decided at each step) — not code, not the title.
   b. Call find_similar_cards with that description and exclude_slug="{ctx.state[PROBLEM]['slug']}".
   c. If the results look unrelated, call search_cards with the pattern label instead.
   At most 3 tool calls in total.
3. Return the analysis. `related` may only contain slugs that appeared in tool results, and only
   ones that genuinely share the idea (an empty list is fine).

{DATA_NOT_INSTRUCTIONS}

{render_problem(ctx.state[PROBLEM])}"""


def build(toolset: McpToolset) -> LlmAgent:
    return LlmAgent(
        name="pattern_analyzer",
        description="Classifies the algorithm pattern and finds the user's related cards.",
        model=config.llm(),
        generate_content_config=config.gen_config("medium"),
        instruction=_instruction,
        include_contents="none",
        tools=[toolset],
        output_schema=PatternAnalysis,
        output_key=ANALYSIS,
    )
