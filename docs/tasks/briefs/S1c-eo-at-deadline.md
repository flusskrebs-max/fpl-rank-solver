# S1c: EO at the deadline

Status: On hold (2026-10-06): a Solio export with EO may replace this for the next GW (ADR 0004) · Size: small · Release: v0.1 · Depends on: S1 (PR #14), B04 (`model/ownership.py`)

## Why

The collector's EO for GW N exists only after the GW N deadline, so S1 currently uses last GW's EO
for a decision about this GW (critical review, 2026-10-06). The one-step forecast from B04 is the
EO we would see at the deadline. EO further out is much less certain, so λ should mostly bite on the
GW we're deciding now.

## Do

1. S1 CLI `--eo-forecast`: `model = fit_default()`, `state = state_for(group, next_gw)`,
   `forecast_eo(group, next_gw, state, model)`; use its `eo_mean` as EO for the next GW.
2. By default apply λ to the first GW of the horizon only (later GWs use raw xP); `--lam-all-gws` keeps
   today's behaviour.
3. Report which EO was used (collected GW, or forecast for GW N) in the CLI header.

## Checks

- With `--eo-forecast` off and `--lam-all-gws` on, plans match S1 as merged.
- λ applied to GW1 only: later GWs' picks match the λ = 0 plan's when nothing forces a change.

## Done when

`uv run python -m fplrank.opt.ownership --team <id> --eo AE64 --eo-forecast --sweep` runs on Alex's PC
before a deadline.
