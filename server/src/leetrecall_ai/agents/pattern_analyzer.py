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

READ_TOOLS = ["search_cards", "get_card", "get_review_history"]


def _instruction(ctx: ReadonlyContext) -> str:
    return f"""\
You are the Pattern Analyzer in a pipeline that writes LeetCode "idea cards" for one user.
You see the problem id/title and the user's accepted code, NOT the problem statement.

1. Decide which algorithm pattern THIS code uses (not what other solutions might use).
   Allowed labels: {", ".join(PATTERN_PRESETS)}
2. Call search_cards with that pattern to find problems the user solved before with a similar idea.
   If nothing useful comes back, try one neighbouring pattern. At most 3 tool calls in total.
3. Return the analysis. `related` may only contain slugs that appeared in tool results.

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
