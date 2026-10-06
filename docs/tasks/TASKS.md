# Tasks for Claude Code

Maintained by Claude Code (PM + developer; see "How we work" in `CLAUDE.md`). Last updated: 2026-10-06.
Take the top task that isn't DONE. Open briefs are in `briefs/` next to this file; finished ones in `docs/briefs/`.

**When you finish or get stuck:** set the status (`DONE (PR #n)`, `IN PROGRESS (branch)`, `BLOCKED: why`),
add a dated line under "Notes from Claude Code", and move a finished task's brief to `docs/briefs/`.

## Queue

Plan agreed with Alex at the 2026-10-06 stock take: three core products, simple first, iterate.
(1) an ownership-weighted EV solver, (2) a choice of the ownership weight from the rank goal, and
(3) a multi-GW elite EO forecast feeding (1). The full simulator / value-function route is parked.

| # | Task | Brief | Status |
|---|---|---|---|
| 1 | Tidy-up: merge PRs #10-#11, move the handover, briefs and this queue into the repo, retire the inbox | (none) | DONE (PR #12) |
| 2 | Points simulator: out-of-sample calibration vs an empirical benchmark | B07b | DONE (PR #11; criteria not met, see note) |
| 4 | **Ownership-weighted solver**: EV solve with xP adjusted by λ x EO; λ sweep with EV cost | S1 | IN REVIEW (PR #14) |
| 5 | **λ from the rank goal**: normal approximation of the relative score; choose λ from gap, target rank, GWs left | S2 | TODO |
| 3 | **Elite EO forecast**: refit on 2025-26 and forecast several GWs ahead | B04b | TODO |

Order: 4, 5, then 3 (row numbers are historical). 4 works with today's EO (collector or Elite 64);
3 later improves its EO input.

## Parked (revisit once the core works)

- Event-engine simulator tuning (B07b follow-ups: haul frequency, defence correlation).
- Value function V(gap, GWs left, chips) and policy backtests on 2025-26: a later check on S2's
  normal approximation, not a prerequisite.
- B03b leftovers: ranks 1/100k and a ~500-manager deeper sample for top-100/1k cut-offs.

## Done

B01, B01b, B02, B03 (PRs #1-4); B03b, B04, B05, B06, B07 (PRs #5-9); B05 follow-up (PR #10); B07b (PR #11).

## Notes from Claude Code

- 2026-10-05: merged PRs #5-9 into main (150d522); 63 tests pass. PR #10 opened for the design doc thresholds.
- 2026-10-06, B07b: PR #11. Alex chose a reduced scope: core out-of-sample test + benchmark, no further tuning,
  1,000 scenarios per GW. Tuned on 2023-24, tested on 2024-25, checked on 2025-26 (criteria committed first).
  Neither model passes on 2024-25. Engine: best log score (1.56 vs 1.66), 69% of means within 0.2 of xP,
  attacker correlation in band, but ordinary players haul too often (10+: 4.0% vs 2.9%). Empirical benchmark:
  haul rates mostly in band, top-10 mean right, means only by band. Report recommends the benchmark for
  haul-sensitive use for now. Biggest fix: projected minutes for old seasons from xP band x recent minutes
  (recent minutes alone ignore team news). "Busy defenders" DC link tested: no effect. Brief not yet moved
  to docs/briefs/ (that's part of the tidy-up task).
- 2026-10-06, task 1 (tidy-up): merged PR #10 and PR #11 (both CI green). Committed the handover files
  (data log, phase-1 design notes, PM handover, three derived 2025-26 datasets, four `scripts/elite64/`
  originals with a header saying where their `ref/` vaastav inputs come from; excluded from ruff). Moved the
  finished briefs to `docs/briefs/` (including B07b, now finished) and B04b to `docs/tasks/briefs/`; this file
  is now `docs/tasks/TASKS.md`; "How we work" is in CLAUDE.md. Before deleting the inbox's `datasets/` and
  `docs/`, checked every file was identical to its copy in the repo or `handover/` (CSV line endings aside);
  only Cowork's 2026-27 dataset README (content already in `datasets/README.md`) and the GW1-5 chart PNG had
  no copy. Corrected the data log: the 2025-26 transfer identity fails in GW3/4/7/25 too, not only GW38.
- Overlap to tidy later: `scripts/elite64/analyse_2025-26.py` and `reconstruct_ownership_2025-26.py` are the
  originals of `scripts/elite_flows.py` and `scripts/reconstruct_elite_ownership.py` (ports from B06).
- B03b is listed as done (PR #5) but was built to the earlier B03 item-5 spec: the table is `thresholds`
  (not `rank_lines`), it tracks ranks 100/1k/10k (not 1 and 100k), and the extra ~500-manager sample from
  standings pages 200/2000 was not added, so top-100/1k cut-offs still have gaps.
- Fixed while doing task 1: `fplrank.data.elite.available()` took `elite64_eo_calculated_2025-26.csv` for a
  dataset with season "calculated_2025-26" (6 tests failed); it now only accepts `<source>_eo_<YYYY-YY>.csv`.
- 2026-10-06, stock take with Alex: simplified the plan to three core products (queue above); new briefs S1
  and S2; B04b gains a multi-GW step. The collector now reads the AE64 (league 1291919) and E64 (league
  38543) members each run (config `leagues`), so their EO is collected exactly from now on.
- 2026-10-06, S1: merged PR #13. Built `src/fplrank/opt/ownership.py`: xP' = xP x (1 + λ(EO − 1)) (centred
  at EO = 1, see solver-design §4 [C]), `solve_with_ownership`, `sweep` (dedupes plans by this GW's XI,
  bench, captain and moves; EV cost vs λ = 0), and a CLI for any team id
  (`uv run python -m fplrank.opt.ownership --team <id> --eo AE64|E64|top1000 --sweep`). EO = latest GW of the
  collector's `eo.parquet`, falling back to the Elite 64 graphics for AE64/E64; unlisted players are 0 and
  the same EO is used for every GW of the horizon (B04b will replace this). Tests cover the brief's three
  checks with real solves on 2025-26 data. Live check on the rank-1 team, GW6, horizon 4, top1000 GW5 EO:
  λ −0.3..−0.2 sells Haaland (EV cost 6.7), λ −0.1..0.05 is the EV plan, λ 0.1 captains Haaland (cost 0.8),
  λ 0.2..0.3 sells Szoboszlai for Groß (cost 3.4); exposure falls from 89 to 67 across the range.
  Solves finish in ~2 s each (12 s for four, API included), so the time limit (now upstream's 600 s by
  default) is not binding. A λ ≠ 0 plan can show a slightly negative EV cost because upstream maximises a
  discounted objective (decay 0.9, FT and bank values), not the raw horizon EV we report.
