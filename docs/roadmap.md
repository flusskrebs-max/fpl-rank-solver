# Roadmap

Ordered by dependency, not by calendar. Each step has an exit test so it is clear when it's done.
The season is live, so data collection runs from now on (scheduled collector, weekly projections)
while the modelling steps are built.

## Phase 0: Setup ✅ (2026-10-05)

- Repo scaffold, upstream vendored at `ec65f5e` (2026-09-15), Python 3.14 + uv environment
- Upstream EV solver callable offline (`fplrank.baseline.solve_ev`), smoke test on 2026-27 data
- Toy spike: SAA probability objective in HiGHS picks differentials when chasing, template when level
- Docs: components list, problem framing, decision records, CLAUDE.md

**Exit:** `uv run pytest` green. ✅

## Phase 1: Define the objective ✅ (2026-10-05, brainstorm)

The objective, architecture and test plan are in
**[research/solver-design.md](research/solver-design.md)**: maximise P(final overall rank ≤ X),
via the relative score Δ against the target group's EO; generate candidates with the upstream MILP
(λ·EO·xP sweep), then evaluate them by simulation.

**Exit:** design and test plan written ✅. ADR 0004 "Objective definition" still to record the
choices that would be expensive to reverse.

## Build order (solver-design §7)

Components: [A] scenario engine, [B] field engine, [C] candidate generator, [D] evaluator.
Data collection that feeds them (Elite 64 datasets B01, top-1000 collector B03 scheduled twice weekly)
runs alongside.

### 1. Residual-based fill for unlisted EO ✅ (B01b)

`fplrank.data.elite.eo_panel` spreads each group's residual EO over unlisted players by ownership,
capped at the listing cutoff.

**Exit:** group totals match 11 + 1 + chips within 1% ✅.

### 2. Projection loader ✅ (B02)

`fplrank.data.projections`: Solio exports in one long shape, with a vintage registry.

**Exit:** registered files join cleanly to FPL ids ✅.

### 3. Rank-line data (in progress: B03 item 5 / B03b)

Live `T_X(now)` from the standings every collector run; end-of-season cut-offs for past seasons from
the `past` field of sampled managers (spread term only).

**Exit:** `T_X(now)` rows every GW, and 2025/26 cut-offs for top 100 / 1k / 10k / 100k.

### 4. [A] Scenario engine v0 + calibration report (B07)

Correlated simulated points per player and GW, consistent with projection means.

**Exit:** calibration report: simulated event frequencies and tails within bootstrap bands of
2025-26 actuals; 10,000 scenarios × 6 GWs in under a minute.

### 5. [B] Field engine v0 + backtest vs persistence (B04, B06)

Next-GW elite EO with an error bar, ownership and captaincy modelled separately.

**Exit:** beats "next week = this week" on MAE out of sample, especially after hauls.

### 6. [C]+[D] Candidate sweep + evaluator for a single GW

Upstream MILP with xP + λ·EO·xP over a λ grid, plus captain/chip options; evaluate each candidate's
P(target) over the scenarios (no rollout yet). Known-answer tests from solver-design §5b.

**Exit:** for a set of historical GWs, the chosen candidate has a higher estimated P(target) than the
EV plan, at a points cost we can quantify.

### 7. Value function V by simulation; then rollout

V(gap, GWs left, chips) from simulated season remainders; multi-GW rollout policy using it.

**Exit:** monotonicity invariants hold (σ(Δ) rises with the gap, falls when ahead).

### 8. Policy backtests

Replay 2025-26 and this season: pure EV vs fixed λ vs the full solver, at a grid of gaps and GWs left.

**Exit:** the full solver's P(finish ≤ X) interval clears the EV policy's at X = 10k and 1k.

### Then: weekly use

One command (or scheduled task) that snapshots data, solves, and produces a short report:
recommended moves, P(target) for each option, and the EV cost of the risk taken.

**Exit:** used for real for 3 consecutive GWs.
