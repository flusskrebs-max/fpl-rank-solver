# B06: Ingest the full 2025-26 Elite 64 dataset

Status: Done (2026-10-05) · Size: small · Depends on: B01 (loader), B01b (residual fill)

> PR https://github.com/flusskrebs-max/fpl-rank-solver/pull/8 (branch `b06-elite64-2025-26`), not merged yet.
> `elite_meta`, `elite_ownership`, `eo_panel("2025-26")` (2025-26 universe from vaastav players_raw:
> FPL ids differ by season), validation tests for both seasons with every quirk pinned in
> `KNOWN_QUIRKS`. Quirks NOT in this brief, kept as-is: GW2 E64 captains 63; GW3 E64 fts_remaining_next
> 63; E64 BB remaining 1 below usage GW13-18; transfers != Σk×managers in GW3 E64 (97/101), GW4 AE64
> (53/54), GW7 E64 (44/42), GW25 E64 (71/67). Rebuild script reproduces E64 exactly, AE64 within 1.5
> managers (committed file clipped negatives); committed file kept as record. No GW20-21 trial file
> existed. Item 5 (B04 on ownership flows) left for a B04 follow-up. pytest 50 passed, ruff clean.

## What's new

Cowork transcribed every 2025-26 Solio Elite 64 graphic Alex collected (inbox `datasets/elite64/`):

| File | Contents |
|---|---|
| `elite64_eo_2025-26.csv` | EO by player, GW10–38 (top ~10 per position per group), with `fpl_id` |
| `elite64_meta_2025-26.csv` | captains, FTs used/available, chips active/remaining, hits, full transfer in/out lists, GW1–38 (+ GW6 WC pick %) |
| `elite64_picks_2025-26.csv` | GW1 squad ownership (not EO) |
| `ownership_2025-26.csv` | **squad ownership** (counts and %) by player, GW1–38, both groups, with a `quality` tier per GW; built by `reconstruct_ownership_2025-26.py` |
| `eo_calculated_2025-26.csv` | calculated EO for every player GW1–38 (`eo_calc_*`) next to listed EO (`eo_listed_*`); built by `calc_eo_2025-26.py`. Off by ~5 points on average vs listed EO outside Free Hit weeks. Use listed where present. |
| `players_map_2025-26.csv` | transcribed name → FPL id (vaastav 2025-26 `players_raw`), with notes on ambiguous names |
| `weekly_summary_2025-26.csv`, `flows_player_gw_2025-26.csv`, `analyse_2025-26.py` | derived tables and the script that built them |

Validation done: every GW, transfers in = transfers out = Σ k × (managers making k transfers);
chip/captain/FT tables sum to the group size; listed EO ≤ expected total EO in every GW.
Known quirks (keep, don't "fix"): one AE64 manager deactivated in GW29 (n = 63 from then);
GW1 E64 sums to 62; GW3 E64 "no chip" is 62 in the source (should be 57); GW38 captains sum to 62/63
and its FT table disagrees with the transfer lists. `Barnes` is assumed to be Harvey Barnes.

## How ownership was rebuilt

GW1 squads (complete) + the complete transfer lists carry ownership forward exactly between
wildcards. GW6 wildcards use the WC pick table (complete for G/F; D/M lists are top 10, so the
shortfall is spread over the kept squads). Other wildcard weeks start with "WC managers mirror the
group", then are corrected so ownership never goes negative before the next wildcard and never sits
below listed EO minus captaincy (and minus Free Hit managers). Held out (no EO anchor), the
transfer-only rebuild tracks EO within ~6–7 points on average over GW16–31.

## Do

1. Copy into `datasets/elite_ownership/` (replace the GW20–21 trial file). Extend `fplrank.data.elite`
   to load `meta` tables (`elite_meta(season, table=...)`) and to use `fpl_id` directly.
2. Read CSVs with `keep_default_na=False` (the chip item `None` is a real label).
3. Add a test that re-runs the validation identities above for both seasons.
4. Don't commit `analyse_2025-26.py` outputs that need vaastav downloads; regenerate them in a
   `scripts/elite_flows.py` instead.

5. Add `elite_ownership(season)` returning the ownership table; B04 should model **ownership**
   transitions (exact transfer flows) and captaincy separately, and derive EO from them.

## Done when

`elite_meta("2025-26", "transfer_in")` and `eo_panel("2025-26")` load, and the validation test passes.
