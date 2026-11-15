"""Central model configuration. Every agent gets its LLM + generate config from here.

Why one place: claude-opus-5-5 rejects forced tool_choice. ADK's structured-output path only
avoids forcing tool_choice when thinking is explicitly on (see spikes/adk_claude_spike.py), so
an agent that forgets this config fails with a 400. Centralizing makes that impossible to miss.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.models import AnthropicGenerateContentConfig
from google.adk.models.anthropic_llm import AnthropicLlm
from google.genai import types

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MODEL = os.environ.get("LEETRECALL_MODEL", "claude-opus-5-5")
MAX_TOKENS = 16000


def llm() -> AnthropicLlm:
    return AnthropicLlm(model=MODEL, max_tokens=MAX_TOKENS)


def gen_config(effort: str = "medium") -> AnthropicGenerateContentConfig:
    return AnthropicGenerateContentConfig(
        thinking_config=types.ThinkingConfig(thinking_budget=-1),  # -1 -> adaptive thinking
        effort=effort,
    )
