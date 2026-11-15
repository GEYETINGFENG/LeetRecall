"""Day 1 spike: does Google ADK drive Claude (claude-opus-5-5) correctly?

Three checks, each a fresh ADK agent run:
  A. function tool calling       -> the core loop every agent will rely on
  B. output_schema, no thinking config      -> ADK's default structured-output path
  C. output_schema, explicit adaptive thinking -> the configuration we plan to use

Run:  cd server && uv run python spikes/adk_claude_spike.py
"""
import asyncio
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import LlmAgent
from google.adk.models import AnthropicGenerateContentConfig
from google.adk.models.anthropic_llm import AnthropicLlm
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

MODEL = "claude-opus-5-5"
SEED = json.loads((Path(__file__).resolve().parents[1] / "data" / "leetrecall-seed-backup.json").read_text())["cards"]


def get_card(slug: str) -> dict:
    """Return the user's saved idea card for a LeetCode problem slug, or an error if it doesn't exist."""
    c = SEED.get(slug)
    if not c:
        return {"error": f"no card for {slug}"}
    return {k: c[k] for k in ("slug", "title", "patterns", "idea", "complexity", "pitfalls")}


class PatternGuess(BaseModel):
    pattern: str
    confidence: float
    reason: str


async def run(agent: LlmAgent, prompt: str) -> dict:
    runner = InMemoryRunner(agent=agent, app_name="spike")
    session = await runner.session_service.create_session(app_name="spike", user_id="u")
    t0 = time.perf_counter()
    tool_calls, final, usage = [], None, {"in": 0, "out": 0}
    async for ev in runner.run_async(
        user_id="u", session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text=prompt)]),
    ):
        for fc in ev.get_function_calls() or []:
            tool_calls.append(f"{fc.name}({json.dumps(fc.args, ensure_ascii=False)})")
        if ev.usage_metadata:
            usage["in"] += ev.usage_metadata.prompt_token_count or 0
            usage["out"] += ev.usage_metadata.candidates_token_count or 0
        if ev.is_final_response() and ev.content and ev.content.parts:
            final = "".join(p.text or "" for p in ev.content.parts if not p.thought)
    return {"latency_s": round(time.perf_counter() - t0, 2), "tool_calls": tool_calls, "usage": usage, "final": final}


async def check(name: str, agent: LlmAgent, prompt: str) -> None:
    print(f"\n=== {name} ===")
    try:
        r = await run(agent, prompt)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    except Exception as e:  # spike: we want to SEE the failure mode, not hide it
        print(f"FAILED: {type(e).__name__}: {str(e)[:400]}")


async def main() -> None:
    llm = AnthropicLlm(model=MODEL, max_tokens=4096)
    adaptive = AnthropicGenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=-1),  # -1 -> thinking: adaptive
        effort="low",
    )

    await check("A. tool calling", LlmAgent(
        name="librarian", model=llm, tools=[get_card],
        instruction="You answer questions about the user's LeetCode idea cards. Always look the card up with get_card first. Reply in one sentence.",
    ), "我之前 daily-temperatures 这题的思路是什么？")

    code = (Path(__file__).resolve().parents[1] / "data" / "eval_solutions" / "largest-rectangle-in-histogram.py").read_text()
    prompt = f"Classify the algorithm pattern this solution uses.\n\n```python\n{code}\n```"

    await check("B. output_schema, default config", LlmAgent(
        name="classifier_default", model=llm, output_schema=PatternGuess,
        instruction="Classify the algorithm pattern of the given code.",
    ), prompt)

    await check("C. output_schema, explicit adaptive thinking", LlmAgent(
        name="classifier_adaptive", model=llm, output_schema=PatternGuess,
        generate_content_config=adaptive,
        instruction="Classify the algorithm pattern of the given code.",
    ), prompt)


if __name__ == "__main__":
    asyncio.run(main())
