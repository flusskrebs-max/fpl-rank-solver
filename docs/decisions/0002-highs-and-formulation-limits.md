# 0002: HiGHS via highspy as the solver; keep models LP/MILP

Date: 2026-10-05 · Status: Accepted

## Context

Upstream moved from sasoptpy to building models directly with `highspy` (HiGHS's Python API) in
2026. HiGHS is free, fast for LP and MILP, and solves convex continuous QP, but has no mixed-integer
QP. Rank objectives naturally involve variance, which is quadratic in the squad decisions.

The toy spike (`fplrank.opt.toy`, removed 2026-10-06; in git history) shows a sample-average-approximation probability objective works
in HiGHS but is slow even when tiny (12 binaries, 400 scenarios: 20 to 40 s), because big-M
scenario constraints have weak LP relaxations.

## Decision

Use HiGHS (`highspy>=1.11`, currently 1.15) for all optimisation. Keep formulations LP or MILP:
represent risk through scenarios and linear risk measures, or evaluate risk outside the MILP by
simulation. Gurobi stays an optional escape hatch (upstream can write MPS files for `gurobi_cl`).

## Consequences

- No licence costs; runs anywhere uv runs.
- Formulation work must avoid quadratic terms with integers; this steers us towards
  generate-and-simulate or CVaR/MAD-style surrogates.
- If a formulation needs it, benchmark Gurobi before redesigning around HiGHS's limits.
