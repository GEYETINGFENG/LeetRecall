// node tests/fsrs.test.mjs
import assert from "node:assert/strict";
import { preview, apply, newSchedule, retrievability, DAY } from "../src/fsrs.js";

const now = new Date("2026-11-10T15:00:00").getTime();

// new card: intervals are ordered and Again is 1 day
const p0 = preview(newSchedule(), now);
assert.equal(p0[1].ivl, 1);
assert.ok(p0[2].ivl <= p0[3].ivl && p0[3].ivl < p0[4].ivl, "Hard <= Good < Easy");

// at the scheduled due time retrievability is close to the 90% target
let s = apply(newSchedule(), 3, now);
let t = now;
for (let k = 0; k < 4; k++) {
  t = s.due + 12 * 3600e3;
  const r = retrievability(s, t);
  assert.ok(r > 0.85 && r < 0.95, `R at due ~0.9, got ${r}`);
  s = apply(s, 3, t);
}

// Good reviews grow the interval; a lapse shrinks stability and counts a lapse
const before = s.s;
const lapsed = apply(s, 1, s.due);
assert.ok(lapsed.s < before);
assert.equal(lapsed.lapses, 1);
assert.equal(Math.round((lapsed.due - new Date(new Date(s.due).setHours(0, 0, 0, 0)).getTime()) / DAY), 1);

// due dates always land on local midnight
assert.equal(new Date(s.due).getHours(), 0);

console.log("fsrs tests passed");
