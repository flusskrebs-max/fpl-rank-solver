# C0: Record the top-100k line each collector run

Status: Ready · Size: tiny · Release: v0.1 · Depends on: nothing

## Why

S2 needs the gap to the target-rank line and how that line grows. The collector saves T_X(now) for
ranks 100, 1k and 10k; adding 100k gives a wider curve (and a realistic target for testing) for one
extra standings page per run.

## Do

1. `config/manager_sets.toml`: `threshold_ranks = [100, 1000, 10000, 100000]`.
2. Check `_page_for(100000)` gives page 2000 and the `thresholds` table picks it up (unit test with a
   fixture snapshot, no network).

## Done when

A collector run on Alex's PC writes a `target_rank = 100000` row to `data/collected/thresholds.parquet`.
