# data/

Everything in here except this file is git-ignored.

| Folder | Contents | Written by |
|---|---|---|
| `raw/vaastav/<season>/` | Historical season files from vaastav/Fantasy-Premier-League | `fplrank.data.historical` |
| `snapshots/<endpoint>/<timestamp>.json` | Dated copies of live FPL API responses | `fplrank.data.fpl_api.FplApi` |
| `collected/*.parquet` | Elite managers' picks, chips, transfers, ranks, EO, past seasons, rank thresholds; `collected/logs/` | `fplrank.collect.elite_picks` |
| `projections/` | Projection CSVs (Solio, FPL Review, Mikkel, our own) | you |
| `projections/solio/GW{vintage}_{yyyymmdd}.csv` | Registered Solio exports, named by first projected GW and download date | `fplrank.data.projections.register` |
| `projections/registry.csv` | One row per registered file: vintage, GW range, players, download time, sha256 | `fplrank.data.projections.register` |

To add a new Solio download: `uv run python -m fplrank.data.projections register "<path to projection (N).csv>"`,
then `uv run python -m fplrank.data.projections check-ids --fetch` to compare its ids with live FPL data.

Projection files from paid services are licensed to you personally, so they must never be
committed or shared. The `.gitignore` blocks `*.csv` everywhere for that reason.
