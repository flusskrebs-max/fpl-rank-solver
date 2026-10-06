# B03b: Rank-line data from the collector

Status: Ready · Size: small · Depends on: B03 (branch `b03-elite-picks-collector`, tests pass when merged with main)

## Why

The objective is final overall rank (solver-design §4). The solver needs `T_X(now)`, today's points
for rank X, every GW; and, for the spread term, end-of-season cut-offs from past seasons.

## Do

1. `build()`: add a `past_seasons` table from every member's `entry/{id}/history/` snapshot
   (`past` list: season_name, total_points, rank). Already in the snapshots, so no new requests.
2. `collect()`: each run, fetch the overall league standings pages holding ranks 1, 100, 1,000,
   10,000 and 100,000 (pages 1, 2, 20, 200, 2000) and store `rank_lines` (`season, gw, collected_at,
   rank, total_points`). One request per rank.
3. Report: end-of-season cut-offs for 2025/26 (and earlier) at ranks 100 / 1k / 10k / 100k,
   read off the `past_seasons` sample (nearest ranks either side, interpolate). Say how many managers
   sit near each rank; top-1000 members give dense coverage near the top only, so add
   `overall_top = [1000]` plus a sample of e.g. 500 managers from standings pages 200 and 2000.
4. Tests on fixture snapshots.

## Done when

`rank_lines` has this GW's rows, and `docs/research/rank-cutoffs.md` gives the 2025/26 cut-offs.
