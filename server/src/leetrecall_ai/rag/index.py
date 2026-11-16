"""Qdrant-backed CardStore: one collection holds both the cards (payload) and their idea vectors.

Trade-off: Qdrant isn't a primary database (no transactions), but for one user's few hundred cards
colocating storage and retrieval removes a whole service from the deployment. Multi-user would
move cards to Firestore/Postgres and keep Qdrant as a pure index.

Connection (first match wins):
  QDRANT_URL (+ QDRANT_API_KEY)  -> Qdrant server / Qdrant Cloud (production)
  QDRANT_PATH                    -> embedded local mode, single process (dev)
  ":memory:"                     -> tests
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from ..models import Card
from ..store import SEED_BACKUP, SERVER_DIR
from .embed import DEFAULT_MODEL, card_text, dim, embed

COLLECTION = "cards"
DEFAULT_PATH = SERVER_DIR / "var" / "qdrant"


def point_id(slug: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"leetrecall:{slug}"))  # stable: re-upserting overwrites


def make_client(location: str | None = None) -> QdrantClient:
    if location != ":memory:" and (url := os.environ.get("QDRANT_URL")):
        return QdrantClient(url=url, api_key=os.environ.get("QDRANT_API_KEY"))
    path = location or os.environ.get("QDRANT_PATH") or str(DEFAULT_PATH)
    if path == ":memory:":  # also lets eval runs get an isolated, seeded store per process
        return QdrantClient(location=":memory:")
    Path(path).mkdir(parents=True, exist_ok=True)
    return QdrantClient(path=path)


class QdrantCardStore:
    def __init__(self, client: QdrantClient | None = None, *, model: str = DEFAULT_MODEL,
                 collection: str = COLLECTION, seed: Path | None = SEED_BACKUP):
        self.client = client or make_client()
        self.model = model
        self.collection = collection
        if not self.client.collection_exists(collection):
            self.client.create_collection(collection, vectors_config=qm.VectorParams(size=dim(model), distance=qm.Distance.COSINE))
            # embedded mode ignores payload indexes (and warns); they matter on a real server
            if os.environ.get("QDRANT_URL"):
                self.client.create_payload_index(collection, "patterns", qm.PayloadSchemaType.KEYWORD)
                self.client.create_payload_index(collection, "has_idea", qm.PayloadSchemaType.BOOL)
            if seed and seed.exists():
                self.upsert_many([Card.model_validate(c) for c in json.loads(seed.read_text())["cards"].values()])

    # ----- CardStore protocol -----
    def get(self, slug: str) -> Card | None:
        recs = self.client.retrieve(self.collection, [point_id(slug)], with_payload=True)
        return Card.model_validate(recs[0].payload["card"]) if recs else None

    def all(self) -> list[Card]:
        out, offset = [], None
        while True:
            recs, offset = self.client.scroll(self.collection, limit=256, offset=offset, with_payload=True)
            out += [Card.model_validate(r.payload["card"]) for r in recs]
            if offset is None:
                return out

    def upsert(self, card: Card) -> Card:
        self.upsert_many([card])
        return card

    def upsert_many(self, cards: list[Card]) -> None:
        if not cards:
            return
        vectors = embed([card_text(c) for c in cards], self.model)
        self.client.upsert(self.collection, [
            qm.PointStruct(id=point_id(c.slug), vector=v, payload={
                "slug": c.slug, "patterns": c.patterns, "has_idea": bool(c.idea),
                "card": c.model_dump(mode="json"),
            }) for c, v in zip(cards, vectors)])

    # ----- retrieval -----
    def similar(self, text: str, *, k: int = 5, exclude_slug: str = "", pattern: str = "",
                min_score: float = 0.0) -> list[tuple[Card, float]]:
        must = [qm.FieldCondition(key="has_idea", match=qm.MatchValue(value=True))]  # empty cards are noise
        if pattern:
            must.append(qm.FieldCondition(key="patterns", match=qm.MatchValue(value=pattern)))
        must_not = [qm.HasIdCondition(has_id=[point_id(exclude_slug)])] if exclude_slug else []
        res = self.client.query_points(
            self.collection, query=embed([text], self.model)[0], limit=k, with_payload=True,
            query_filter=qm.Filter(must=must, must_not=must_not), score_threshold=min_score or None)
        return [(Card.model_validate(p.payload["card"]), round(p.score, 4)) for p in res.points]
