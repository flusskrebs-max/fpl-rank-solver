# Roadmap

What we're shipping, in order. The queue of one-PR tasks is `docs/tasks/TASKS.md`; the full design
(including the parked simulator route) is `docs/research/solver-design.md`.

**Product:** give it your team, your points (or rank), a target rank and the GW, and it returns this
week's plan with the risk weight λ that maximises P(finishing at or above the target), and what that
risk costs in expected points.

## Releases

Each release is something Alex can run for a real deadline. Ship it, use it once, then improve.
A release counts as shipped only when its "Ship" row in TASKS.md is done: a real-deadline run logged in
`docs/tasks/log.md`.

| Release | Alex can… | Tasks | Exit |
|---|---|---|---|
| **v0.1 Risk knob** | Run the EV solve with a λ knob and see plans across λ with their EV cost | S1, C0, C1, S1b, S1c, S1d, W1 | Logged real-deadline run |
| **v0.2 Pick λ for me** | Enter target rank + points; get λ, P(target) vs the EV plan, EV cost | S2a, D1, S2b, V1, S2c | Sensible λ across a grid of gaps and GWs left (S2 checks); logged real-deadline run |
| **v0.3 Weekly harness** | One command from current EO, projections, team, rank and rank goal to the GW report; a noise mode shows how stable the plan is | R1, R2 | Logged real-deadline run; then used for 3 consecutive GWs |
| **v0.4 Better EO** | Use a forecast of how elite EO moves over the horizon, then see on 2025-26 when λ changes decisions | B04b-1a, B04b-1b, B04b-1c, B04b-2, RP1 | Forecast beats persistence out of sample; S1 and the harness use it; logged real-deadline run |

The harness moved ahead of Better EO on 2026-10-06: R1 uses today's one-step EO, so it no longer waits for
B04b-2, and Alex gets one command sooner.

After v0.4: check S2's normal approximation against simulation and backtests (parked list in TASKS.md),
and only build the value function if the check shows it changes decisions.

## Weekly loop (from v0.1)

| When | What | Where |
|---|---|---|
| Tue 20:00 | Collector: final ranks, points, transfers; T_X(now) | Scheduled on Alex's PC |
| Before the deadline | Download Solio, register it, run the solver, read the plan | Alex's PC (`docs/weekly-run.md`) |
| Fri 20:00 | Collector: the new GW's picks, captains, chips (deadline EO) | Scheduled on Alex's PC |
| After the GW | One line in `docs/tasks/log.md`: λ chosen, what happened, anything to fix next | Claude Code |

The last row is the iteration loop: each GW's use should feed one small fix or task into the queue.

## Done so far

- Setup: repo, vendored open-fpl-solver (pinned), uv + Python 3.14, CI (ruff + pytest on every push).
- Data: Elite 64 2025-26 and 2026-27 GW1-5; collector (top 1000, AE64, E64) twice weekly; Solio
  projection loader; end-of-season rank cut-offs; T_X(now) for ranks 100/1k/10k.
- Models: EO dynamics v0 (beats persistence by ~20% on 2026-27 GW2-5); scenario engine v0 with an
  out-of-sample calibration (parked: hauls too often; the empirical benchmark is the fallback).

Data sources and what each is for: `docs/research/data-sources.md`. What the data showed: `docs/data-log.md`.
