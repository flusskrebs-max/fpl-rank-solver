# C1: Sampled top-10k set in the collector

Status: Ready · Size: small · Release: v0.3 · Depends on: nothing (C0 is in the same file)

## Why

The target tier's EO should match the target rank. We have top 1000, AE64 and E64 exactly, but nothing
for top 10k, the main development target. A 1-in-10 sample of ranks 1-10,000 (~1,000 managers) gives EO
to about ±1.5 points at 50%, for the cost of one more top-1000-sized run. No public archive of past
top-10k EO exists, so the sooner this runs the longer our own history.

## Do

1. Config: `[sampled]` table, e.g. `top10k = { ranks = 10000, every = 10 }` → set and EO group `top10k`.
2. `members()`: take every 10th entry from standings pages 1-200 (50 a page), so 200 standings
   requests plus the sampled managers' picks. Reuse the existing snapshot cache and resumability.
3. Make `--eo top10k` available in S1/S2 once the first run has landed.
4. Tests with fixture standings pages; no network.

## Checks

- First run: EO for the top 10 players sits between top-1000 EO and overall `selected_by_percent`.
- Optional manual check against LiveFPL's top-10k page for one GW (don't scrape it).

## Done when

A scheduled run writes a `top10k` EO group to `data/collected/eo.parquet`, and run time is noted in
`docs/collect-schedule.md`.
