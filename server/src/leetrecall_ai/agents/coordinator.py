"""Coordinator: the full multi-agent pipeline.

    coordinator (SequentialAgent)
    ├── pattern_analyzer  (LlmAgent + read-only MCP tools)  -> state.analysis
    └── review_loop (LoopAgent, max_iterations=N)            [critic on]
        ├── card_writer   (LlmAgent, no tools)              -> state.draft
        ├── critic        (LlmAgent, no tools)              -> state.verdict
        └── gate          (code: pass -> escalate)          -> state.rounds
    critic off: coordinator = [pattern_analyzer, card_writer]  (the eval baseline)

Run:  uv run python -m leetrecall_ai.agents.coordinator largest-rectangle-in-histogram [--no-critic] [--rounds 3]
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from google.adk.agents import LoopAgent, SequentialAgent
from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
from pydantic import BaseModel

from ..obs import metrics as obs_metrics
from ..obs.tracing import setup_tracing, tracer
from ..schemas import CardContent, CardDraft, PatternAnalysis, ProblemInput
from . import card_writer, critic, pattern_analyzer
from .common import ANALYSIS, DRAFT, PROBLEM, ROUNDS, mcp_params
from .runtime import RunTrace, dump, run_once, seen_slugs

DATASET = Path(__file__).resolve().parents[3] / "eval" / "dataset.jsonl"


class CriticReport(BaseModel):
    enabled: bool
    rounds: int
    passed: bool | None  # None when critic is off
    history: list[dict[str, Any]]


class CardResult(BaseModel):
    draft: CardDraft
    critic: CriticReport
    dropped_related: list[str]
    metrics: dict[str, Any]  # from OpenTelemetry spans: latency, tokens, cost, tokens/sec, per agent
    trace_id: str  # look this up in Cloud Trace
    trace: dict[str, Any]


def build_pipeline(toolset: McpToolset, *, use_critic: bool, max_rounds: int) -> SequentialAgent:
    analyzer = pattern_analyzer.build(toolset)
    writer = card_writer.build()
    if not use_critic:
        return SequentialAgent(name="coordinator", sub_agents=[analyzer, writer])
    loop = LoopAgent(name="review_loop", max_iterations=max_rounds,
                     sub_agents=[writer, critic.build_critic(), critic.Gate(name="gate")])
    return SequentialAgent(name="coordinator", sub_agents=[analyzer, loop])


def assemble(problem: ProblemInput, trace: RunTrace, use_critic: bool, metrics: dict, trace_id: str) -> CardResult:
    s = trace.state
    analysis = PatternAnalysis.model_validate(s[ANALYSIS])
    content = CardContent.model_validate(s[DRAFT])
    grounded = seen_slugs(trace)  # related cards must come from an actual tool result
    draft = CardDraft(primary_pattern=analysis.primary_pattern, patterns=analysis.patterns,
                      **content.model_dump(), related=[r for r in analysis.related if r.slug in grounded])
    rounds = s.get(ROUNDS, [])
    return CardResult(
        draft=draft,
        critic=CriticReport(enabled=use_critic, rounds=len(rounds) if use_critic else 1,
                            passed=rounds[-1]["passed"] if rounds else None, history=rounds),
        dropped_related=[r.slug for r in analysis.related if r.slug not in grounded],
        metrics=metrics, trace_id=trace_id,
        trace=json.loads(dump(trace)),
    )


async def generate_card(problem: ProblemInput, *, use_critic: bool = True, max_rounds: int = 3) -> CardResult:
    collector = setup_tracing()
    toolset = McpToolset(connection_params=StdioConnectionParams(server_params=mcp_params(), timeout=30),
                         tool_filter=pattern_analyzer.READ_TOOLS)
    with tracer().start_as_current_span("generate_card", attributes={
            "leetrecall.slug": problem.slug, "leetrecall.critic": use_critic, "leetrecall.max_rounds": max_rounds}) as root:
        trace_id = root.get_span_context().trace_id
        try:
            pipeline = build_pipeline(toolset, use_critic=use_critic, max_rounds=max_rounds)
            trace = await run_once(pipeline, "Write the idea card for this problem.",
                                   state={PROBLEM: problem.model_dump()})
        finally:
            await toolset.close()
        rounds = len(trace.state.get(ROUNDS, [])) if use_critic else 1
        root.set_attribute("leetrecall.rounds", rounds)
    m = obs_metrics.compute(collector.pop(trace_id)).to_dict()
    return assemble(problem, trace, use_critic, m, format(trace_id, "032x"))


def load_problem(slug: str) -> ProblemInput:
    for line in DATASET.read_text().splitlines():
        row = json.loads(line)
        if row["slug"] == slug:
            return ProblemInput.model_validate(row)
    raise SystemExit(f"{slug} not in {DATASET}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--no-critic", action="store_true")
    ap.add_argument("--rounds", type=int, default=3)
    a = ap.parse_args()
    r = await generate_card(load_problem(a.slug), use_critic=not a.no_critic, max_rounds=a.rounds)
    print(json.dumps(r.trace["tool_calls"], ensure_ascii=False, indent=2))
    print("metrics:", json.dumps(r.metrics, ensure_ascii=False, indent=2))
    for i, rd in enumerate(r.critic.history, 1):
        v = rd["verdict"]
        if rd.get("malformed"):
            print(f"\n--- round {i}: critic verdict malformed ({rd.get('error')}), treated as not passed")
            continue
        spoilers = [h["index"] for h in v["hint_checks"] if h["spoils"]]
        print(f"\n--- round {i}: passed={rd['passed']} idea={v['idea_correct']} cx={v['complexity_correct']} "
              f"pattern={v['pattern_correct']} spoiler_hints={spoilers}")
        print("hints:", json.dumps(rd["draft"]["hints"], ensure_ascii=False))
        if v["issues"]:
            print("issues:", json.dumps(v["issues"], ensure_ascii=False))
    print("\nFINAL:", r.draft.model_dump_json(indent=2))
    print("critic:", r.critic.model_dump(exclude={"history"}), "| dropped_related:", r.dropped_related)


if __name__ == "__main__":
    asyncio.run(main())
