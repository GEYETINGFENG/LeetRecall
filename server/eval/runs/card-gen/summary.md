# Card generation eval: Critic loop vs no Critic

Pipeline model `claude-opus-5-5`, judge `claude-fable-5-2`. Gold labels human-reviewed: 0/20. Means are over cases (each case = mean of its reps); ± is a 95% CI over cases.

- **baseline** (no Critic): 3 cases × 1 reps, 3 rows, 0 truncated, 0 errors
- **v1** (Critic, max 3 rounds): 3 cases × 1 reps, 3 rows, 0 truncated, 0 errors

| metric | baseline | v1 (Critic) | paired Δ (v1 − baseline) |
|---|---|---|---|
| card pass | 0.333 ± 0.653 | 1.000 ± 0.000 | +0.667 ± 0.653 (n=3) |
| no spoiler | 0.333 ± 0.653 | 1.000 ± 0.000 | +0.667 ± 0.653 (n=3) |
| idea ok | 1.000 ± 0.000 | 1.000 ± 0.000 | +0.000 ± 0.000 (n=3) |
| complexity ok | 1.000 ± 0.000 | 1.000 ± 0.000 | +0.000 ± 0.000 (n=3) |
| hints helpful | 1.000 ± 0.000 | 1.000 ± 0.000 | +0.000 ± 0.000 (n=3) |
| pattern | 1.000 ± 0.000 | 1.000 ± 0.000 | +0.000 ± 0.000 (n=3) |
| pattern (len.) | 1.000 ± 0.000 | 1.000 ± 0.000 | +0.000 ± 0.000 (n=3) |
| spoiler hints | 0.222 ± 0.218 | 0.000 ± 0.000 | -0.222 ± 0.218 (n=3) |

| perf (per card) | baseline | v1 (Critic) |
|---|---|---|
| latency mean (s) | 17.493 | 58.713 |
| latency p50 (s) | 16.610 | 54.730 |
| latency p95 (s) | 21.720 | 71.990 |
| pipeline cost mean ($) | 0.078 | 0.186 |
| output tok/s mean | 85.900 | 87.600 |
| rounds mean | 1.000 | 2.000 |
| critic passed (share) | 0.000 | 1.000 |
| judge cost mean ($) | 0.048 | 0.046 |

Total measured spend for these rows (pipeline + judge): $1.07
