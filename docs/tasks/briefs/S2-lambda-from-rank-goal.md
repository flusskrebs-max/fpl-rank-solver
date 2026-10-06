# S2: Choose λ from the rank goal

Status: Ready (after S1) · Size: three PRs (S2a, S2b, S2c) · Release: v0.2 · Depends on: S1, C0, D1

## Why

Alex wants a general solver: enter current points (or rank), target rank and GWs left, and it sets
the risk weight. No full simulation for v1 (stock take, 2026-10-06): a normal approximation of the
relative score is enough to see the trade-off, and we can check it against the simulator later.

## Do

Ship as three PRs: **S2a** = step 1, **S2b** = step 2's variance table, **S2c** = steps 2-5.

1. Gap: `G = T_X - our points`, with `T_X` the target-rank line now (collector `thresholds` table) plus
   a simple projection of how it grows to GW38 (past seasons' cut-offs from `rank-cutoffs.md`).
2. Relative score of a plan over the horizon: mean `μ = Σ (m - EO) x xP` (m = our multiplier),
   variance `σ² = Σ (m - EO)² x v(xP)`, with `v(xP)` a table of actual points variance by position x xP
   band from vaastav 2023-24, 2024-25 and 2025-26 (2025-26 added 2026-10-06: first season with defensive
   contribution points; use D1's `ep_next` as its xP, since vaastav `xP` is blank for 27 GWs). Ignore covariance for v1 and say so.
3. Scale to the rest of the season: GWs left x per-GW μ and σ² (independent GWs).
4. `choose_lambda(gap, gws_left, plans)`: for each S1 plan, `P = Φ((μ_season - G) / σ_season)`; return
   the plan with the highest P, its λ, P, and EV cost vs the EV plan.
5. Inputs as a small config or CLI: target rank, our points (or rank), GW.

## Checks

- Level with the target line and many GWs left: λ ≈ 0 (EV plan).
- Ahead: λ > 0 (cover); far behind with few GWs left: λ < 0 (chase).
- P increases with μ and falls with σ when ahead, and the reverse when behind.

## Done when

`choose_lambda` gives sensible λ for a grid of (gap, GWs left) and a one-line report:
"λ = -0.15, P(top 10k) 23% vs 19% for the EV plan, EV cost 1.4 points".
