# Tasks for Claude Code

Maintained by Claude Code (PM + developer; see "How we work" in `CLAUDE.md`). Last updated: 2026-10-06.
Take the top task that isn't DONE. Open briefs are in `briefs/` next to this file; finished ones in `docs/briefs/`.

**When you finish or get stuck:** set the status (`DONE (PR #n)`, `IN PROGRESS (branch)`, `BLOCKED: why`),
add a dated line under "Notes from Claude Code", and move a finished task's brief to the repo's
`docs/briefs/`. Don't reorder or delete tasks; the PM tidies the list.

## Queue

| # | Task | Brief | Status |
|---|---|---|---|
| 1 | **Tidy-up (one-off, do first).** (a) Merge PR #10 (design doc thresholds). (b) Commit everything in `handover/` to the same paths in the repo (data log, phase-1 design notes, three derived 2025-26 datasets, four `scripts/elite64/` scripts; the 2025-26 ones expect vaastav files under `ref/`, so add a short note at the top of each saying where those come from), then empty `handover/`. (c) Move every brief in `briefs/` except B04b and B07b to a new repo folder `docs/briefs/`. (d) Delete the inbox's old `datasets/` and `docs/` folders (all of it is now in the repo or in `handover/`; the one screenshot there is already transcribed). (e) Paste `handover/docs/how-we-work.md` into the repo `CLAUDE.md` as a "How we work" section (don't commit that file on its own). (f) **Switch to Claude Code only:** commit `handover/docs/pm/pm-handover.md` to `docs/pm/`; move this `TASKS.md` to `docs/tasks/TASKS.md` and the open briefs (B04b, B07b) to `docs/tasks/briefs/`; from then on you are PM as well as developer, per the new CLAUDE.md section, and this inbox folder is retired (leave a one-line README saying so). Also merge PR #11 if you're happy with it (see pm-handover). | (this row) | DONE (PRs #10, #11 merged; tidy-up PR #12) |
| 2 | Points simulator: calibrate out of sample (tune 2023-24, test 2024-25, check 2025-26); fix haul frequency, premium players' means and blanks, defence correlation; minutes only from xMins; benchmark against a simple empirical model. | B07b | DONE (PR #11, merged; reduced scope, criteria not met - see note) |
| 3 | Elite ownership forecast: refit and backtest on the full 2025-26 season. | B04b | TODO |

Tasks 2 and 3 are independent.

## Later (briefs not written yet)

4. Single-GW candidate generator + evaluator (MILP plans across ownership weights, scored by P(finish ≤ X)). Waits for 2 and 3.
5. Value function V(gap, GWs left, chips). Waits for 4.
6. Policy backtests on 2025-26. Waits for 5.

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
