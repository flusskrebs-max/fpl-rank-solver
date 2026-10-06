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

Scope: we build only the EO projection and the λ choice; Sertalp's vendored solver does the rest, run through
`uv run fplrank solve` (`docs/weekly-run.md`).

## v0.3 One command: `fplrank solve`

| # | Task | Brief | Status |
|---|---|---|---|
| CLEAN | Bug check and spring clean: dead code out, docs consolidated | (none) | DONE (PR #41) |
| RG1 | P(target) inputs from the data: line spread and drift against the group over full seasons, κ 0.75 (`--kappa`) | (none; `docs/research/rank-goal-inputs.md`) | IN REVIEW |
| Ship v0.3 | Logged real-deadline run of `fplrank solve --target` (replaces the v0.1 and v0.2 ship runs) | (none) | TODO |
| CLI 5 | One-page local Streamlit app that only fills in `fplrank solve` flags | (to write) | TODO |

## v0.4 Better EO

| # | Task | Brief | Status |
|---|---|---|---|
| EO1b | `--eo` uses fair persistence re-picked on next-GW xP (XI and captain per manager, `model/eo_blend.py`) instead of last GW's EO, armband herded for AE64/E64 | [EO1b](../briefs/EO1b-repick-eo.md) | DONE (PR #42) |
| EO1c | Recheck the herded re-pick against plain re-pick and persistence on GW6 (fresh file) and at ~GW10 | (none) | TODO |
| RP1 | 2025-26 replay: run `fplrank solve` week by week on last season and record when λ changes the decision (moves, captain) vs the EV plan | (to write) | TODO |
| Ship v0.4 | Logged real-deadline run with the re-picked EO | (none) | TODO |

## Parked (revisit once v0.4 is in use)

- Transfers in the EO forecast (ownership moves): the per-manager solve catches more of them than the re-pick
  (`docs/research/eo-blend.md`); worth it only if the re-pick misses big moves in use.
- Multi-GW EO (λ beyond the next GW); wildcard templates weighted by the expected wildcard share; fallers continuing
  (`docs/research/eo-patterns-2025-26.md`).
- `LIVE_WEIGHT` in `opt/ownership.py`: move `--eo elite` weight onto today's top 10k as ranks settle.
- Value function V(gap, GWs left, chips), rollout and policy backtests: a later check on S2's normal
  approximation, not a prerequisite.
- Top-100 cut-offs from a deeper sample; ranks 1 and 100k from the `past` field.
- Chips in the λ choice (ours and the field's) beyond what the upstream solver already does.

## Done

B01-B07b, C0, C1, D1, S1-S1d, S2a-S2c, V1, W1 (PRs #1-26); CLI 1-4 (PRs #32-37); EO ideas 1 and 3, `--eo elite`,
the EO blend (PRs #36, #38-40). R1/R2 (our own weekly harness) and B04b (refit of EO dynamics v0) were superseded:
`fplrank solve` replaced the harness, and the re-pick beat the v0 model.
