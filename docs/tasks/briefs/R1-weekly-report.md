# R1: One-command weekly report

Status: v1 built, awaiting live use · Size: small-medium · Release: v0.4 · Depends on: S1, S2c (B04b-2 plugs in later)

## Why

The end product is a weekly decision, not a set of modules. One command should go from fresh data to
a short report Alex reads before the deadline.

## Do

1. `uv run python -m fplrank.weekly --team <id> --target 10000 [--eo AE64|solio|...]`: live API (every
   call saved as a snapshot), latest projections (Solio, else `ep_next` with a loud warning), EO as S1
   uses it today (last collected GW, or Solio's per-GW forecast), S1 sweep, S2c choice of λ.
2. Write `reports/GW{n}.md` (git-ignored: Solio-derived numbers): recommended plan (moves, captain, chip,
   XI, bench), λ, P(target) for it and the EV plan, EV cost, the EV plan if different, the two nearest
   distinct alternatives, and the whole sweep table.
3. Later: B04b-2's multi-GW EO forecast in place of the repeated EO; a Windows scheduled task the evening
   before the deadline, once the manual run is trusted.

4. Harness shape: `Inputs` (current EO, EV projections, current team, current points and rank, rank goal)
   and `run(inputs, mode)`. `--mode optimum` (S1 sweep + S2c's λ) is R1; `--mode simulate` is R2 (below).
   λ applies to the next GW only, as in S1c; `--eo-forecast` takes B04's deadline EO.

## R2: mode "simulate" (follow-up, not built)

Sertalp's open-fpl-solver already has the noise: with `randomized: true`, `dev/solver.py` adds, per GW and
player, `Pts * (92 - xMins) / 134 * N(0, 1) * randomization_strength` (seeded by `randomization_seed`), and
`run/simulations.py` re-solves N times and tallies moves (`run/sensitivity.py`). No vendor edit is needed:
`solve_ev` passes options through, so R2 is N calls of `solve_with_ownership` at S2c's λ with
`{"randomized": True, "randomization_seed": i}`, then a table of how often each first-GW move set, captain
and chip comes out on top. Noise goes on after the λ adjustment (upstream adds it to the adjusted Pts), which
is what we want. Later option: draw the noise from our own scenario engine (`sim/scenarios.py`, correlated by
team) instead of upstream's independent normals. Cost: N solves; 50 runs at a few seconds each is fine on
Alex's PC, too slow for the 2-CPU cloud box.

## Checks

- Rendering tested on fake plans (recommendation, EV plan, alternatives are distinct plans).
- Offline slow test: sweep on the saved GW6 real team with `ep_next`, report renders.
- Logic is shared with the S1 CLI (`pick_projections`, `pick_eo`, `rank_goal_table`), not copied.

## Done when

Alex has used the report for 3 consecutive GWs and the log has a line for each.
