"""Run an ADK agent once and collect what we need for debugging and metrics."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.runners import InMemoryRunner
from google.genai import types


@dataclass
class ToolCall:
    agent: str
    name: str
    args: dict[str, Any]
    is_error: bool = False
    response: Any = None


@dataclass
class RunTrace:
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0  # excludes thinking tokens (ADK reports them separately)
    thinking_tokens: int = 0
    llm_calls: int = 0
    tool_calls: list[ToolCall] = field(default_factory=list)
    final_text: str = ""
    state: dict[str, Any] = field(default_factory=dict)


def _slugs_in(obj: Any) -> set[str]:
    """Every value under a 'slug' key anywhere in a tool response."""
    out: set[str] = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "slug" and isinstance(v, str):
                out.add(v)
            else:
                out |= _slugs_in(v)
    elif isinstance(obj, list):
        for v in obj:
            out |= _slugs_in(v)
    return out


def seen_slugs(trace: RunTrace) -> set[str]:
    return set().union(*(_slugs_in(tc.response) for tc in trace.tool_calls if not tc.is_error))


async def run_once(agent: BaseAgent, prompt: str, app_name: str = "leetrecall") -> RunTrace:
    runner = InMemoryRunner(agent=agent, app_name=app_name)
    session = await runner.session_service.create_session(app_name=app_name, user_id="user")
    trace = RunTrace()
    pending: dict[str, ToolCall] = {}
    t0 = time.perf_counter()
    async for ev in runner.run_async(
        user_id="user", session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        if ev.usage_metadata and not ev.partial:
            trace.llm_calls += 1
            trace.input_tokens += ev.usage_metadata.prompt_token_count or 0
            trace.output_tokens += ev.usage_metadata.candidates_token_count or 0
            trace.thinking_tokens += ev.usage_metadata.thoughts_token_count or 0
        for fc in ev.get_function_calls() or []:
            tc = ToolCall(agent=ev.author, name=fc.name, args=dict(fc.args or {}))
            pending[fc.id or str(uuid.uuid4())] = tc
            trace.tool_calls.append(tc)
        for fr in ev.get_function_responses() or []:
            tc = pending.get(fr.id)
            if tc:
                resp = fr.response or {}
                tc.response = resp
                tc.is_error = bool(resp.get("isError") or resp.get("is_error") or "error" in resp)
        if ev.is_final_response() and ev.content and ev.content.parts:
            trace.final_text = "".join(p.text or "" for p in ev.content.parts if not p.thought)
    trace.latency_s = round(time.perf_counter() - t0, 2)
    final = await runner.session_service.get_session(app_name=app_name, user_id="user", session_id=session.id)
    trace.state = dict(final.state) if final else {}
    return trace


def dump(trace: RunTrace) -> str:
    calls = [f"{tc.agent}: {tc.name}({json.dumps(tc.args, ensure_ascii=False)}){' -> ERROR' if tc.is_error else ''}"
             for tc in trace.tool_calls]
    return json.dumps({
        "latency_s": trace.latency_s, "llm_calls": trace.llm_calls,
        "tokens": {"input": trace.input_tokens, "output": trace.output_tokens, "thinking": trace.thinking_tokens},
        "tool_calls": calls,
    }, ensure_ascii=False, indent=2)
