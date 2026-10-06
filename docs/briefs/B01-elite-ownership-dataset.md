# B01: Elite ownership dataset in the repo

Status: Ready · Size: small · Depends on: nothing

## Goal

Bring the hand-transcribed Elite 64 data into the repo as a versioned dataset with a loader, so
every later model can read "elite ownership by GW" from one place. More seasons and sources
(FPL Review, LiveFPL, our own collector) will be added to the same structure later.

## Inputs

`Documents/fpl-rank-solver-inbox/datasets/elite64/` (read its README first):
`elite64_eo_2026-27.csv`, `elite64_meta_2026-27.csv`, `build.py`.

## Do

1. Copy the two CSVs to `datasets/elite_ownership/` in the repo. Add a `.gitignore` exception so
   they are committed (they are transcriptions of public graphics, not paid data).
2. Create `src/fplrank/data/elite.py` with:
   - `load_eo(source="elite64", season="2026-27") -> DataFrame` in a **long** shape:
     `season, gw, group, fpl_id, player, team, pos, eo` (group = "AE64" / "E64", eo as a fraction, 1.0 = 100%).
   - `load_meta(...)` returning the long meta table with `group` as a column.
   - `eo_panel(groups, gws, players, floor=0.025)`: a complete player × GW matrix where unlisted
     players get `floor` and a boolean `censored=True` column. `floor` is a parameter, default 2.5%.
3. Port the validation checks from `build.py` into `tests/test_elite_data.py`:
   partition tables sum to 64, chips-remaining consistent with usage, every row has an `fpl_id`,
   listed EO coverage between 0.85 and 1.0 of the group total.
4. Add `datasets/README.md` describing the folder, sources, licence/attribution and the
   "censored, not zero" rule.

## Done when

- `from fplrank.data.elite import eo_panel` works and tests pass.
- README explains how to add a new season/source.
