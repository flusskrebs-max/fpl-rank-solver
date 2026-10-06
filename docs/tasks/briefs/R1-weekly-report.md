# R1: One-command weekly report

Status: v1 built (rough) · Size: small-medium · Release: v0.4 · Depends on: S1, S2c (B04b-2 plugs in later)

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

## Checks

- Rendering tested on fake plans (recommendation, EV plan, alternatives are distinct plans).
- Offline slow test: sweep on the saved GW6 real team with `ep_next`, report renders.
- Logic is shared with the S1 CLI (`pick_projections`, `pick_eo`, `rank_goal_table`), not copied.

## Done when

Alex has used the report for 3 consecutive GWs and the log has a line for each.
