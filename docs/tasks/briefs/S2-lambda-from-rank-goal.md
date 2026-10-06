# S2: Choose λ from the rank goal

Status: Ready (after S1) · Size: three PRs (S2a, S2b, S2c) · Release: v0.2 · Depends on: S1, C0, D1

## Why

Alex wants a general solver: enter current points (or rank), target rank and GWs left, and it sets
the risk weight. No full simulation for v1 (stock take, 2026-10-06): a normal approximation of the
relative score is enough to see the trade-off, and we can check it against the simulator later.

## Do

Ship as PRs: **S2a** = step 1, **S2b** = the variance table v(xP), **V1** = the realised-spread check
(sets s, drift and the base σ²), **S2c** = steps 2-5. Revised 2026-10-06 after a critical review.

1. **Gap (S2a):** `G = T_X(now) - ours(now) + drift x GWs left`, where drift is the mean over this
   season's collected GWs of (the line's GW gain - the EO group's mean GW points), from the collector's
   thresholds and the group's picks/points; drift = 0 until 3 GWs are in. Using the gap against the line
   *relative to the group* stops the field's growth being counted twice (μ below is already relative to
   the group). `target_line()` is kept as the indicative absolute line for the report only; its `sd`² is
   added to σ² in step 4.
2. **Per-GW relative score of a plan:** `μ = κ x Σ (m - EO) x xP`, κ = 0.3 by default (how much of our
   projection edge over the field is real), printed on the report; `σ² = s² x Σ (m - EO)² x v(xP)`, with
   s from V1 (1 until V1 lands) and v(xP) from S2b. Ignore covariance for v1 and say so.
3. **Season total:** `μ_tot = μ_plan(H) + μ_base x (GWs left - H)`, the same for σ², where H is the
   plan's horizon and the base is the λ = 0 plan's per-GW average (later V1's empirical spread). A plan
   for this week is not assumed to repeat for the whole season.
4. `choose_lambda(gap, gws_left, plans)`: `P = Φ((μ_tot - G) / sqrt(σ²_tot + sd_line²))`; return the plan
   with the highest P, its λ, P, and EV cost vs the EV plan.
5. Inputs as a small config or CLI: target rank, our points (or rank), GW.

## Checks

- A plan identical to the field, G = 0 and drift 0 ⇒ P = 0.5.
- Level with the target line and many GWs left: λ ≈ 0 (EV plan). If this fails, κ is too high: report
  it, don't tune around it.
- Ahead: λ > 0 (cover); far behind with few GWs left: λ < 0 (chase).
- P increases with μ and falls with σ when ahead, and the reverse when behind.
- 30 GWs left: P(chosen plan) - P(EV plan) is a few points, not tens.

## Done when

`choose_lambda` gives sensible λ for a grid of (gap, GWs left) and a one-line report:
"λ = -0.15, P(top 10k) 23% vs 19% for the EV plan, EV cost 1.4 points".
