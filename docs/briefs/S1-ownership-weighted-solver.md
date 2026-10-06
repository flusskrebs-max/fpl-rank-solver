# S1: Ownership-weighted solver

Status: Ready · Size: small-medium · Depends on: B02 (projections), an EO source (collector or Elite 64)

## Why

The core product (stock take, 2026-10-06): the standard Solio EV solve plus one knob that weights
ownership, like the community "risk position". λ > 0 covers template players, λ < 0 chases
differentials. S2 picks λ from the rank goal; this brief only builds the knob.

## Do

1. `src/fplrank/opt/ownership.py`: `adjust_projections(projections, eo, lam)`: for each player and GW,
   `xP' = xP x (1 + lam x (EO - mean EO of the squad-sized template))`, or the simpler
   `xP' = xP + lam x EO x xP` (the linear term from solver-design §1). Pick one, say why, keep it linear.
   EO is per player per GW (one GW of current EO repeated across the horizon is fine for v1; B04b
   will supply a forecast).
2. `solve_with_ownership(my_data, projections, eo, lam, ...)` -> plan, via `fplrank.baseline.solve_ev`
   (no changes to `vendor/`). Report each plan's EV (on unadjusted xP) and its EO overlap.
3. A sweep helper: plans for λ on a grid (e.g. -0.3 to 0.3), deduplicated, each with EV and EV cost
   vs λ = 0.
4. A CLI: `uv run python -m fplrank.opt.ownership --team <id> --eo <AE64|E64|top1000> --lam 0.1`.

## Checks

- λ = 0 gives exactly the EV plan.
- As λ rises, the plan's EO-weighted overlap with the field rises and its EV falls (weakly).
- Captaincy: with a 150%+ EO captain and a slightly higher-xP alternative, the choice flips as λ crosses
  a small positive value.

## Done when

A plan for this GW at a few λ values, with EV cost, from one command on Alex's PC.
