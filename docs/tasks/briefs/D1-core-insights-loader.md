# D1: Loader for FPL-Core-Insights per-GW player data

Status: Ready · Size: small · Release: v0.2 · Depends on: nothing

## Why

vaastav no longer updates weekly and its 2025-26 `xP` is blank for 27 of 38 GWs. FPL-Core-Insights
(github.com/olbauday/FPL-Core-Insights, free CSVs, refreshed twice a day, FPL ids) has a per-GW snapshot
of every player's FPL record, including `ep_next`, `selected_by_percent` and transfers in/out, for
2025-26 and 2026-27. It feeds S2b (variance table incl. 2025-26) and B04b (projections for every GW).
See `docs/research/data-sources.md`.

## Do

1. `fplrank.data.historical` (or a new `core_insights.py`): download and cache
   `data/<season>/playerstats.csv` under `data/raw/core_insights/<season>/` (git-ignored), like vaastav.
2. `playerstats(season)` → long table `gw, fpl_id, ep_next, ep_this, selected_by_percent,
   transfers_in_event, transfers_out_event, now_cost, status` with tidy dtypes.
3. `xp_from_ep_next(season)`: for GW N, the `ep_next` recorded at gw = N − 1 (check the offset against
   vaastav `xP` on the 11 GWs where both exist and record the result in `docs/data-log.md`).
4. Tests on a small committed fixture (a few rows, free data) plus one `@pytest.mark.network` test.
5. Attribution: link to the repo in `datasets/README.md` or the module docstring (the author asks for one).

## Done when

`xp_from_ep_next("2025-26")` returns a value for every player and GW, and the data log has the
comparison with vaastav `xP`.
