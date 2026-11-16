"""Agent I/O contracts."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .models import PATTERN_PRESETS

# An enum in the JSON schema: the model literally cannot emit a label outside the extension's list.
Pattern = Literal[*PATTERN_PRESETS]


class ProblemInput(BaseModel):
    """What the extension sends. Deliberately no problem statement — only id/title and the user's own work."""

    slug: str
    id: str = ""
    title: str
    titleCn: str = ""
    difficulty: str = ""
    lang: str = "python3"
    code: str
    notes: str = ""


class RelatedCard(BaseModel):
    slug: str = Field(description="slug of an existing card returned by a tool call")
    why: str = Field(description="one short sentence: what idea the two problems share")


class CardDraft(BaseModel):
    primary_pattern: Pattern = Field(description="the pattern THIS code actually uses")
    patterns: list[Pattern] = Field(min_length=1, max_length=3, description="primary first, then other valid patterns")
    idea: str = Field(description="1-2 sentences in Chinese: the key insight that makes this solution work")
    complexity: str = Field(description="e.g. 时间 O(n) / 空间 O(1), must match the given code")
    pitfalls: str = Field(description="1-2 concrete mistakes to avoid, in Chinese")
    hints: list[str] = Field(min_length=3, max_length=3, description=(
        "3 progressive hints in Chinese, weakest first. They nudge toward the idea but must NOT state it; "
        "the user reads them before flipping the card."))
    related: list[RelatedCard] = Field(default_factory=list, max_length=3)


# ---------- multi-agent contracts ----------

class PatternAnalysis(BaseModel):
    """Pattern Analyzer output: classification + retrieval, no prose for the user."""

    primary_pattern: Pattern = Field(description="the pattern THIS code actually uses")
    patterns: list[Pattern] = Field(min_length=1, max_length=3, description="primary first, then other valid patterns")
    evidence: str = Field(description="which lines/structures in the code show the pattern, 1-2 sentences")
    key_observation: str = Field(description="the insight that makes the approach correct, for the writer; may be a spoiler")
    related: list[RelatedCard] = Field(default_factory=list, max_length=3)


class CardContent(BaseModel):
    """Card Writer output: the user-facing text."""

    idea: str = Field(description="1-2 sentences in Chinese: the key insight that makes this solution work")
    complexity: str = Field(description="e.g. 时间 O(n) / 空间 O(1), must match the given code")
    pitfalls: str = Field(description="1-2 concrete mistakes to avoid, in Chinese")
    hints: list[str] = Field(min_length=3, max_length=3, description="3 progressive hints in Chinese, weakest first, none may reveal the idea")


class HintCheck(BaseModel):
    index: int = Field(ge=1, le=3)
    spoils: bool = Field(description="true if a user who forgot the solution could write the algorithm from this hint alone")
    why: str


class CriticVerdict(BaseModel):
    """Critic output. Component judgments only — whether the card passes is decided in code."""

    idea_correct: bool = Field(description="the idea accurately describes what the given code does and why it works")
    complexity_correct: bool = Field(description="the stated complexity matches the given code")
    pattern_correct: bool = Field(description="the primary pattern label fits the given code")
    hint_checks: list[HintCheck] = Field(min_length=3, max_length=3)
    issues: list[str] = Field(description="every concrete problem found, empty if none")
    fix_instructions: str = Field(description="what the writer must change; empty if nothing")
