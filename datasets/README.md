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
from fplrank.data.elite import elite_meta, elite_ownership, eo_panel, load_eo, load_meta

load_eo(season="2025-26")              # listed players: season, gw, group, fpl_id, player, team, pos, eo (1.0 = 100%)
load_meta(season="2025-26")            # manager counts: season, gw, group, table, item, count, fpl_id
elite_meta("2025-26", "transfer_in")   # one meta table
elite_ownership("2025-26")             # squad ownership (not EO) by GW: count, own (0-1), quality
eo_panel("2025-26")                    # every FPL player x GW, unlisted filled from the residual
eo_panel(groups=["AE64"], gws=[4, 5])  # current season, one group
```

### Sources

| Files | Groups | Season / GWs | Source |
|---|---|---|---|
| `elite64_eo_2025-26.csv` (GW10-38), `elite64_meta_2025-26.csv` (GW1-38), `elite64_picks_2025-26.csv` (GW1 squads), `elite64_players_map_2025-26.csv`, `elite64_ownership_2025-26.csv` (GW1-38) | `AE64`, `E64` | 2025-26 | Transcribed by Claude (Cowork) on 2026-10-05 from every 2025-26 Solio Elite 64 graphic Alex collected (EO, captains and transfers, chips, free transfers, GW6 wildcard picks). Ownership rebuilt from them (see below). |
| `elite64_eo_2026-27.csv`, `elite64_meta_2026-27.csv` | `AE64` (Analytics Elite 64), `E64` (#Elite64, the template group) | 2026-27, GW1-5 | Hand-transcribed by Claude (Cowork) on 2026-10-05 from the public weekly graphics by @FPL_Spaceman / Solio: "Effective Ownership % for Analytics Elite 64 and #Elite64" and "Captains and Transfers ..." |

Each group is 64 managers (2025-26 AE64: 63 from GW29, when one manager was deactivated).

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
| `transfer_in`, `transfer_out` | player name (2025-26: complete lists) | no |
| `wc_pick_pct` | player name; % of GW6 wildcarders picking him (2025-26 only) | no |

`chip_active` "no chip" is blank in 2026-27 and `None` in 2025-26; both load as `none`. Read these
files with `keep_default_na=False`, or pandas turns `None` into a missing value. For player tables
`load_meta` adds `fpl_id` from `<source>_players_map_<season>.csv` (name -> id, with notes on
ambiguous names) or, without a map, from the season's EO listing (2026-27: transfer names that
were never listed have no id yet).

`<source>_ownership_<season>.csv`: **squad ownership**, not EO: `season, gw, fpl_id, web_name, pos`,
then per group `<group>_own` (managers owning him; fractional where squads were estimated) and
`<group>_own_pct`, plus a `quality` tier per GW:

| quality | meaning |
|---|---|
| `exact` | GW1, from the transcribed squads |
| `good (transfers exact, EO-anchored)` | carried forward exactly with the complete transfer lists |
| `estimated (GW4 WCs mirrored; GW6 WC table partial for D/M)` | after early wildcards whose new squads are only partly known |
| `anchored (GW32/35 WC squads inferred from EO + later sales)` | wildcard squads inferred from EO and later sales |

How it was rebuilt (Cowork, `scripts/reconstruct_elite_ownership.py`): the GW1 squads plus the
complete transfer lists carry ownership forward exactly between wildcards. GW6 wildcards use the
wildcard pick table (complete for G/F; D/M lists are top 10, so the shortfall is spread over the
kept squads). Other wildcard weeks start from "wildcarders mirror the group" and are then corrected
so ownership never goes negative before the next wildcard and never sits below listed EO minus
captaincy (and Free Hit managers). Held out (no EO anchor), the transfer-only rebuild tracks EO
within ~6-7 points on average over GW16-31. Re-running the script reproduces E64 exactly and AE64
within 1.5 managers (the committed file had negatives clipped in Cowork); the committed file is the
dataset of record.

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
remaining EO. Use the `censored` flag where that matters. FPL ids are re-numbered every season, so
for a past season (e.g. `eo_panel("2025-26")`) the universe comes from vaastav's `players_raw.csv`
for that season (downloaded once into `data/raw/`), with end-of-season ownership.

### Known quirks (Elite 64, 2026-27)

- GW3 AE64 "chips remaining" in the source graphic was stale (64/64/64). The file has the values
  recomputed from chip usage.
- GW1 and GW2 EO include Bench Boost benches (48-49 of 64 managers in GW1, 7-12 in GW2).
- GW3 was a heavy Free Hit week (AE64 21/64, E64 12/64), so its EO does not reflect squads.
- GW1 meta has only captains and chips.
- `fpl_id` was matched on `web_name` + team, falling back to name + position for players who
  changed club after the vaastav GW1 snapshot.

### Known quirks (Elite 64, 2025-26)

Kept as transcribed, never "fixed". `KNOWN_QUIRKS` in `tests/test_elite_data.py` lists each one
with its exact value, so the validation tests fail if the data changes or a new quirk appears.

- One AE64 manager deactivated in GW29: n = 63 from then on (ownership and chips scale with it).
- GW1 E64 captain and chip tables sum to 62; GW2 E64 captains sum to 63.
- GW3 E64 "no chip" is 62 in the source (should be 57), so chip_active sums to 69; GW3 E64
  `fts_remaining_next` sums to 63.
- E64 Bench Boost "remaining" is one lower than chip usage implies for GW13-18 (probably the BB
  missing from the GW1/GW3 chip tables).
- Transfers in always equal transfers out, but differ from the `fts_used` total (sum of k x managers
  making k transfers) in GW3 E64 (97 vs 101), GW4 AE64 (53 vs 54), GW7 E64 (44 vs 42), GW25 E64
  (71 vs 67) and GW38 (AE64 97 vs 89, E64 122 vs 99: the GW38 FT table disagrees with the lists).
- GW38 captains sum to 62 (AE64) and 63 (E64).
- `Barnes` is assumed to be Harvey Barnes (id 487); `James`, `Johnson`, `King` were resolved by
  crest or points (see the players map notes).
- EO graphics start at GW10, so `load_eo` / `eo_panel` cover GW10-38 only; meta and ownership cover
  GW1-38.

Derived tables (weekly summary, transfer flows vs last-GW points, biggest pile-ins) need vaastav's
points, so they are not committed: `uv run python scripts/elite_flows.py 2025-26` writes them to
`data/derived/elite64/`.

### Adding a new season or source

1. Save the files as `elite_ownership/<source>_eo_<season>.csv` and `<source>_meta_<season>.csv`
   using the formats above (season like `2027-28`, source a short lower-case name like `elite64` or
   `livefpl10k`). Group names come from the column names, so new groups need no code changes.
2. For a new source, add its group size to `GROUP_SIZE` in `tests/test_elite_data.py`.
3. Add a row to the Sources table above, with attribution, and list any quirks.
4. Run `uv run pytest tests/test_elite_data.py`. The validation tests run automatically for every
   file pair found (`fplrank.data.elite.available()`).
5. To extend a season with more GWs, append rows to the existing files. Keep the season/gw columns.
