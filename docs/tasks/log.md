# Task log

Dated notes from Claude Code, newest last. Moved out of `TASKS.md` on 2026-10-06 so the queue stays short.
One line per finished task or decision from now on; detail belongs in the PR and the research reports.

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
  Solves take ~2 s each on a 4-GW horizon and ~80 s on 8 GWs, so the CLI defaults to upstream's 600 s limit
  (that commit missed PR #14 and went in with plan v2). A λ ≠ 0 plan can show a slightly negative EV cost
  because upstream maximises a discounted objective (decay 0.9, FT and bank values), not raw horizon EV.
- 2026-10-06, plan v2: queue cut into one-PR slices grouped into releases v0.1-v0.4 (`docs/roadmap.md`);
  data-source review added (`docs/research/data-sources.md`): vaastav no longer updates weekly, so
  FPL-Core-Insights `ep_next` replaces B04b's proxy and joins S2's variance table; notes moved to this file.
- 2026-10-06, critical review of the S2 plan (triaged in another thread): gap now uses the line's drift against the EO group
  (no double-counted field growth); μ shrunk by κ = 0.3; season total = plan horizon + λ = 0 base; new V1 (realised spread) and
  S1c (EO at the deadline); C1 moved to v0.1; S2b bands by xP quantile; S1 docstring: centring at EO = 1 is a scale choice.
- 2026-10-06, C0: collector records the top-100k line too (page 2000, one extra request per run). Live check: 377 points after GW5.
- 2026-10-06, S2a: `fplrank.rank.target`. `line_drift(rank, group)`: line's GW gain - group's mean net GW points,
  with past lines interpolated from collected managers' overall ranks. GW2-5: top 10k vs AE64 +2.4 a GW, vs E64 +4.1,
  vs top1000 -10.0 (biased: today's top 1000 were selected for scoring well). `target_line(rank)` (report only):
  line now + GWs left x past seasons' pace; after GW5 top 10k 398 now, ~2589 ± 95 at GW38.
- 2026-10-06: ADR 0004 (accepted by Alex): keep S1's xP adjustment, equivalent to the community "risk" term `w·EO·xP`
  plus a (1 − λ) rescaling; no vendor changes. New S1d (`--eo solio`) blocked on a Solio export with EO; S1c on hold.
- 2026-10-06: PRs #15-17 merged (plan v2, C0, S2a).
- 2026-10-06, C1: collector `[sampled]` sets; `top10k` = every 10th of ranks 1-10,000. First run started on Alex's PC.
- 2026-10-06, S1b: `projections.from_ep_next(bootstrap, fixtures, horizon)` and S1 `--projections ep_next` (also the
  automatic fallback when no Solio file is registered); offline test on a saved real GW6 team (`tests/fixtures/gw6_live/`)
  checks λ = 0 equals `solve_ev`. Finding: `ep_next` is FPL's form-based estimate, not a projection (Groß 15.5 for GW6,
  so the plan captains him); fine for tests and history, not for real decisions.
- 2026-10-06, S1d: `--eo solio` reads Solio's per-GW EO forecast (matched to FPL ids by name + team) and S1 now takes
  a different EO per GW. Live GW6 sweep on the rank-1 team: EV plan for λ -0.1..0.1, Haaland captain for λ ≥ 0.2 (cost 3.4).
- 2026-10-06, W1: `docs/weekly-run.md`, the pre-deadline steps on Alex's PC.
- 2026-10-06, collector fix (with C1): FPL's picks endpoint shows the team after automatic subs once a GW is played, so
  EO was post-sub (João Pedro GW5 AE64 0% instead of 6%). `deadline_picks` swaps auto-subs back; EO tables rebuilt.
  LiveFPL `/EO` (all players, top 10k + overall, current GW) is the manual cross-check; no history or per-manager data.
- 2026-10-06, D1: `fplrank.data.core_insights` (playerstats loader, `xp_from_ep_next` with gw = N, checked vs vaastav).
- 2026-10-06, S2b: `fplrank.model.variance` (v by position x within-source xP decile; table in `docs/research/variance-table.md`).
- 2026-10-06, S2c: `fplrank.opt.rank_goal` + S1 CLI `--target-rank [--points]`. Live, rank-1 team's squad, top 10k, AE64,
  GW6, 33 GWs left: P 53% / 36% / 20% with 450 / 398 / 340 points; across λ P moves by at most ~1.3 points (season sd ~72
  dwarfs a 4-GW plan's effect), matching the review's "a few points, not tens" check. Ties go to λ near 0.
- 2026-10-06, queue tidy: v0.1/v0.2 rows done (PRs #22-26); harness (R1, R2) moved ahead of Better EO as v0.3;
  B04b split into 1a/1b/1c/2; 2025-26 replay (RP1) added; each release ends with a logged real-deadline "Ship" row.
- 2026-10-06, V1: realised spread vs S2's sd on GW1-5: ratio 0.97-0.99 (top 1000, top 10k), 0.82-0.86 (AE64, E64),
  all within 20%, so s = 1. Report: `docs/research/realised-spread.md` (with drift by group).
- 2026-10-06, S1c: `--eo-forecast` (B04 one-step forecast as deadline EO) and λ on the next GW only by default
  (`--lam-all-gws` keeps the old behaviour).
- 2026-10-06, R1 v1: `uv run python -m fplrank.weekly --team <id> --target 10000` writes `reports/GW{n}.md` (git-ignored):
  recommended plan, P(target) vs the EV plan, EV cost, two nearest alternatives, full sweep. Loud warning on `ep_next`.
  S1 CLI helpers shared (`pick_projections`, `pick_eo`, `rank_goal_table`). `run(Inputs, mode)` harness; `--mode simulate`
  reserved for R2 (upstream's `randomized` noise, plan in the brief). Not yet run live.
- 2026-10-06, S1 CLI: ran S1c live on Alex's PC (team 157924, GW6), fine; Alex's failure was the literal `<id>` in PowerShell.
  Added a progress line per λ (about 30-40s each, so a full sweep is ~5 min). Odd: λ = -0.2 beat λ = 0 on 5-GW EV (-0.91), so
  the λ = 0 solve isn't reaching the optimum; not yet looked at.
- 2026-10-06, CLI 1/4: `solve_ev` now runs every solve through Sertalp's `solve_regular` (as simulations.py does): λ-adjusted
  projections go in as his `data/fplrank.csv`, his settings files apply, his solutions come back. Our own prep/solve calls removed.
- 2026-10-06, CLI 2/4: `uv run fplrank solve` = his solve.py (his settings and flags unchanged) plus `--eo`, `--target`, `--lam`:
  his projections are λ-scaled on read, one solve per λ, best P(target) chosen, his output for that plan under a short λ block.
