// Build synthetic seed data from library.json / eval_set.json + solution files.
//   node server/data/build_seed.mjs
// Outputs (deterministic — fixed clock + seeded PRNG):
//   server/data/leetrecall-seed-backup.json  -> plugin "从 JSON 恢复", and POST /v1/cards/sync
//   server/eval/dataset.jsonl                -> held-out eval set (code only + gold labels)
// Review history is simulated with the plugin's own FSRS implementation so `sched` matches real usage.
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { apply, newSchedule, DAY } from "../../src/fsrs.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const NOW = new Date("2026-11-10T12:00:00").getTime();
const SETTINGS = { retention: 0.9, maxInterval: 180 };
const HARD_PATTERNS = new Set(["动态规划", "区间DP", "背包", "线段树/树状数组", "单调队列", "最短路"]);

// mulberry32 — tiny seeded PRNG so reruns produce identical files
let seed = 20261110;
const rand = () => {
  seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
  let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
};
const randInt = (lo, hi) => lo + Math.floor(rand() * (hi - lo + 1));
const pick = (arr) => arr[Math.floor(rand() * arr.length)];

const code = (dir, slug) => {
  const p = join(HERE, dir, `${slug}.py`);
  if (!existsSync(p)) throw new Error(`missing solution: ${dir}/${slug}.py`);
  return readFileSync(p, "utf8").trimEnd();
};

const library = JSON.parse(readFileSync(join(HERE, "library.json"), "utf8"));
const evalSet = JSON.parse(readFileSync(join(HERE, "eval_set.json"), "utf8")).items;

// Guard against leakage: eval problems must never be in the RAG corpus.
const libSlugs = new Set(library.map((c) => c.slug));
const leaked = evalSet.filter((e) => libSlugs.has(e.slug)).map((e) => e.slug);
if (leaked.length) throw new Error("eval/library overlap: " + leaked.join(", "));

function simulate(card) {
  const hard = card.patterns.some((p) => HARD_PATTERNS.has(p));
  const createdAt = NOW - randInt(7, 60) * DAY - randInt(0, 10) * 3600_000;
  let sched = newSchedule();
  const history = [];
  // first rating happens right after the accepted submission (mode "solve")
  let t = createdAt + randInt(1, 30) * 60_000;
  let g = hard ? pick([1, 2, 2, 3]) : pick([2, 3, 3, 4]);
  sched = apply(sched, g, t, SETTINGS);
  history.push({ t, g, mode: "solve", wasNew: true });
  // then flip-card reviews on each due day until today
  while (true) {
    t = sched.due + randInt(9, 22) * 3600_000;
    if (t > NOW) break;
    if (rand() < 0.15) break; // user skipped this review -> card stays overdue
    g = hard ? pick([1, 2, 3, 3]) : pick([2, 3, 3, 3, 4]);
    sched = apply(sched, g, t, SETTINGS);
    history.push({ t, g, mode: "card", wasNew: false });
  }
  return { createdAt, updatedAt: history.at(-1).t, sched, history };
}

const cards = {};
for (const c of library) {
  const sim = simulate(c);
  cards[c.slug] = {
    slug: c.slug, id: c.id, title: c.title, titleCn: c.titleCn, difficulty: c.difficulty,
    tags: [], // LeetCode topicTags intentionally empty: they'd leak the pattern label
    patterns: c.patterns, idea: c.idea, complexity: c.complexity, pitfalls: c.pitfalls,
    code: code("solutions", c.slug), lang: "python3", site: "com",
    createdAt: sim.createdAt, updatedAt: sim.updatedAt, suspended: false,
    sched: sim.sched, history: sim.history,
    stats: { attempts: randInt(1, 3), lastSolveMinutes: randInt(8, 45) },
  };
}

const backup = { app: "leetrecall", version: 1, exportedAt: NOW, synthetic: true, cards };
writeFileSync(join(HERE, "leetrecall-seed-backup.json"), JSON.stringify(backup, null, 2) + "\n");

mkdirSync(join(HERE, "..", "eval"), { recursive: true });
const lines = evalSet.map((e) => JSON.stringify({
  slug: e.slug, id: e.id, title: e.title, titleCn: e.titleCn, difficulty: e.difficulty,
  code: code("eval_solutions", e.slug), lang: "python3",
  gold_primary: e.gold_primary, acceptable: e.acceptable,
  reference_idea: e.reference_idea, reference_complexity: e.reference_complexity, reviewed: e.reviewed,
}));
writeFileSync(join(HERE, "..", "eval", "dataset.jsonl"), lines.join("\n") + "\n");

const reviews = Object.values(cards).reduce((n, c) => n + c.history.length, 0);
const due = Object.values(cards).filter((c) => c.sched.due <= NOW).length;
const patterns = new Set(Object.values(cards).flatMap((c) => c.patterns));
console.log(`library: ${library.length} cards, ${reviews} review events, ${patterns.size} patterns, ${due} due today`);
console.log(`eval: ${evalSet.length} held-out problems, ${new Set(evalSet.map((e) => e.gold_primary)).size} distinct gold patterns, ${evalSet.filter((e) => e.reviewed).length} reviewed`);
