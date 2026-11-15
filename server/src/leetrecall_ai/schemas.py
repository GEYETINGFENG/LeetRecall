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
