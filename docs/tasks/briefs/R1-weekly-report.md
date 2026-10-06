# R1: One-command weekly report

Status: Draft (write fully when v0.3 lands) · Size: small-medium · Release: v0.4 · Depends on: S2c, B04b-2

## Why

The end product is a weekly decision, not a set of modules. One command should go from fresh data to
a short report Alex reads before the deadline.

## Do (outline)

1. `uv run python -m fplrank.weekly --team <id> --target 10000` : snapshot `bootstrap-static` and
   fixtures, pick the latest projections (Solio, else `ep_next`), EO forecast for the chosen group,
   T_X and gap, S1 sweep, S2 choice.
2. Write `reports/GW{n}.md` (git-ignored if it contains Solio-derived numbers): recommended moves and
   captain, λ, P(target) for the EV plan and the chosen plan, EV cost, and the two nearest alternatives.
3. Optional: a Windows scheduled task the evening before the deadline, alongside the collector tasks.

## Done when

Alex has used the report for 3 consecutive GWs and the log has a line for each.
