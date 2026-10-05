# CLAUDE.md

Context for Claude sessions working in this repo. Keep it short and current.

## What this is

A Fantasy Premier League solver that maximises **P(final rank ≤ X)** instead of expected points.
Built on the vendored open-fpl-solver (HiGHS via `highspy`). Owner: Alex, who is new to Claude
Code and git; explain git/GitHub steps briefly when they come up.

## Where things are

- `src/fplrank/baseline.py`: `solve_ev(my_data, projections, bootstrap, fixtures, options)` runs the
  upstream EV model with in-memory inputs. Every rank-objective idea is compared against this.
- `src/fplrank/data/`: `fpl_api.py` (live API, saves dated snapshots), `historical.py` (vaastav
  season files), `offline.py` (rebuild API-shaped inputs from history; placeholder projections).
- `src/fplrank/opt/toy.py`: spike showing the SAA probability objective in HiGHS.
- `vendor/open-fpl-solver/`: upstream, pinned. **Never edit**; update with `scripts/update_upstream.sh`.
- `docs/roadmap.md` (phases), `docs/components.md` (what we need), `docs/research/` (thinking),
  `docs/decisions/` (ADRs: add one for any decision that would be expensive to reverse).

## Commands

```bash
uv sync --group dev
uv run pytest                 # all tests; -m "not slow" skips real solves
uv run ruff check . && uv run ruff format .
uv run python scripts/smoke_baseline.py
```

## Conventions

- British spelling in prose and docs.
- New modelling code goes in `src/fplrank/<area>/`, with tests in `tests/`. Mark tests that run real
  MILPs `@pytest.mark.slow` and ones that download data `@pytest.mark.network`.
- Upstream code ported into `src/` keeps an attribution comment naming the source file and commit.
- `data/` and all CSVs are git-ignored. Paid projection files must never be committed.
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
