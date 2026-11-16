"""Eval runner: does the Critic loop make cards better? (20 held-out problems x R reps x 2 variants)

  baseline = analyzer -> writer (no Critic)
  v1       = analyzer -> [writer -> critic -> gate] x max 3 rounds

Usage (from server/):
  uv run python eval/run_eval.py --variant baseline --reps 3
  uv run python eval/run_eval.py --variant v1 --reps 3
  uv run python eval/run_eval.py --summarize            # table + paired deltas -> runs/card-gen/summary.md
  uv run python eval/run_eval.py --judge-selftest       # known-good / known-bad cards through the judge
  add --limit 3 for a pilot

Harness gate: the first run, and any run after the runner, judge, pipeline code, lockfile or dataset
changed, exits 2 until YOU re-run with --approve-harness (that approval is the user's call).

Layout (runs/card-gen/<variant>/): results.jsonl (one row per case x rep, written as it completes,
resume-safe), errors.jsonl (attempts that produced nothing scorable: timeout / api_error / refusal /
model_mismatch / judge_fallback — never scored as 0), traces/<slug>_rep<k>.json.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import random
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("QDRANT_PATH", ":memory:")  # each case's MCP server gets its own seeded, isolated index
os.environ.setdefault("LEETRECALL_STORE_BACKEND", "qdrant")

import anthropic  # noqa: E402

HERE = Path(__file__).resolve().parent
SERVER = HERE.parent
sys.path.insert(0, str(HERE))
from judge import JUDGE_MODEL, grades, judge  # noqa: E402

from leetrecall_ai import config  # noqa: E402
from leetrecall_ai.agents.common import render_problem  # noqa: E402
from leetrecall_ai.agents.coordinator import generate_card  # noqa: E402
from leetrecall_ai.obs.metrics import call_cost  # noqa: E402
from leetrecall_ai.schemas import ProblemInput  # noqa: E402

FLOW = HERE / "runs" / "card-gen"
VARIANTS = {"baseline": {"use_critic": False}, "v1": {"use_critic": True, "max_rounds": 3}}
HARNESS = ["eval/run_eval.py", "eval/judge.py", "eval/dataset.jsonl", "uv.lock", "src/leetrecall_ai"]
METRICS = [
    {"id": "card_pass", "label": "card pass", "kind": "binary"},
    {"id": "no_spoiler", "label": "no spoiler", "kind": "binary"},
    {"id": "idea_correct", "label": "idea ok", "kind": "binary"},
    {"id": "complexity_correct", "label": "complexity ok", "kind": "binary"},
    {"id": "hints_helpful", "label": "hints helpful", "kind": "binary"},
    {"id": "pattern_strict", "label": "pattern", "kind": "binary"},
    {"id": "pattern_lenient", "label": "pattern (len.)", "kind": "binary"},
    {"id": "spoiler_hint_frac", "label": "spoiler hints", "kind": "float", "scale": 1, "better": "lower"},
]
PERF = [{"id": "latency_s", "label": "latency", "unit": "s"}, {"id": "cost_usd", "label": "cost", "unit": "$"},
        {"id": "output_tok_per_s", "label": "out tok/s"}, {"id": "rounds", "label": "rounds"},
        {"id": "judge_cost_usd", "label": "judge $", "unit": "$"}]


# ---------------- harness gate ----------------

def harness_sha() -> str:
    h = hashlib.sha256()
    for rel in HARNESS:
        p = SERVER / rel
        for f in sorted(p.rglob("*.py")) if p.is_dir() else [p]:
            h.update(str(f.relative_to(SERVER)).encode())
            h.update(f.read_bytes())
    return h.hexdigest()


def gate(approve: bool) -> None:
    FLOW.mkdir(parents=True, exist_ok=True)
    sp = FLOW / "_state.json"
    state = json.loads(sp.read_text()) if sp.exists() else {}
    sha = harness_sha()
    if state.get("harness_sha") != sha:
        if not approve:
            print("Harness changed (or first run). Review the runner, judge and pipeline, then re-run with "
                  "--approve-harness.", file=sys.stderr)
            sys.exit(2)
        state["harness_sha"] = sha
    state.update({"metrics": METRICS, "perf_fields": PERF, "harness_paths": HARNESS,
                  "prices": {"claude-opus-5-5": {"in": 4.0, "out": 20.0}, "claude-fable-5-2": {"in": 8.0, "out": 40.0}}})
    sp.write_text(json.dumps(state, indent=2))


# ---------------- one case ----------------

def load_rows() -> list[dict]:
    return [json.loads(line) for line in (HERE / "dataset.jsonl").read_text().splitlines()]


def trace_turns(row: dict, r, verdict, expl) -> list[dict]:
    turns = [{"role": "user", "content": render_problem(row)}]
    for tc in r.trace["tool_calls"]:
        turns.append({"role": "tool_call", "name": tc.split("(")[0], "content": tc})
    for i, rd in enumerate(r.critic.history, 1):
        turns.append({"role": "assistant", "name": f"card_writer (round {i})",
                      "content": json.dumps(rd["draft"], ensure_ascii=False, indent=2)})
        turns.append({"role": "assistant", "name": f"critic (round {i}, passed={rd['passed']})",
                      "content": json.dumps(rd["verdict"], ensure_ascii=False, indent=2)})
    turns.append({"role": "assistant", "name": "final card", "content": r.draft.model_dump_json(indent=2)})
    turns.append({"role": "assistant", "name": f"judge ({JUDGE_MODEL})",
                  "content": json.dumps({"verdict": verdict.model_dump(), "explanation": expl}, ensure_ascii=False, indent=2)})
    return turns


async def run_case(row: dict, rep: int, variant: str, client: anthropic.AsyncAnthropic) -> tuple[str, dict]:
    """Returns ("ok"|<failure class>, row-or-error-dict)."""
    t0 = time.perf_counter()
    r = await generate_card(ProblemInput.model_validate(row), **VARIANTS[variant])
    m = r.metrics
    base = {"prompt_id": row["slug"], "rep": rep, "variant": variant, "model": ",".join(m["models_served"]),
            "usage": {"input_tokens": m["input_tokens"], "output_tokens": m["output_tokens"],
                      "cache_read_input_tokens": m["cache_read_tokens"], "cache_creation_input_tokens": 0},
            "cost_usd": m["cost_usd"], "trace_id": r.trace_id}
    if m["models_served"] != [config.MODEL]:
        return "model_mismatch", {**base, "error": f"served {m['models_served']}, asked {config.MODEL}"}
    j = await judge(client, row, r.draft.model_dump())
    judge_cost = call_cost(j.model, j.usage["input_tokens"], j.usage["cache_read_input_tokens"],
                           j.usage["cache_creation_input_tokens"], j.usage["output_tokens"]) if j.model in (JUDGE_MODEL,) else None
    base |= {"judge_model": j.model, "judge_usage": j.usage, "judge_cost_usd": judge_cost}
    if j.fallback_used or j.model != JUDGE_MODEL:
        return "judge_fallback", {**base, "error": f"judge served by {j.model}"}
    if j.verdict is None:
        return "refusal", {**base, "error": f"judge stop_reason={j.stop_reason}"}
    truncated = j.stop_reason == "max_tokens" or m["truncated_calls"] > 0
    g, expl = grades(row, r.draft.model_dump(), j.verdict)
    out = {**base, "prompt": render_problem(row), "tags": [row["gold_primary"], row["difficulty"]],
           "stop_reason": "end_turn", "status": "truncated" if truncated else "ok",
           "grade": g, "explanation": expl, "latency_s": m["latency_s"],
           "output_tok_per_s": m["output_tok_per_s"], "rounds": r.critic.rounds, "critic_passed": r.critic.passed,
           "per_agent": m["per_agent"], "draft": r.draft.model_dump(), "wall_s": round(time.perf_counter() - t0, 2)}
    tdir = FLOW / variant / "traces"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / f"{row['slug']}_rep{rep}.json").write_text(
        json.dumps(trace_turns(row, r, j.verdict, expl), ensure_ascii=False, indent=2))
    return "ok", out


async def run_variant(variant: str, reps: int, limit: int | None, concurrency: int, timeout_s: float) -> None:
    vdir = FLOW / variant
    vdir.mkdir(parents=True, exist_ok=True)
    res_p, err_p = vdir / "results.jsonl", vdir / "errors.jsonl"
    done = {(d["prompt_id"], d["rep"]) for d in map(json.loads, res_p.read_text().splitlines())} if res_p.exists() else set()
    rows = load_rows()[:limit] if limit else load_rows()
    todo = [(row, rep) for rep in range(reps) for row in rows if (row["slug"], rep) not in done]
    print(f"{variant}: {len(todo)} to run ({len(done)} already done), concurrency {concurrency}")
    client = anthropic.AsyncAnthropic(max_retries=5)  # SDK retries 429/5xx with jittered exponential backoff
    sem, lock = asyncio.Semaphore(concurrency), asyncio.Lock()
    t_start = time.perf_counter()

    async def one(row: dict, rep: int) -> None:
        async with sem:
            await asyncio.sleep(random.random())  # de-synchronize starts
            try:
                status, rec = await asyncio.wait_for(run_case(row, rep, variant, client), timeout_s)
            except TimeoutError:
                status, rec = "timeout", {"prompt_id": row["slug"], "rep": rep, "error": f">{timeout_s}s"}
            except anthropic.APIError as e:
                status, rec = "api_error", {"prompt_id": row["slug"], "rep": rep, "error": f"{type(e).__name__}: {e}"[:500]}
            except Exception as e:  # harness bug: record it, don't score it
                status, rec = "harness_error", {"prompt_id": row["slug"], "rep": rep, "error": f"{type(e).__name__}: {e}"[:500]}
            async with lock:
                target = res_p if status == "ok" else err_p
                with target.open("a") as f:
                    f.write(json.dumps(rec if status == "ok" else {"failure": status, **rec}, ensure_ascii=False) + "\n")
            mark = f"card_pass={rec['grade']['card_pass']:.0f} {rec['latency_s']}s ${rec['cost_usd']:.3f}" if status == "ok" else status.upper()
            print(f"  [{variant}] {row['slug']} rep{rep}: {mark}", flush=True)

    await asyncio.gather(*(one(row, rep) for row, rep in todo))
    print(f"{variant}: wall clock {time.perf_counter() - t_start:.0f}s")


# ---------------- summary ----------------

def load_results(variant: str) -> list[dict]:
    p = FLOW / variant / "results.jsonl"
    return [d for d in map(json.loads, p.read_text().splitlines())] if p.exists() else []


def per_case(rows: list[dict], key) -> dict[str, float]:
    by: dict[str, list[float]] = {}
    for d in rows:
        if d["status"] == "ok":
            by.setdefault(d["prompt_id"], []).append(key(d))
    return {k: statistics.mean(v) for k, v in by.items()}


def mean_ci(xs: list[float]) -> tuple[float, float]:
    if not xs:
        return float("nan"), float("nan")
    m = statistics.mean(xs)
    return m, (1.96 * statistics.stdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else float("nan"))


def pct(xs: list[float], q: float) -> float:
    s = sorted(xs)
    return s[min(len(s) - 1, int(q * len(s)))] if s else float("nan")


def summarize() -> None:
    data = {v: load_results(v) for v in VARIANTS}
    errs = {v: len((FLOW / v / "errors.jsonl").read_text().splitlines()) if (FLOW / v / "errors.jsonl").exists() else 0 for v in VARIANTS}
    reviewed = sum(r["reviewed"] for r in load_rows())
    lines = ["# Card generation eval: Critic loop vs no Critic", "",
             f"Pipeline model `{config.MODEL}`, judge `{JUDGE_MODEL}`. Gold labels human-reviewed: {reviewed}/20. "
             "Means are over cases (each case = mean of its reps); ± is a 95% CI over cases.", ""]
    for v, rows in data.items():
        n_cases = len({d["prompt_id"] for d in rows})
        reps = max((d["rep"] for d in rows), default=-1) + 1
        trunc = sum(d["status"] != "ok" for d in rows)
        lines.append(f"- **{v}** ({'Critic, max 3 rounds' if VARIANTS[v]['use_critic'] else 'no Critic'}): "
                     f"{n_cases} cases × {reps} reps, {len(rows)} rows, {trunc} truncated, {errs[v]} errors")
    lines += ["", "| metric | baseline | v1 (Critic) | paired Δ (v1 − baseline) |", "|---|---|---|---|"]
    for mt in METRICS:
        b, c = per_case(data["baseline"], lambda d: d["grade"][mt["id"]]), per_case(data["v1"], lambda d: d["grade"][mt["id"]])
        common = sorted(set(b) & set(c))
        bm, bci = mean_ci(list(b.values()))
        cm, cci = mean_ci(list(c.values()))
        dm, dci = mean_ci([c[k] - b[k] for k in common])
        lines.append(f"| {mt['label']} | {bm:.3f} ± {bci:.3f} | {cm:.3f} ± {cci:.3f} | {dm:+.3f} ± {dci:.3f} (n={len(common)}) |")
    lines += ["", "| perf (per card) | baseline | v1 (Critic) |", "|---|---|---|"]
    for label, fn in [("latency mean (s)", lambda rs: statistics.mean(d["latency_s"] for d in rs)),
                      ("latency p50 (s)", lambda rs: pct([d["latency_s"] for d in rs], 0.5)),
                      ("latency p95 (s)", lambda rs: pct([d["latency_s"] for d in rs], 0.95)),
                      ("pipeline cost mean ($)", lambda rs: statistics.mean(d["cost_usd"] for d in rs)),
                      ("output tok/s mean", lambda rs: statistics.mean(d["output_tok_per_s"] for d in rs)),
                      ("rounds mean", lambda rs: statistics.mean(d["rounds"] for d in rs)),
                      ("critic passed (share)", lambda rs: statistics.mean(float(bool(d["critic_passed"])) for d in rs)),
                      ("judge cost mean ($)", lambda rs: statistics.mean(d["judge_cost_usd"] or 0 for d in rs))]:
        vals = [f"{fn(rs):.3f}" if rs else "-" for rs in (data["baseline"], data["v1"])]
        lines.append(f"| {label} | {vals[0]} | {vals[1]} |")
    total = sum(d["cost_usd"] + (d["judge_cost_usd"] or 0) for rs in data.values() for d in rs)
    lines += ["", f"Total measured spend for these rows (pipeline + judge): ${total:.2f}"]
    (FLOW / "summary.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


# ---------------- judge self-test (known-good / known-bad) ----------------

async def judge_selftest() -> None:
    rows = load_rows()
    client = anthropic.AsyncAnthropic(max_retries=5)
    vacuous = ["想想这道题", "注意边界情况", "考虑一下效率"]
    cases = []
    for i, row in enumerate(rows[:3]):
        other = rows[(i + 7) % len(rows)]
        cases += [
            ("oracle idea/complexity", row, {"idea": row["reference_idea"], "complexity": row["reference_complexity"],
                                              "hints": vacuous, "pitfalls": ""}, {"idea_correct": True, "complexity_correct": True}),
            ("hints = the idea", row, {"idea": row["reference_idea"], "complexity": row["reference_complexity"],
                                       "hints": [row["reference_idea"]] * 3, "pitfalls": ""}, {"no_spoiler": False}),
            ("wrong idea + complexity", row, {"idea": other["reference_idea"], "complexity": "时间 O(n!) / 空间 O(n!)",
                                              "hints": vacuous, "pitfalls": ""}, {"idea_correct": False, "complexity_correct": False}),
            ("empty card", row, {"idea": "", "complexity": "", "hints": ["", "", ""], "pitfalls": ""},
             {"idea_correct": False, "complexity_correct": False, "hints_helpful": False}),
            ("vacuous hints", row, {"idea": row["reference_idea"], "complexity": row["reference_complexity"],
                                    "hints": vacuous, "pitfalls": ""}, {"no_spoiler": True, "hints_helpful": False}),
        ]

    async def one(name, row, card, expect):
        j = await judge(client, row, card)
        g, _ = grades(row, {"primary_pattern": row["gold_primary"]}, j.verdict)
        got = {k: bool(g[k]) for k in expect}
        return name, row["slug"], got == expect, expect, got, j

    res = await asyncio.gather(*(one(*c) for c in cases))
    spend = 0.0
    for name, slug, ok, expect, got, j in res:
        spend += call_cost(j.model, j.usage["input_tokens"], 0, 0, j.usage["output_tokens"])
        print(f"{'PASS' if ok else 'FAIL'}  {name:26s} {slug:40s} expect={expect} got={got}")
    print(f"\n{sum(r[2] for r in res)}/{len(res)} self-test expectations met; judge spend ${spend:.3f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=list(VARIANTS))
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--timeout-s", type=float, default=600)
    ap.add_argument("--approve-harness", action="store_true")
    ap.add_argument("--summarize", action="store_true")
    ap.add_argument("--judge-selftest", action="store_true")
    a = ap.parse_args()
    if a.summarize:
        return summarize()
    gate(a.approve_harness)
    if a.judge_selftest:
        return asyncio.run(judge_selftest())
    if not a.variant:
        ap.error("--variant is required")
    asyncio.run(run_variant(a.variant, a.reps, a.limit, a.concurrency, a.timeout_s))


if __name__ == "__main__":
    main()
