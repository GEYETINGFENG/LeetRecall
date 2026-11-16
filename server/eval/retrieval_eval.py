"""Offline retrieval eval: which embedding model and which query text find the right prior cards?

For each of the 20 held-out problems, query the 35-card library and check whether the retrieved
cards share the problem's gold pattern. No LLM calls — deterministic and free to rerun.

Query variants:
  title  - "Two Sum II ..." : what the extension knows without any AI
  code   - the user's raw code
  hyde   - an idea-style description of the solution (here: the reference idea, i.e. the
           upper bound for a HyDE query the Pattern Analyzer writes itself)

Run:  uv run python eval/retrieval_eval.py [--models m1 m2 ...]
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from qdrant_client import QdrantClient

from leetrecall_ai.rag.index import QdrantCardStore

HERE = Path(__file__).parent
MODELS = ["BAAI/bge-small-zh-v1.5", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
          "jinaai/jina-embeddings-v2-base-zh"]
K = 5


def queries(row: dict) -> dict[str, str]:
    return {"title": f"{row['title']} {row['titleCn']}", "code": row["code"], "hyde": f"思路：{row['reference_idea']}"}


def evaluate(model: str, rows: list[dict]) -> dict:
    t0 = time.perf_counter()
    store = QdrantCardStore(QdrantClient(location=":memory:"), model=model)
    index_s = time.perf_counter() - t0
    out = {}
    for qtype in ("title", "code", "hyde"):
        hit1 = hit3 = rr = 0.0
        lat = []
        per_item = []
        for row in rows:
            t = time.perf_counter()
            res = store.similar(queries(row)[qtype], k=K)
            lat.append((time.perf_counter() - t) * 1000)
            rel = [row["gold_primary"] in c.patterns for c, _ in res]
            first = next((i for i, r in enumerate(rel) if r), None)
            hit1 += rel[0] if rel else 0
            hit3 += any(rel[:3])
            rr += 1 / (first + 1) if first is not None else 0
            per_item.append({"slug": row["slug"], "gold": row["gold_primary"], "top3": [c.slug for c, _ in res[:3]],
                             "first_relevant_rank": None if first is None else first + 1})
        n = len(rows)
        out[qtype] = {"hit@1": round(hit1 / n, 3), "hit@3": round(hit3 / n, 3), f"mrr@{K}": round(rr / n, 3),
                      "query_ms_p50": round(sorted(lat)[n // 2], 1), "items": per_item}
    return {"model": model, "index_build_s": round(index_s, 2), "results": out}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=MODELS)
    a = ap.parse_args()
    rows = [json.loads(l) for l in (HERE / "dataset.jsonl").read_text().splitlines()]
    reviewed = sum(r["reviewed"] for r in rows)
    runs = [evaluate(m, rows) for m in a.models]

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = HERE / "results" / f"retrieval-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw.json").write_text(json.dumps({"n": len(rows), "labels_reviewed": reviewed, "runs": runs},
                                                 ensure_ascii=False, indent=2))
    lines = [f"# Retrieval eval {stamp}", "",
             f"{len(rows)} held-out problems vs 35-card library; relevant = shares the gold pattern. "
             f"Gold labels human-reviewed: {reviewed}/{len(rows)}.", "",
             f"| model | query | hit@1 | hit@3 | MRR@{K} | query p50 (ms) |", "|---|---|---|---|---|---|"]
    for r in runs:
        for q, m in r["results"].items():
            lines.append(f"| {r['model'].split('/')[-1]} | {q} | {m['hit@1']} | {m['hit@3']} | {m[f'mrr@{K}']} | {m['query_ms_p50']} |")
    (out_dir / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {out_dir.relative_to(HERE.parent)}")


if __name__ == "__main__":
    main()
