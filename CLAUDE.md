# CLAUDE.md

Context for Claude sessions working in this repo. Keep it short and current.

## What this is

A Fantasy Premier League solver that maximises **P(final rank ≤ X)** instead of expected points.
Built on the vendored open-fpl-solver (HiGHS via `highspy`). Owner: Alex, who is new to Claude
Code and git; explain git/GitHub steps briefly when they come up.

## How we work

Everything happens in Claude Code. You are both **PM** and **lead developer**; Alex sets direction.
The repo is the only memory: if it isn't committed, the next session won't know it.

**Each session**
1. Read `docs/roadmap.md` (releases), `docs/tasks/TASKS.md` (the queue) and `docs/pm/pm-handover.md` (PM context).
   Long chats are compacted automatically; anything that must survive goes in these files.
2. Take the top task that isn't DONE, or ask Alex if the queue is empty or a decision is his.
3. Finish by updating `TASKS.md` (status) and `docs/tasks/log.md` (one dated line) and, if anything durable changed,
   `docs/data-log.md`, `docs/decisions/` or the relevant `docs/research/` report.

**Planning (PM hat)**
- Before building anything non-trivial, write a short brief in `docs/tasks/briefs/` (why, what to do,
  checks, "done when"). Use plan mode for design work. Keep briefs small enough for one PR.
- Check work against `docs/research/solver-design.md` (architecture and test plan). Update it when a
  design decision changes, and record decisions that would be costly to reverse as ADRs.
- Prefer simple, testable models over clever ones; out-of-sample checks before trusting any fit;
  write pass criteria before looking at test results.

**Building (developer hat)**
- Do the work directly by default. Use subagents only when a job is large, self-contained and
  clearly cheaper to hand off (they cost more); give them the brief, the files they may touch and the
  checks, and review their diff before committing.
- Run `uv run pytest` and `uv run ruff check .` before every commit.
- One branch and PR per brief. Explain git/GitHub steps to Alex briefly when he needs to act.

**Talking to Alex**
- British spelling. Short and plain; no filler, no "genuinely", no "great question".
- Lead with what changed and what needs his decision.

**Never**
- Commit paid projection files (Solio CSVs) or anything under `data/`.
- Edit `vendor/open-fpl-solver/` (update it with `scripts/update_upstream.sh`).

## Where things are

- `src/fplrank/baseline.py`: `solve_ev(my_data, projections, bootstrap, fixtures, options)` runs the
  upstream EV model with in-memory inputs. Every rank-objective idea is compared against this.
- `src/fplrank/data/`: `fpl_api.py` (live API, saves dated snapshots), `historical.py` (vaastav
  season files), `offline.py` (rebuild API-shaped inputs from history; placeholder projections),
  `elite.py` (elite-group EO, meta tables and 2025-26 squad ownership from `datasets/elite_ownership/`;
  unlisted EO = censored, not zero),
  `projections.py` (Solio exports → long `vintage_gw, gw, fpl_id, ... xmins, xpts`; registry of
  files in `data/projections/`; `latest(gw)` = newest file made at or before a GW).
- `src/fplrank/collect/elite_picks.py`: collects picks/chips/transfers/ranks for the manager sets in
  `config/manager_sets.toml` (default top 1000) into `data/collected/*.parquet`, plus deadline EO in
  the B01 long shape. Resumable from snapshots; scheduled on Alex's PC (`docs/collect-schedule.md`).
- `src/fplrank/model/ownership.py`: ownership dynamics v0. `forecast_eo(group, gw_next, state, model)`
  = next-GW EO with an 80% band (XI share logistic transition + captain softmax; chips as input).
  `fit_default()`, `backtest()`; results in `docs/research/ownership-dynamics-v0.md`.
- `notebooks/`: analysis as cell-marked `.py` files (`# %%`); open in VS Code or run with uv.
- `src/fplrank/sim/scenarios.py`: scenario engine ([A]). `simulate(projections, fixtures, S, H, seed, rules=season)`
  -> int points `[S, H, players]`, correlated via shared team goals, means matched to projections.
  All tunable constants in `Params`. `sim/calibration.py`: tuned on 2023-24, tested on 2024-25, checked on
  2025-26 against an empirical benchmark (`docs/research/scenario-calibration.md`).
