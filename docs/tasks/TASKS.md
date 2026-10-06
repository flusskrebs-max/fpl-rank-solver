# Tasks

Maintained by Claude Code (PM + developer; see "How we work" in `CLAUDE.md`). Last updated: 2026-10-06.
The plan and release order are in `docs/roadmap.md`; finished-task notes are in `log.md` next to this file.

**Rules for the queue**
- One row = one PR, small enough to finish in a session. If it isn't, split it before starting.
- Take the top row that isn't DONE. A row is DONE when its PR is merged and its "done when" is met.
- When you finish or get stuck: set the status (`DONE (PR #n)`, `IN PROGRESS (PR #n)`, `IN REVIEW (PR #n)`,
  `BLOCKED: why`), add one dated line to `log.md`, move the brief to `docs/briefs/`.
- Each release ends with a **Ship** row: Alex runs it for a real GW deadline and `log.md` gets a line
  (GW, λ chosen, what happened, anything to fix). The release ships when that row is DONE.

## v0.1 Risk knob

| # | Task | Brief | Status |
|---|---|---|---|
| S1 | Ownership-weighted solver: xP·(1 + λ(EO − 1)), λ sweep with EV cost, CLI | S1 | DONE (PR #14) |
| C0 | Collector: add rank 100,000 to `threshold_ranks` (one config line) | C0 | DONE (PR #16) |
| C1 | Collector: sampled top-10k set (1 in 10 of ranks 1-10,000), so S1/S2 can use `--eo top10k` | C1 | DONE (PR #22) |
| S1b | Free fallback projections from FPL `ep_next`, so S1 runs without a Solio file (and in cloud tests) | S1b | DONE (PR #23) |
| S1c | EO at the deadline: `--eo-forecast` uses the B04 one-step forecast; by default λ applies to the first GW only | S1c | DONE (PR #26) |
| S1d | `--eo solio`: read EO from a Solio export; compare with collected AE64/top-1000/top-10k EO (ADR 0004) | (none) | DONE (PR #23) |
| W1 | `docs/weekly-run.md`: the pre-deadline steps on Alex's PC (download Solio, register, run S1) | (none) | DONE (PR #23) |
| Ship v0.1 | Logged real-deadline run with the λ sweep | (none) | TODO |

## v0.2 Pick λ for me

| # | Task | Brief | Status |
|---|---|---|---|
| S2a | Gap: T_X now + drift of the line against the EO group this season; `target_line` kept as the indicative absolute line (report only) | S2 | DONE (PR #17) |
| D1 | Loader for FPL-Core-Insights `playerstats.csv` (2025-26, 2026-27): per-GW `ep_next`, ownership, transfers | D1 | DONE (PR #20) |
| S2b | Variance table v(xP) by position × within-source xP quantile from 2023-24, 2024-25 and 2025-26 | S2 | DONE (PR #21) |
| V1 | Realised-spread check vs S2's σ for top-1000, top-10k and Elite 64 squads; sets s | V1 | DONE (PR #25): s = 1 |
| S2c | `choose_lambda` + one-line report; CLI takes target rank and our points or rank | S2 | DONE (PR #24) |
| Ship v0.2 | Logged real-deadline run with λ chosen from the rank goal | (none) | TODO |

## v0.3 One command: `fplrank solve`

Scope (2026-10-06): we build only the EO projection and the λ choice; Sertalp's vendored solver does the
rest (team, projections, settings, solve, simulations). The one documented way to run it is
`uv run fplrank solve ... [--sims N]` (`docs/weekly-run.md`). R1 (our own harness) and R2 are superseded.

| # | Task | Brief | Status |
|---|---|---|---|
| CLI 1 | Every solve through his `solve_regular` | (none) | DONE (PR #32) |
| CLI 2 | `fplrank solve`: his flags plus `--eo`, `--target`, `--lam` | (none) | DONE (PR #33) |
| CLI 3 | `--sims N`: his simulations and sensitivity summary at the chosen λ | (none) | DONE (PR #35) |
| CLI 4 | Clean-up: remove our own team loading, projection picking, S1 CLI, weekly harness, toy spike; docs | (none) | IN REVIEW |
| CLI 5 | One-page local Streamlit app that only fills in `fplrank solve` flags | (to write) | TODO |
| Ship v0.3 | Logged real-deadline run of `fplrank solve` | (none) | TODO |

## v0.4 Better EO

| # | Task | Brief | Status |
|---|---|---|---|
| EO1 | EO projector refit (per-group flow model with ΔEV and price-band gap; `docs/research/eo-projector.md`), then wire into `--eo` | (none) | IN PROGRESS |
| B04b-1a | Refit the one-step EO model on 2025-26 with D1's `ep_next`; backtest vs persistence (GW10-38, AE64 and E64) | B04b | TODO |
| B04b-1b | Add blank/double, banked-FT and chip-week covariates; backtest by week type | B04b | TODO |
| B04b-1c | Captaincy: refit τ per group on 38 GWs of captain counts | B04b | TODO |
| B04b-2 | Multi-GW EO forecast (1/3/6 GWs ahead), backtested vs persistence; wire into S1 and the harness | B04b | TODO |
| RP1 | 2025-26 replay: run the harness week by week on last season and record when λ changes the decision (moves, captain) vs the EV plan | (to write) | TODO |
| Ship v0.4 | Logged real-deadline run with the multi-GW EO | (none) | TODO |

## Parked (revisit once v0.4 is in use)

- Event-engine simulator tuning (B07b follow-ups: haul frequency, defence correlation).
- Value function V(gap, GWs left, chips), rollout and policy backtests: a later check on S2's normal
  approximation, not a prerequisite.
- Top-100/1k cut-offs from a deeper sample (B03b leftover); ranks 1 and 100k from the `past` field.
- ClubElo fixture probabilities as an EO feature; FPL Review export as a second projection source.
- Chips in the λ choice (ours and the field's) beyond what the upstream solver already does.

## Done

B01, B01b, B02, B03 (PRs #1-4); B03b, B04, B05, B06, B07 (PRs #5-9); B05 follow-up (PR #10);
B07b (PR #11); task 1 tidy-up (PR #12); plan v1 + Elite 64 leagues in the collector (PR #13).
