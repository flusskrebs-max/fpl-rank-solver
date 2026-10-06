# Roadmap

What we're shipping, in order. The queue of one-PR tasks is `docs/tasks/TASKS.md`; the full design
is `docs/research/solver-design.md`.

**Product:** give it your team, your points (or rank), a target rank and the GW, and it returns this
week's plan with the risk weight λ that maximises P(finishing at or above the target), and what that
risk costs in expected points.

## Releases

Each release is something Alex can run for a real deadline. Ship it, use it once, then improve.
A release counts as shipped only when its "Ship" row in TASKS.md is done: a real-deadline run logged in
`docs/tasks/log.md`.

| Release | Alex can… | Tasks | Exit |
|---|---|---|---|
| **v0.1 Risk knob** | Run the EV solve with a λ knob and see plans across λ with their EV cost | S1, C0, C1, S1b, S1c, S1d, W1 | Built; shipped as part of v0.3 |
| **v0.2 Pick λ for me** | Enter target rank + points; get λ, P(target) vs the EV plan, EV cost | S2a, D1, S2b, V1, S2c | Built; shipped as part of v0.3 |
| **v0.3 One command** | `fplrank solve`: his solver with his flags, plus `--eo`, `--target`, `--lam`, `--sims` | CLI 1-4, CLEAN, CLI 5 | Logged real-deadline run |
| **v0.4 Better EO** | `--eo` re-picks each manager's XI and captain on next-GW xP instead of repeating last GW's EO; see on 2025-26 when λ changes decisions | EO1b, EO1c, RP1 | Re-pick still beats persistence at ~GW10; logged real-deadline run |

Our own weekly harness (R1/R2) was dropped on 2026-10-06 for `fplrank solve`, and the B04b refit of EO dynamics v0
for the re-pick, which did better (`docs/research/eo-blend.md`).

After v0.4: check S2's normal approximation against backtests (parked list in TASKS.md), and only build the value
function if the check shows it changes decisions.

## Weekly loop (from v0.1)

| When | What | Where |
|---|---|---|
| Tue 20:00 | Collector: final ranks, points, transfers; T_X(now) | Scheduled on Alex's PC |
| Before the deadline | Download Solio, load the team, run `fplrank solve`, read the plan | Alex's PC (`docs/weekly-run.md`) |
| Fri 20:00 | Collector: the new GW's picks, captains, chips (deadline EO) | Scheduled on Alex's PC |
| After the GW | One line in `docs/tasks/log.md`: λ chosen, what happened, anything to fix next | Claude Code |

The last row is the iteration loop: each GW's use should feed one small fix or task into the queue.

## Done so far

- Setup: repo, vendored open-fpl-solver (pinned), uv + Python 3.14, CI (ruff + pytest on every push).
- Data: Elite 64 2025-26 and 2026-27 GW1-5; collector (top 1000, AE64, E64) twice weekly; Solio
  projection loader; end-of-season rank cut-offs; T_X(now) for ranks 100/1k/10k.
- Models: variance table v(xP) and the λ choice (S2); next-GW EO research: fair persistence (in `--eo`), the
  XI and captain re-pick (EO error a third below persistence, as good as running his solver per manager).
  EO dynamics v0, the EO flow model and our own scenario engine were tried and removed (`docs/research/archive/`).

Data sources and what each is for: `docs/research/data-sources.md`. What the data showed: `docs/data-log.md`.
