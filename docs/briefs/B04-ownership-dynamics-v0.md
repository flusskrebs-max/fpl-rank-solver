# B04: Ownership dynamics v0 (first model from historical data)

Status: Done (2026-10-05) · Size: medium

> PR https://github.com/flusskrebs-max/fpl-rank-solver/pull/6 (branch `b04-ownership-dynamics`),
> not merged yet. `fplrank.model.ownership` (`forecast_eo`, `state_for`, `fit_default`, `backtest`),
> `notebooks/b04_ownership_dynamics.py` (cell-marked .py, no Jupyter), write-up
> `docs/research/ownership-dynamics-v0.md`. Fitted on top-1000 (B03) data, applied to AE64/E64.
> Q1 projections drive XI share, last-GW points ≈ 0; Q2 τ top1000 0.62, AE64 0.37, E64 0.38;
> Q3 Wildcard 7.3 / Free Hit 8.5 XI changes vs 1.9 normal, chip timing not modellable yet (no
> blanks/doubles); Q4 no evidence AE64 leads E64. Backtest MAE vs persistence: top1000 0.020 vs
> 0.026, E64 0.158 vs 0.201, AE64 0.196 vs 0.241 (wins GW3-5, loses GW2). Deviation: B01 floor
> replaced by B01b; GW3-5 use the GW2 projection file. pytest 43 passed, ruff clean.

## Goal

A first, deliberately simple model of how elite EO moves week to week, built from what we have
(Elite 64 GW1-5 now, last season's screenshots later, B03 data when it lands). The output is a
forecast of next-GW elite EO with an error bar, which the rank solver will consume.

## Questions to answer (in a notebook + short write-up in docs/research/)

1. **Ownership (excluding captaincy):** how does a player's elite ownership change from GW t to t+1
   as a function of: his projected points next 1/3/6 GWs (from B02's vintage for GW t+1), his
   points last GW, price change, fixture swing, and how many FTs the group has banked?
2. **Captaincy share:** given who the group owns, how is the armband split? Test a softmax over
   projected points with a "temperature" fitted per group (analytics vs template).
3. **Chip weeks:** how much do WC/FH weeks move EO, and can we predict chip timing from the
   chips-remaining counts and the fixture calendar (blanks/doubles)?
4. **Group difference:** does AE64 lead E64 (moves a week earlier)? If so, AE64 is a predictor of E64.

## Method guidance

- Separate ownership (0-1 per player) from multiplier (captain/TC/bench) before modelling.
- Unlisted players: use the B01 `floor` and treat as censored, not observed.
- Fit tiny models (logistic/softmax with 2-4 parameters); report fit and how wrong it is.
  Small n (64 managers, few GWs): prefer interpretable over clever.

## Done when

- A function `forecast_eo(group, gw_next, state) -> DataFrame[fpl_id, eo_mean, eo_low, eo_high]`.
- A backtest over the GWs we have showing its error vs "next week = this week".
