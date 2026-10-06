# B03: Elite picks collector (runs on Alex's PC)

Status: Done (2026-10-05) · Size: medium · Depends on: B01 (output shape)

> Items 1-4, 6: PR #4, merged. `fplrank.collect.elite_picks`; first run top 1000 GW1-5 (58 min,
> 0 failures); report `docs/research/top1000-vs-elite64.md` (top1000 ≈ E64, AE64 differs more).
> Scheduled tasks "fplrank collect (Fri)" / "(Tue)" 20:00 created on Alex's PC (catch-up on),
> test run OK. Item 5: PR https://github.com/flusskrebs-max/fpl-rank-solver/pull/5, not merged yet.
> `past_seasons` + `thresholds` tables, `season_cutoffs`, report `docs/research/rank-cutoffs.md`:
> top 10k/100k covered 8/8 seasons, top 1k 3/8, top 100 0/8 (today's top 1000 mostly finished far
> from the top in past seasons; needs another sample). T_X after GW5: 100→429, 1k→414, 10k→398.

## Goal

Build our own, complete version of the Elite 64 data from the official FPL API: for a set of
managers, every GW's picks, captain, vice, chip, transfers and hits. This replaces screenshots
going forward and backfills this season's GWs.

## Manager sets (config file, extendable)

- `overall_top_N`: top N of the overall league (league 314), N configurable (start with 1000).
  Taken from the standings at collection time.
- `named_lists`: hand-maintained lists of team ids (e.g. Elite 64 members if Alex can get the ids).

## Endpoints (all public, no login)

- `leagues-classic/314/standings/?page_standings=P` (50 per page)
- `entry/{id}/event/{gw}/picks/` (picks, multipliers, active chip, hits)
- `entry/{id}/history/` (chips used with GW, rank and points by GW, transfers/hits by GW)
- `entry/{id}/transfers/`
- `bootstrap-static/`, `fixtures/`, `event/{gw}/live/` (for context and points)

## Do

1. `src/fplrank/collect/elite_picks.py` using `fplrank.data.fpl_api.FplApi` (snapshots every response).
   Be polite: ~2 requests/second, retries with backoff, resumable (skip what's already stored).
2. Output (git-ignored `data/collected/`): parquet tables `picks`, `chips`, `transfers`, `ranks`,
   keyed by `season, gw, entry_id`. Plus a derived `eo` table in the **same long shape as B01**
   (`season, gw, group, fpl_id, eo`) with `group = "top1000"` etc.
3. Backfill: for each manager, all GWs played so far this season.
   Note survivorship: today's top 1000 were not the top 1000 in GW1. Store each manager's rank by GW
   (from history) so we can later reconstruct "top 1000 as of GW t" approximately.
4. A `collect` CLI and a Windows Task Scheduler recipe (in `docs/`) to run it every Friday evening
   and every Tuesday (post-GW, for chips/transfers).
5. Rank thresholds: from each sampled manager's `entry/{id}/history/`, store the `past` list
   (season, total_points, rank) in a `past_seasons` table. Fit points-vs-rank for 2025/26 and earlier and
   report the top 100 / 1k / 10k / 100k end-of-season cut-offs. Also store the overall league standings
   page for ranks 100, 1000, 10000 every GW (`T_X(now)` snapshots).
6. Sanity check against the Elite 64 dataset: for players listed in both, our top-1000 EO should be
   in the same ballpark (report the comparison, don't assert).

## Done when

- One command collects GW1-to-now for the top 1000 and produces the `eo` table.
- A table of end-of-season cut-offs (top 100/1k/10k/100k) for 2025/26 and earlier from the `past` sample.
- A short report (markdown) compares top-1000 EO vs AE64/E64 for GW1-5.
