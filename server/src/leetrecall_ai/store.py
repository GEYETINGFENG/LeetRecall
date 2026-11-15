"""Card storage behind a small interface.

Day 1: a JSON file in the extension's own backup format, so a real export can be dropped in.
Day 2: a Qdrant-backed store implements the same Protocol and the MCP layer doesn't change.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path
from typing import Protocol

from .models import Card

SERVER_DIR = Path(__file__).resolve().parents[2]
SEED_BACKUP = SERVER_DIR / "data" / "leetrecall-seed-backup.json"
DEFAULT_STORE = SERVER_DIR / "var" / "cards.json"


class CardStore(Protocol):
    def get(self, slug: str) -> Card | None: ...
    def all(self) -> list[Card]: ...
    def upsert(self, card: Card) -> Card: ...


class JsonCardStore:
    """Whole-file JSON store. Fine for one user's few hundred cards; writes are atomic."""

    def __init__(self, path: Path | str | None = None, seed: Path | None = SEED_BACKUP):
        self.path = Path(path or os.environ.get("LEETRECALL_STORE") or DEFAULT_STORE)
        self._lock = threading.Lock()
        if not self.path.exists():
            # Never write into the committed seed file: copy it to a working location first.
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if seed and seed.exists():
                shutil.copyfile(seed, self.path)
            else:
                self._write({})
        self._cards = self._read()

    def _read(self) -> dict[str, Card]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        cards = raw.get("cards", raw) if isinstance(raw, dict) else {}  # backup format or bare map
        return {slug: Card.model_validate(c) for slug, c in cards.items()}

    def _write(self, cards: dict[str, Card]) -> None:
        payload = {
            "app": "leetrecall",
            "version": 1,
            "exportedAt": int(time.time() * 1000),
            "cards": {s: c.model_dump(mode="json") for s, c in cards.items()},
        }
        # write-to-temp + rename: a crash mid-write can never leave a half-written store
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def get(self, slug: str) -> Card | None:
        return self._cards.get(slug)

    def all(self) -> list[Card]:
        return list(self._cards.values())

    def upsert(self, card: Card) -> Card:
        with self._lock:
            self._cards[card.slug] = card
            self._write(self._cards)
        return card
