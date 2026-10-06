# B01b: Replace the flat EO floor with a residual-based fill

Status: Done (2026-10-05) · Size: small · Depends on: B01 (merged in PR #1)

> PR https://github.com/flusskrebs-max/fpl-rank-solver/pull/3 (branch `b01b-residual-eo-fill`),
> not merged yet. `expected_totals` / `expected_total_eo`, residual water-fill in `eo_panel`,
> `fill_method` column, `universe_from_bootstrap` (default = latest bootstrap snapshot), `floor`
> removed. Deviation: cap = smallest *positive* listed EO (26 listed 0% rows would zero the cap).
> Real data: totals match expected exactly; max fill 7.1%. pytest 32 passed, ruff clean.

## Why

Review of B01 (2026-10-05): `eo_panel` fills unlisted players with a flat `floor=0.025`. Listed
players already cover 90-98% of each group's total EO, so the flat floor overcounts. With only
the ~70 players ever listed, group totals already come out at 12-15 (1200-1500%) instead of
about 11.6-12.8, and it gets far worse if the panel includes all ~600 players.

## Do

1. Add `expected_total_eo(group, gw)` from the meta table:
   `11 + 1 (captain) + TC share × 1 + BB share × 4` (shares = chip_active counts / 64).
2. In `eo_panel`, compute `residual = expected_total − listed total` per group/GW (clip at 0).
   Spread it across **all** unlisted players in the panel's player universe, in proportion to their
   overall FPL ownership (`selected_by_percent` from bootstrap/vaastav players_raw; uniform fallback
   if missing), and cap each at the smallest listed EO for that position/group/GW. Redistribute any
   amount removed by the cap.
3. Keep `censored=True` and add `fill_method` ("listed" / "residual").
4. Default player universe = every FPL player (so totals are meaningful); keep the `players=` filter.
5. Tests: for every group/GW, panel EO sums to `expected_total` within 1%; no unlisted value
   exceeds the listing cutoff; listed values unchanged.

## Done when

Tests pass and `docs/` notes the method (one paragraph in datasets/README.md).
