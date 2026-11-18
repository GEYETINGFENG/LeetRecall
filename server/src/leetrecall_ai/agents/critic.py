"""Critic + Gate: self-reflection loop.

The Critic (LLM) gives component judgments. The Gate (plain code) decides pass/fail from them and
ends the loop by escalating. Keeping the decision in code means the LLM can't say "passed" while
listing issues, and the stop rule is testable without an API call.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from google.adk.agents import BaseAgent, LlmAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.events import Event, EventActions
from pydantic import ValidationError

from .. import config
from ..schemas import CriticVerdict
from .card_writer import RULES
from .common import ANALYSIS, DATA_NOT_INSTRUCTIONS, DRAFT, PROBLEM, ROUNDS, VERDICT, as_json, render_problem


def _instruction(ctx: ReadonlyContext) -> str:
    s = ctx.state
    a = s[ANALYSIS]
    return f"""\
You are a strict reviewer of LeetCode "idea cards". Check the draft against the user's code.
You did not write it; do not assume it is right.

Check:
1. idea_correct: does the idea accurately explain why THIS code works? Wrong or vague = false.
2. complexity_correct: does it match THIS code? Work it out yourself first.
3. pattern_correct: does the label "{a['primary_pattern'] if isinstance(a, dict) else a.primary_pattern}" fit THIS code?
4. hint_checks: judge each hint separately against the hint rule below. Be strict: naming the data
   structure/technique, stating the invariant, or giving away the key trick are all spoilers.

The writer was given these rules:
{RULES}

Report every concrete issue. fix_instructions must tell the writer exactly what to change.
Do not nitpick wording that is correct and clear.

{DATA_NOT_INSTRUCTIONS}

{render_problem(s[PROBLEM])}

Draft to review:
{as_json(s[DRAFT])}"""


def build_critic() -> LlmAgent:
    return LlmAgent(
        name="critic",
        description="Checks accuracy and whether hints spoil the idea.",
        model=config.llm(),
        generate_content_config=config.gen_config("high"),  # verification is where depth pays off
        instruction=_instruction,
        include_contents="none",
        output_schema=CriticVerdict,
        output_key=VERDICT,
    )


def passed(v: CriticVerdict | dict) -> bool:
    v = CriticVerdict.model_validate(v)
    return v.idea_correct and v.complexity_correct and v.pattern_correct and not any(h.spoils for h in v.hint_checks)


def review_round(verdict: object, draft: object) -> dict:
    """One round's record. A malformed verdict counts as 'not passed' instead of crashing the request.

    With thinking on, ADK can't force the structured-output tool, so the API does not enforce the
    schema; the eval caught a verdict with 1 hint check instead of 3 (1 of 60 Critic runs). Failing
    closed keeps the loop going (the next round re-reviews) and the request still returns a card.
    """
    try:
        return {"draft": draft, "verdict": verdict, "passed": passed(verdict), "malformed": False}
    except ValidationError as e:
        return {"draft": draft, "verdict": verdict, "passed": False, "malformed": True,
                "error": " ".join(str(e).splitlines()[:3])}  # "N validation errors ... <field> <reason>"


class Gate(BaseAgent):
    """Deterministic loop controller: records the round, exits the loop when the verdict passes."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        s = ctx.session.state
        rec = review_round(s[VERDICT], s[DRAFT])
        delta = {ROUNDS: list(s.get(ROUNDS, [])) + [rec]}
        if rec["malformed"]:
            delta[VERDICT] = None  # don't feed the writer an unparseable review; it redrafts cleanly
        yield Event(
            author=self.name, invocation_id=ctx.invocation_id,
            actions=EventActions(state_delta=delta, escalate=rec["passed"]),
        )