- `docs/tasks/TASKS.md` (the queue, grouped by release), `docs/tasks/log.md` (dated notes), `docs/tasks/briefs/`
  (open briefs); `docs/briefs/` (finished briefs); `docs/pm/pm-handover.md` (PM context); `docs/data-log.md` (what data we have and first findings).
- `docs/weekly-run.md`: Alex's pre-deadline steps (update, register Solio files, run S1).
- `scripts/elite64/`: Cowork's original 2025-26/2026-27 dataset scripts, kept as written (not linted).
- `datasets/`: small committed datasets (free/public sources only); see `datasets/README.md`.
- `src/fplrank/opt/ownership.py`: S1 ownership-weighted solve. `adjust_projections(proj, eo, lam)`,
  `solve_with_ownership(...)`, `sweep(...)` (plans per λ with EV, EV cost, EO held, exposure);
  CLI `uv run python -m fplrank.opt.ownership --team <id> --eo AE64|E64|top1000 --sweep` (live API).
- `src/fplrank/rank/target.py`: S2a. `line_drift(rank, group)` (the gap's drift against the EO group) and
  `target_line(rank)` (indicative absolute line for the report); `uv run python -m fplrank.rank.target 10000`.
- `src/fplrank/opt/rank_goal.py`: S2c. `plan_moments`, `choose_lambda` (P of reaching the target line per λ);
  CLI: add `--target-rank 10000 [--points N]` to the S1 command. `src/fplrank/model/variance.py`: S2b v(xP) table.
- `src/fplrank/weekly.py`: R1. `uv run python -m fplrank.weekly --team <id> --target 10000` runs S1 + S2c and writes
  `reports/GW{n}.md` (git-ignored); `render(...)` builds the markdown.
- `src/fplrank/opt/toy.py`: spike showing the SAA probability objective in HiGHS.
- `vendor/open-fpl-solver/`: upstream, pinned. **Never edit**; update with `scripts/update_upstream.sh`.
- `docs/roadmap.md` (releases and the weekly loop), `docs/research/` (thinking; `data-sources.md` = which
  data we use and why),
  `docs/decisions/` (ADRs: add one for any decision that would be expensive to reverse).

## Commands

```bash
uv sync --group dev
uv run pytest                 # all tests; -m "not slow" skips real solves
uv run ruff check . && uv run ruff format .
uv run python scripts/smoke_baseline.py
uv run python -m fplrank.data.projections register <file> [...]   # then: check-ids --fetch
uv run python -m fplrank.collect.elite_picks collect [--top N]     # FPL API: Alex's PC only
uv run python -m fplrank.opt.ownership --team <id> --eo AE64 --sweep  # S1 plans per λ (live API)
```

## Conventions

- British spelling in prose and docs.
- New modelling code goes in `src/fplrank/<area>/`, with tests in `tests/`. Mark tests that run real
  MILPs `@pytest.mark.slow` and ones that download data `@pytest.mark.network`.
- Upstream code ported into `src/` keeps an attribution comment naming the source file and commit.
- `data/` and all CSVs are git-ignored, except `datasets/**/*.csv` (curated, free-to-share data
  only). Paid projection files must never be committed.
- HiGHS solves LP, MILP and convex QP, but **not** mixed-integer QP. Variance/risk terms in a MILP
  must be linear (scenarios, MAD, CVaR, piecewise) or handled outside the MILP.
- Snapshot any live API data used in a solve so the solve can be reproduced.

## Environment notes (as of 2026-10-05)

- Cloud sessions reach GitHub (git + raw.githubusercontent.com) and PyPI, but **not**
  fantasy.premierleague.com or most FPL sites (blocked by the network allowlist). Use historical
  data or snapshots in the cloud; run live API calls on Alex's machine or after the domain is allowed.
- The cloud container is ephemeral. Push to GitHub or save to the claude.ai Project before ending.
- Cloud sandbox has 2 CPUs; scenario MILPs may need a bigger machine.
- vaastav's 2026-27 files only covered GW1 on 2026-10-05 (the live season was further on), so
  "next GW" in offline runs reflects the data, not the real calendar.
