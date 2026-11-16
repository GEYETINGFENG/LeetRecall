"""Card Writer: turn the analysis into the user-facing card text. No tools.

On a revision round it also sees its previous draft and the Critic's verdict.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext

from .. import config
from ..schemas import CardContent
from .common import ANALYSIS, DATA_NOT_INSTRUCTIONS, DRAFT, PROBLEM, VERDICT, as_json, render_problem

RULES = """\
Write in Chinese, concise, like a note to self.
- idea: 1-2 sentences, the insight that makes THIS code correct (not a code walkthrough).
- complexity: must match THIS code, not the best known solution.
- pitfalls: 1-2 concrete bugs this code avoids.
- hints: exactly 3, shown BEFORE the user flips the card, weakest first. A hint may point at what to
  look at or ask a guiding question about a property of the problem. A hint must NEVER name the
  technique or data structure, state the invariant, or give a formula/trick from the idea. Test:
  if a user who forgot the solution could write the algorithm from the hint alone, it is a spoiler."""


def _instruction(ctx: ReadonlyContext) -> str:
    s = ctx.state
    base = f"""\
You are the Card Writer in a pipeline that writes LeetCode "idea cards" for one user.

{RULES}

{DATA_NOT_INSTRUCTIONS}

{render_problem(s[PROBLEM])}

Pattern analysis (from the analyzer; key_observation may be a spoiler and is for you only):
{as_json(s[ANALYSIS])}"""
    if s.get(VERDICT):  # revision round
        base += f"""

REVISION. Your previous draft was rejected by the reviewer.
Previous draft:
{as_json(s[DRAFT])}
Reviewer verdict:
{as_json(s[VERDICT])}
Fix every issue the reviewer listed. Keep what was not criticized."""
    return base


def build() -> LlmAgent:
    return LlmAgent(
        name="card_writer",
        description="Writes the idea, complexity, pitfalls and progressive hints.",
        model=config.llm(),
        generate_content_config=config.gen_config("medium"),
        instruction=_instruction,
        include_contents="none",
        output_schema=CardContent,
        output_key=DRAFT,
    )
