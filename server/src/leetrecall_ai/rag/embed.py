"""Local text embeddings (fastembed / ONNX, CPU). No API key, no per-call cost, works offline.

The default model was picked by eval/retrieval_eval.py, not by guesswork — see README.
"""
from __future__ import annotations

import os
from functools import lru_cache

from fastembed import TextEmbedding

from ..models import Card

DEFAULT_MODEL = os.environ.get("LEETRECALL_EMBED_MODEL", "BAAI/bge-small-zh-v1.5")


@lru_cache(maxsize=4)
def _model(name: str) -> TextEmbedding:
    return TextEmbedding(model_name=name, cache_dir=os.environ.get("FASTEMBED_CACHE_PATH"))


def embed(texts: list[str], model: str = DEFAULT_MODEL) -> list[list[float]]:
    return [v.tolist() for v in _model(model).embed(texts)]


def dim(model: str = DEFAULT_MODEL) -> int:
    return len(embed(["x"], model)[0])


def card_text(c: Card) -> str:
    """What a card is 'about' for similarity: the idea, not the code or the title.

    We want "problems I solved with a similar idea", so the vector is built from the user's own
    idea/pattern/pitfall notes. Code is excluded: two monotonic-stack solutions look nothing alike
    token-wise, and titles say little about technique.
    """
    parts = [f"套路：{'、'.join(c.patterns)}" if c.patterns else "", f"思路：{c.idea}" if c.idea else "",
             f"易错：{c.pitfalls}" if c.pitfalls else ""]
    return "\n".join(p for p in parts if p) or c.title
