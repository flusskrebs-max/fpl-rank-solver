# B04b: Refit and backtest the field model on the full 2025-26 season

> Superseded 2026-10-06: not built. The XI and captain re-pick (`docs/research/eo-blend.md`) beat the v0 model it would have refitted, and v0 was removed.

Status: Ready · Size: four PRs (B04b-1a = steps 2 and 4, B04b-1b = step 3 with its backtest by week type, B04b-1c = step 5, B04b-2 = step 6, which also feeds the R1 harness) · Release: v0.4 · Depends on: B04, B06, D1

## Why

B04 was built on 2026-27 GW1-5 (four transitions), before the 2025-26 data landed. Its findings are
sensible (projections drive moves; last week's points add nothing; elite captaincy is very tight),
but four transitions can't test it. B06 now gives 37 transitions × 2 groups with complete squad
ownership, transfer flows, captains and chips, including blanks, doubles and wildcard weeks.

## Do

1. (Done: B04 is merged.)
2. Refit `forecast_eo` on 2025-26, using `ownership_2025-26.csv` for squad ownership and the transfer
   lists for flows. Projections for last season: use D1's `xp_from_ep_next("2025-26")` (FPL's own xP,
   roughly at the deadline) for every GW instead of a home-made proxy (changed 2026-10-06, see
   `docs/research/data-sources.md`). D1 also gives overall `selected_by_percent` and transfer flow per GW:
   try overall net transfers as one extra covariate and keep it only if it helps out of sample.
3. Add the parts B04 couldn't test: fixtures (blank/double), banked FTs as a persistence modifier,
   chip weeks (WC GW6/32, FH GW13/34, BB GW33).
4. Backtest GW10-38 against listed EO (out of sample by GW), against persistence, separately for
   AE64 and E64, and for normal / double / blank / chip weeks.
5. Captaincy: refit τ per group on 38 GWs of captain counts.
6. **Multi-GW** (added 2026-10-06): forecast EO for the next H GWs by applying the one-step model
   repeatedly with each GW's projections, so S1 can use a per-GW EO over its horizon. Backtest 1-, 3-
   and 6-GW-ahead error against persistence. Then pass the forecast into S1 (`--eo-forecast`) in place
   of "this GW's EO repeated".
7. From 2026-10-06 the collector also tracks AE64 and E64 directly (config `leagues`), so this
   season's elite EO is exact for every player; use it alongside the 2025-26 graphics data.

## Done when

`docs/research/ownership-dynamics-v0.md` has a 2025-26 section with the backtest table, and the
model beats persistence overall and in double/blank weeks; `forecast_eo` can return several GWs ahead.
