# B02: Projection loader and vintage registry

Status: Done (2026-10-05) · Size: small · Depends on: nothing

> PR https://github.com/flusskrebs-max/fpl-rank-solver/pull/2 (branch `b02-projection-loader`),
> not merged yet. `src/fplrank/data/projections.py` (`load_solio`, `register`, `latest`,
> `id_report`, CLI `register` / `check-ids [--fetch]`), `tests/test_projections.py` + synthetic
> fixture. Registered locally from Downloads: projection (1)/(2)/(3) → vintage GW1, (8) → GW6.
> IDs: none missing vs live bootstrap; renames only (403 Savinho→Sávio, 569 García→Gonzalo).
> Not registered: projection (4)/(5) (GW1, identical to each other), (6)/(7) (GW2),
> projection.csv (Apr 2026, GW33+, last season). pytest 28 passed, ruff clean.

## Goal

Read Solio projection exports into one standard shape and keep track of *when* each file was made,
so we can compare "what the model expected" against "what the elite did" week by week.

## Context

- Format: `Pos, ID, Name, BV, SV, Team, {gw}_xMins..., {gw}_Pts...` (means only).
- Files are paid data: store under `data/projections/` (git-ignored). **Never commit them.**
- A file's vintage = the GW it was made for = its first `_Pts` column (pre-season files start at GW1;
  e.g. "projection 8" starts at GW6). Prices (BV) also hint at the date.

## Do

1. `src/fplrank/data/projections.py`:
   - `load_solio(path) -> DataFrame` long format: `vintage_gw, gw, fpl_id, name, team, pos, price, xmins, xpts`.
   - `register(path)`: copies the file into `data/projections/solio/GW{vintage:02d}_{yyyymmdd}.csv`
     and appends a row to `data/projections/registry.csv` (file, vintage_gw, first/last gw,
     n_players, downloaded date, sha256).
   - `latest(gw)`: the newest projection made at or before `gw`.
2. A CLI: `uv run python -m fplrank.data.projections register <file> [<file> ...]`.
3. Tests with a tiny synthetic CSV in `tests/fixtures/` (fake players, not real Solio data).
4. Register Alex's current files: `projection 1/2/3.csv` (pre-season) and `projection 8.csv` (GW6).
   Ask Alex where they are saved.

## Done when

- `registry.csv` lists the four files with correct vintages.
- `load_solio` output joins cleanly to FPL ids (report any unmatched ids).
