# B04b: Refit and backtest the field model on the full 2025-26 season

Status: Ready · Size: small-medium · Depends on: B04 (branch `b04-ownership-dynamics`), B06 (2025-26 data)

## Why

B04 was built on 2026-27 GW1-5 (four transitions), before the 2025-26 data landed. Its findings are
sensible (projections drive moves; last week's points add nothing; elite captaincy is very tight),
but four transitions can't test it. B06 now gives 37 transitions × 2 groups with complete squad
ownership, transfer flows, captains and chips, including blanks, doubles and wildcard weeks.

## Do

1. Merge B04 (only `docs/roadmap.md` conflicts with B03b; keep both sets of lines).
2. Refit `forecast_eo` on 2025-26, using `ownership_2025-26.csv` for squad ownership and the transfer
   lists for flows. Projections for last season: vaastav `xP` only exists for 11 GWs of 2025-26, so
   build a simple proxy for every GW (e.g. last-4-GW points per 90 × minutes share × fixture
   difficulty, with 0 for blanks and ×2 for doubles), check it against xP on the 11 GWs, and say in
   the report that it is a proxy.
3. Add the parts B04 couldn't test: fixtures (blank/double), banked FTs as a persistence modifier,
   chip weeks (WC GW6/32, FH GW13/34, BB GW33).
4. Backtest GW10-38 against listed EO (out of sample by GW), against persistence, separately for
   AE64 and E64, and for normal / double / blank / chip weeks.
5. Captaincy: refit τ per group on 38 GWs of captain counts.

## Done when

`docs/research/ownership-dynamics-v0.md` has a 2025-26 section with the backtest table, and the
model beats persistence overall and in double/blank weeks.
