// FSRS-4.5 scheduler (default parameters), simplified to day-level intervals.
// Ratings: 1 = Again(忘了), 2 = Hard(想了很久), 3 = Good(想起来了), 4 = Easy(秒想到)

export const DEFAULT_W = [
  0.4872, 1.4003, 3.7145, 13.8206, 5.1618, 1.2298, 0.8975, 0.031, 1.6474,
  0.1367, 1.0461, 2.1072, 0.0793, 0.3246, 1.587, 0.2272, 2.8755,
];

const DECAY = -0.5;
const FACTOR = 19 / 81;
export const DAY = 24 * 60 * 60 * 1000;

const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));

export function newSchedule() {
  return { state: "new", s: 0, d: 0, due: Date.now(), last: 0, reps: 0, lapses: 0 };
}

export function retrievability(sched, now = Date.now()) {
  if (!sched || sched.state === "new" || !sched.s) return null;
  const t = Math.max(0, (now - sched.last) / DAY);
  return Math.pow(1 + (FACTOR * t) / sched.s, DECAY);
}

function initD(w, g) {
  return clamp(w[4] - (g - 3) * w[5], 1, 10);
}

function nextD(w, d, g) {
  const nd = d - w[6] * (g - 3);
  return clamp(w[7] * initD(w, 3) + (1 - w[7]) * nd, 1, 10);
}

function successS(w, d, s, r, g) {
  const hard = g === 2 ? w[15] : 1;
  const easy = g === 4 ? w[16] : 1;
  return s * (Math.exp(w[8]) * (11 - d) * Math.pow(s, -w[9]) * (Math.exp(w[10] * (1 - r)) - 1) * hard * easy + 1);
}

function failS(w, d, s, r) {
  const ns = w[11] * Math.pow(d, -w[12]) * (Math.pow(s + 1, w[13]) - 1) * Math.exp(w[14] * (1 - r));
  return Math.min(ns, s); // forgetting never increases stability
}

function intervalDays(s, retention, maxInterval) {
  const i = (s / FACTOR) * (Math.pow(retention, 1 / DECAY) - 1);
  return clamp(Math.round(i), 1, maxInterval);
}

// Returns {1: sched, 2: sched, 3: sched, 4: sched} with an `ivl` (days) on each.
export function preview(sched, now = Date.now(), opts = {}) {
  const w = opts.w || DEFAULT_W;
  const retention = opts.retention || 0.9;
  const maxInterval = opts.maxInterval || 365;
  const cur = sched || newSchedule();
  const out = {};

  for (const g of [1, 2, 3, 4]) {
    let s, d;
    if (cur.state === "new" || !cur.s) {
      s = w[g - 1];
      d = initD(w, g);
    } else {
      const r = retrievability(cur, now);
      d = nextD(w, cur.d, g);
      s = g === 1 ? failS(w, d, cur.s, r) : successS(w, d, cur.s, r, g);
    }
    out[g] = {
      state: g === 1 && cur.state !== "new" ? "relearning" : "review",
      s,
      d,
      last: now,
      reps: (cur.reps || 0) + 1,
      lapses: (cur.lapses || 0) + (g === 1 && cur.state !== "new" ? 1 : 0),
      ivl: g === 1 ? 1 : intervalDays(s, retention, maxInterval),
    };
  }
  // keep Hard <= Good < Easy, all >= 1 day
  out[2].ivl = Math.min(out[2].ivl, out[3].ivl);
  out[3].ivl = Math.max(out[3].ivl, out[2].ivl + 1);
  out[4].ivl = Math.max(out[4].ivl, out[3].ivl + 1);
  for (const g of [1, 2, 3, 4]) out[g].due = startOfDay(startOfDay(now) + out[g].ivl * DAY + DAY / 2); // DST-safe local midnight
  return out;
}

export function apply(sched, rating, now = Date.now(), opts = {}) {
  const next = preview(sched, now, opts)[rating];
  const { ivl, ...rest } = next;
  return rest;
}

export function startOfDay(ts = Date.now()) {
  const d = new Date(ts);
  d.setHours(0, 0, 0, 0);
  return d.getTime();
}

export function formatIvl(days) {
  if (days < 30) return `${days}天`;
  if (days < 365) return `${Math.round(days / 30)}个月`;
  return `${(days / 365).toFixed(1)}年`;
}
