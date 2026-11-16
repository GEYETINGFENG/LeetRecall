"""Per-request LLM metrics, computed from the request's OpenTelemetry spans.

Source of truth for tokens is the Claude SDK span (`anthropic.messages.create`), which records the
API's own `usage`. Cost = tokens x the price of the model that actually SERVED the call
(`gen_ai.response.model`), never the configured one.

Definitions (stated so the numbers are reproducible):
  latency_s          wall clock of the whole request (root span)
  output_tok_per_s   sum(output tokens) / sum(model-call durations). Non-streaming, so each call's
                     duration includes time to first token: this is end-to-end generation throughput.
  cost_usd           sum over calls of uncached_in*in + cache_write*in*1.25 + cache_read*cache_read + out*out
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from opentelemetry.sdk.trace import ReadableSpan

# USD per 1M tokens, Anthropic first-party API (claude-api skill price table, cached 2026-11-03).
PRICES: dict[str, dict[str, float]] = {
    "claude-opus-5-5": {"in": 4.00, "out": 20.00, "cache_read": 0.20},
    "claude-fable-5-2": {"in": 8.00, "out": 40.00, "cache_read": 0.20},
    "claude-sonnet-5-5": {"in": 2.00, "out": 10.00, "cache_read": 0.10},
    "claude-haiku-5-5": {"in": 0.10, "out": 0.50, "cache_read": 0.01},
}
CACHE_WRITE_MULT = 1.25


@dataclass
class LlmCall:
    agent: str
    model: str
    input_tokens: int  # includes cache reads and writes
    cache_read: int
    cache_write: int
    output_tokens: int
    duration_s: float
    stop_reason: str
    cost_usd: float


@dataclass
class AgentStats:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    model_time_s: float = 0.0
    agent_time_s: float = 0.0  # sum of the agent's invoke spans (all loop rounds)


@dataclass
class RequestMetrics:
    latency_s: float
    llm_calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cost_usd: float
    output_tok_per_s: float
    tool_time_s: dict[str, float]
    per_agent: dict[str, AgentStats]
    models_served: list[str]
    truncated_calls: int  # calls that stopped at max_tokens: their output is clipped, not "wrong"
    calls: list[LlmCall] = field(default_factory=list)

    def to_dict(self, with_calls: bool = False) -> dict:
        d = asdict(self)
        if not with_calls:
            d.pop("calls")
        return d


def call_cost(model: str, input_tokens: int, cache_read: int, cache_write: int, output_tokens: int) -> float:
    p = PRICES.get(model)
    if p is None:
        raise KeyError(f"no price for model {model!r}; add it to PRICES")  # fail loud, never a silent $0
    uncached = max(0, input_tokens - cache_read - cache_write)
    return (uncached * p["in"] + cache_write * p["in"] * CACHE_WRITE_MULT
            + cache_read * p["cache_read"] + output_tokens * p["out"]) / 1e6


def _dur(s: ReadableSpan) -> float:
    return (s.end_time - s.start_time) / 1e9


def compute(spans: list[ReadableSpan], root_name: str = "generate_card") -> RequestMetrics:
    by_id = {s.context.span_id: s for s in spans}

    def agent_of(s: ReadableSpan) -> str:
        p = s.parent
        while p and p.span_id in by_id:
            a = by_id[p.span_id].attributes or {}
            if a.get("gen_ai.operation.name") in ("invoke_agent", "generate_content") and a.get("gen_ai.agent.name"):
                return str(a["gen_ai.agent.name"])
            p = by_id[p.span_id].parent
        return "unknown"

    calls, per_agent, tools = [], {}, {}
    for s in spans:
        a = s.attributes or {}
        if s.name == "anthropic.messages.create":
            model = str(a.get("gen_ai.response.model") or a.get("gen_ai.request.model"))
            it, ot = int(a.get("gen_ai.usage.input_tokens", 0)), int(a.get("gen_ai.usage.output_tokens", 0))
            cr = int(a.get("gen_ai.usage.cache_read.input_tokens", 0))
            cw = int(a.get("gen_ai.usage.cache_write.input_tokens", 0))
            c = LlmCall(agent_of(s), model, it, cr, cw, ot, _dur(s), str(a.get("anthropic.message.stop_reason", "")),
                        call_cost(model, it, cr, cw, ot))
            calls.append(c)
            st = per_agent.setdefault(c.agent, AgentStats())
            st.calls += 1
            st.input_tokens += it
            st.output_tokens += ot
            st.cost_usd += c.cost_usd
            st.model_time_s += c.duration_s
        elif a.get("gen_ai.operation.name") == "invoke_agent" and (name := a.get("gen_ai.agent.name")):
            per_agent.setdefault(str(name), AgentStats()).agent_time_s += _dur(s)
        elif a.get("gen_ai.operation.name") == "execute_tool" and (tool := a.get("gen_ai.tool.name")):
            tools[str(tool)] = tools.get(str(tool), 0.0) + _dur(s)

    root = next((s for s in spans if s.name == root_name), None)
    model_time = sum(c.duration_s for c in calls)
    out = sum(c.output_tokens for c in calls)
    for st in per_agent.values():
        st.cost_usd = round(st.cost_usd, 6)
        st.model_time_s, st.agent_time_s = round(st.model_time_s, 2), round(st.agent_time_s, 2)
    return RequestMetrics(
        latency_s=round(_dur(root), 2) if root else round(model_time, 2),
        llm_calls=len(calls),
        input_tokens=sum(c.input_tokens for c in calls),
        output_tokens=out,
        cache_read_tokens=sum(c.cache_read for c in calls),
        cost_usd=round(sum(c.cost_usd for c in calls), 6),
        output_tok_per_s=round(out / model_time, 1) if model_time else 0.0,
        tool_time_s={k: round(v, 3) for k, v in tools.items()},
        per_agent={k: v for k, v in per_agent.items() if k != "coordinator"},
        models_served=sorted({c.model for c in calls}),
        truncated_calls=sum(c.stop_reason == "max_tokens" for c in calls),
        calls=calls,
    )
