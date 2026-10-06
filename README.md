# fpl-rank-solver

A Fantasy Premier League solver whose objective is **the probability of finishing at or above a
target rank**, not expected points. Built on [open-fpl-solver](https://github.com/solioanalytics/open-fpl-solver)
and the [HiGHS](https://highs.dev) MILP solver.

Why that is a different problem: your rank depends on your points *relative to the managers
around the target rank*, and on the spread of that relative score, not just its average. A
manager who is ahead should cover popular picks; one who is behind needs variance. An
EV-maximiser does neither. See [docs/research/problem-framing.md](docs/research/problem-framing.md).

## Status

Scope: we build only the EO projection and the λ choice. Sertalp's vendored solver does everything
else (team, projections, settings, the MILP, his simulations), run through one command,
`fplrank solve`. Releases: [docs/roadmap.md](docs/roadmap.md); the design:
[docs/research/solver-design.md](docs/research/solver-design.md).

## Quick start

Needs [uv](https://docs.astral.sh/uv/). It installs Python 3.14 and all dependencies.

```bash
uv sync --group dev
uv run pytest                 # add -m "not slow" to skip real solves
uv run fplrank solve --team_id <id> --eo AE64 --target 10000 --sims 50
```

`fplrank solve` takes all of his `solve.py` flags unchanged and adds `--eo`, `--target`, `--lam`,
`--points` and `--sims`. The weekly steps, including loading your team with his bookmarklet, are in
[docs/weekly-run.md](docs/weekly-run.md).

## Layout

```
src/fplrank/
  cli.py             `fplrank solve`: his solve.py plus the EO and λ choice
  upstream.py        imports his solver and patches it for one call (vendored code untouched)
  data/              FPL API client with snapshots, historical loaders, elite EO, Solio projection files
  collect/           elite picks collector (top 1000, AE64, E64), rank cut-offs
  model/             EO dynamics (ownership.py), variance table (variance.py)
  opt/               λ weighting and plan scoring (ownership.py), λ choice (rank_goal.py)
  rank/              target line and its drift against the EO group
  sim/, eval/        scenario engine (parked), realised-spread check
vendor/open-fpl-solver/   unmodified upstream copy, pinned (see vendor/README.md)
scripts/             collector, elite-data scripts, upstream updater
tests/               pytest
docs/                roadmap, task queue and briefs, research notes, decision records
data/                local only, git-ignored
```

## Credits and licence

The vendored solver is by Sertalp Bilal and contributors under Apache-2.0, dual-licensed with a
commercial licence; see [NOTICE](NOTICE). Historical data comes from
[vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League). This
project's own licence is not yet chosen (see `docs/decisions`).
