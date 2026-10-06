# Tasks

Maintained by Claude Code (PM + developer; see "How we work" in `CLAUDE.md`). Last updated: 2026-10-06.
The plan and release order are in `docs/roadmap.md`; finished-task notes are in `log.md` next to this file.

**Rules for the queue**
- One row = one PR, small enough to finish in a session. If it isn't, split it before starting.
- Take the top row that isn't DONE. A row is DONE when its PR is merged and its "done when" is met.
- When you finish or get stuck: set the status (`DONE (PR #n)`, `IN REVIEW (PR #n)`, `BLOCKED: why`),
  add one dated line to `log.md`, move the brief to `docs/briefs/`.
- A release ships when all its rows are DONE and Alex has used it once for a real GW. Note that in `log.md`.

## v0.1 Risk knob (ship for the next deadline)

| # | Task | Brief | Status |
|---|---|---|---|
| S1 | Ownership-weighted solver: xP·(1 + λ(EO − 1)), λ sweep with EV cost, CLI | S1 | DONE (PR #14) |
| C0 | Collector: add rank 100,000 to `threshold_ranks` (one config line) | C0 | DONE (PR #16) |
| C1 | Collector: sampled top-10k set (1 in 10 of ranks 1-10,000), so S1/S2 can use `--eo top10k` (moved from v0.3: this season's history can't be backfilled later; AE64 stays S1's default) | C1 | IN REVIEW (PR #22) |
| S1b | Free fallback projections from FPL `ep_next`, so S1 runs without a Solio file (and in cloud tests); offline test on a saved real team | S1b | IN REVIEW (PR #23) |
| S1c | EO at the deadline: `--eo-forecast` uses the B04 one-step forecast (`eo_mean`); by default λ applies to the first GW of the horizon only | S1c | TODO (Solio's EO is a broad-field forecast, so elite groups still need this) |
| S1d | `--eo solio`: read EO from a Solio export; compare with collected AE64/top-1000/top-10k EO for the same GW (ADR 0004) | (none) | IN REVIEW (PR #23) |
| W1 | `docs/weekly-run.md`: the pre-deadline steps on Alex's PC (download Solio, register, run S1) | (none) | IN REVIEW (PR #23) |

## v0.2 Pick λ for me

| # | Task | Brief | Status |
|---|---|---|---|
| S2a | Gap: T_X now + drift of the line against the EO group this season; `target_line` kept as the indicative absolute line (report only) | S2 | DONE (PR #17) |
| D1 | Loader for FPL-Core-Insights `playerstats.csv` (2025-26, 2026-27): per-GW `ep_next`, ownership, transfers | D1 | DONE (PR #20) |
| S2b | Variance table v(xP) by position × within-source xP quantile (not raw xP) from 2023-24, 2024-25 and 2025-26 (D1's `ep_next` as xP) | S2 | DONE (PR #21) |
| V1 | Realised-spread check: per-GW realised Δ = Σ (m − EO) × pts for top-1000 and Elite 64 managers this season vs S2's σ for the same squads; within ~20% → s = 1, else set s to match. Also outputs drift and σ²_base | V1 | IN REVIEW (PR #25) |
| S2c | `choose_lambda` + one-line report; CLI takes target rank and our points or rank | S2 | IN REVIEW (PR #24) |

## v0.3 Better EO

| # | Task | Brief | Status |
|---|---|---|---|
| B04b-1 | Refit the one-step EO model on 2025-26 with D1's `ep_next`; backtest vs persistence by week type | B04b | TODO |
| B04b-2 | Multi-GW EO forecast (1/3/6 GWs ahead) and wire it into S1 (S1c already does one step) | B04b | TODO |

## v0.4 Weekly report

| # | Task | Brief | Status |
|---|---|---|---|
| R1 | One command: snapshot, solve, write `reports/GW{n}.md` (moves, λ, P(target), EV cost); optional scheduled run | R1 | TODO |

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
