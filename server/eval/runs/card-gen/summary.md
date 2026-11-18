# Card generation eval: Critic loop vs no Critic

Pipeline model `claude-opus-5-5`, judge `claude-fable-5-2`. Gold labels human-reviewed: 20/20. Means are over cases (each case = mean of its reps); ± is a 95% CI over cases.

- **baseline** (no Critic): 20 cases × 3 reps, 60 rows, 0 truncated, 0 errors
- **v1** (Critic, max 3 rounds): 20 cases × 3 reps, 59 rows, 0 truncated, 1 errors

| metric | baseline | v1 (Critic) | paired Δ (v1 − baseline) |
|---|---|---|---|
| card pass | 0.717 ± 0.179 | 0.967 ± 0.045 | +0.250 ± 0.195 (n=20) |
| no spoiler | 0.717 ± 0.179 | 0.967 ± 0.045 | +0.250 ± 0.195 (n=20) |
| idea ok | 1.000 ± 0.000 | 1.000 ± 0.000 | +0.000 ± 0.000 (n=20) |
| complexity ok | 1.000 ± 0.000 | 1.000 ± 0.000 | +0.000 ± 0.000 (n=20) |
| hints helpful | 1.000 ± 0.000 | 1.000 ± 0.000 | +0.000 ± 0.000 (n=20) |
| pattern | 0.967 ± 0.065 | 0.983 ± 0.033 | +0.017 ± 0.033 (n=20) |
| pattern (len.) | 1.000 ± 0.000 | 1.000 ± 0.000 | +0.000 ± 0.000 (n=20) |
| spoiler hints | 0.094 ± 0.060 | 0.011 ± 0.015 | -0.083 ± 0.065 (n=20) |

| perf (per card) | baseline | v1 (Critic) |
|---|---|---|
| latency mean (s) | 16.791 | 51.379 |
| latency p50 (s) | 16.340 | 49.970 |
| latency p95 (s) | 24.490 | 86.490 |
| pipeline cost mean ($) | 0.074 | 0.173 |
| output tok/s mean | 88.080 | 92.059 |
| rounds mean | 1.000 | 1.814 |
| critic passed (share) | 0.000 | 0.983 |
| judge cost mean ($) | 0.054 | 0.050 |

Total measured spend for these rows (pipeline + judge): $20.84
