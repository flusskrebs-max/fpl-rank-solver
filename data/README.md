# data/

Everything in here except this file is git-ignored.

| Folder | Contents | Written by |
|---|---|---|
| `raw/vaastav/<season>/` | Historical season files from vaastav/Fantasy-Premier-League | `fplrank.data.historical` |
| `snapshots/<endpoint>/<timestamp>.json` | Dated copies of live FPL API responses | `fplrank.data.fpl_api.FplApi` |
| `projections/` | Projection CSVs (Solio, FPL Review, Mikkel, our own) | you |

Projection files from paid services are licensed to you personally, so they must never be
committed or shared. The `.gitignore` blocks `*.csv` everywhere for that reason.
