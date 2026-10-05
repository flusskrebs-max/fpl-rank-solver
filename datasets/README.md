# datasets/

Small, curated datasets that **are** committed, unlike `data/`, which holds local downloads and
paid files and is git-ignored. Only add data here that is free to share: our own transcriptions of
public posts, data we collect ourselves, or openly licensed files. Paid projections (Solio, FPL
Review, etc.) never go here.

`.gitignore` blocks `*.csv` everywhere but makes an exception for `datasets/**/*.csv`.

## elite_ownership/

Effective ownership (EO) and behaviour of elite manager groups, by gameweek. Load it with
`fplrank.data.elite`:

```python
from fplrank.data.elite import eo_panel, load_eo, load_meta

load_eo()     # listed players: season, gw, group, fpl_id, player, team, pos, eo (1.0 = 100%)
load_meta()   # manager counts: season, gw, group, table, item, count
eo_panel(groups=["AE64"], gws=[4, 5])   # every FPL player x GW, unlisted filled from the residual
```

### Sources

| Files | Groups | Season / GWs | Source |
|---|---|---|---|
| `elite64_eo_2026-27.csv`, `elite64_meta_2026-27.csv` | `AE64` (Analytics Elite 64), `E64` (#Elite64, the template group) | 2026-27, GW1-5 | Hand-transcribed by Claude (Cowork) on 2026-10-05 from the public weekly graphics by @FPL_Spaceman / Solio: "Effective Ownership % for Analytics Elite 64 and #Elite64" and "Captains and Transfers ..." |

Each group is 64 managers.

### Licence and attribution

The underlying figures belong to their publishers, who should be credited whenever this data is
used or shown: **@FPL_Spaceman / Solio Analytics** for the Elite 64 files. These files are our
transcriptions of graphics posted publicly. They are not covered by the project's code licence and
are not an official export. If a publisher asks us to remove their data, remove it.

### File formats

`<source>_eo_<season>.csv`: one row per listed player per GW.

- `season, gw, pos, player, team, fpl_id`, then one `<group>_eo` column per group (EO in **percent**).
- EO counts captaincy double and Triple Captain triple, and includes bench players for managers on
  Bench Boost.
- `pos` is G/D/M/F. `fpl_id` is the FPL element id for that season. Every row must have one.

`<source>_meta_<season>.csv`: long format `season, gw, table, item`, then one manager-count column
per group (lower-case group name). Tables:

| table | item | partition (sums to group size)? |
|---|---|---|
| `captain` | player name | yes |
| `chip_active` | WC / FH / TC / BB, blank = no chip (loaded as `none`) | yes |
| `chips_remaining` | WC / FH / TC / BB / "No chips" | no |
| `fts_used` | 0-4 free transfers used, or WC / FH | yes |
| `fts_remaining_next` | 1-5 free transfers for next GW | yes |
| `hits` | 0, -4, -8, ... | yes |
| `transfer_in`, `transfer_out` | player name | no |

### Censored, not zero

Sources list only the top players per position (about 7-10). A player missing from a GW's list has
an EO somewhere below that week's cutoff, **not** zero. Never treat a missing row as 0%.

- A *listed* row carries a value for every group, so a listed 0% (e.g. Kinsky, AE64, GW3) is a real
  observation, not a censored one.
- Listed players cover 90-98% of each group's total EO (a manager's total is 11 starters + captain,
  plus 1 for Triple Captain and 4 for a Bench Boost bench). `tests/test_elite_data.py` requires
  85-100%.

**How `eo_panel` fills unlisted players (residual fill).** For each group and GW, the expected total
EO is `11 + 1 + TC share + 4 x BB share` (shares from the `chip_active` counts; `expected_totals`).
The residual, expected total minus the listed total (never below 0), is spread across every
unlisted player in the FPL player universe in proportion to their overall FPL ownership
(`selected_by_percent`). Each player is capped at the listing cutoff, the smallest *positive*
listed EO for their position in that group and GW. Listed zeros are excluded because they are
players listed for the other group's sake. Any amount removed by a cap is passed on to the
players still below theirs, so each group/GW total matches the expected total. Filled cells
have `censored = True` and `fill_method = "residual"`; listed cells keep their value and have
`fill_method = "listed"`. The universe defaults to the latest saved `bootstrap-static` snapshot
(`FplApi().bootstrap()` saves one), or pass `universe=`. Two limits: ownership is from the snapshot
date, not each GW, and overall ownership is only a rough guide to how elite managers spread their
remaining EO. Use the `censored` flag where that matters.

### Known quirks (Elite 64, 2026-27)

- GW3 AE64 "chips remaining" in the source graphic was stale (64/64/64). The file has the values
  recomputed from chip usage.
- GW1 and GW2 EO include Bench Boost benches (48-49 of 64 managers in GW1, 7-12 in GW2).
- GW3 was a heavy Free Hit week (AE64 21/64, E64 12/64), so its EO does not reflect squads.
- GW1 meta has only captains and chips.
- `fpl_id` was matched on `web_name` + team, falling back to name + position for players who
  changed club after the vaastav GW1 snapshot.

### Adding a new season or source

1. Save the files as `elite_ownership/<source>_eo_<season>.csv` and `<source>_meta_<season>.csv`
   using the formats above (season like `2027-28`, source a short lower-case name like `elite64` or
   `livefpl10k`). Group names come from the column names, so new groups need no code changes.
2. For a new source, add its group size to `GROUP_SIZE` in `tests/test_elite_data.py`.
3. Add a row to the Sources table above, with attribution, and list any quirks.
4. Run `uv run pytest tests/test_elite_data.py`. The validation tests run automatically for every
   file pair found (`fplrank.data.elite.available()`).
5. To extend a season with more GWs, append rows to the existing files. Keep the season/gw columns.
