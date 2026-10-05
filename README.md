# fpl-rank-solver

A Fantasy Premier League solver whose objective is **the probability of finishing at or above a
target rank**, not expected points. Built on [open-fpl-solver](https://github.com/solioanalytics/open-fpl-solver)
and the [HiGHS](https://highs.dev) MILP solver.

Why that is a different problem: your rank depends on your points *relative to the managers
around the target rank*, and on the spread of that relative score, not just its average. A
manager who is ahead should cover popular picks; one who is behind needs variance. An
EV-maximiser does neither. See [docs/research/problem-framing.md](docs/research/problem-framing.md).

## Status

Phase 0 (setup) done. The upstream EV solver runs offline against historical data, and a toy
spike shows a probability objective in HiGHS choosing differently from EV. Next:
define the objective precisely (Phase 1). See [docs/roadmap.md](docs/roadmap.md).

## Quick start

Needs [uv](https://docs.astral.sh/uv/). It installs Python 3.14 and all dependencies.

```bash
uv sync --group dev                       # create .venv with everything
uv run pytest                             # ~15 s; add -m "not slow" to skip real solves
uv run python scripts/smoke_baseline.py   # offline end-to-end EV solve on this season's data
uv run python -m fplrank.opt.toy          # EV vs rank-probability toy comparison
```

## Layout

```
src/fplrank/
  baseline.py        upstream EV solver, callable with in-memory inputs (works offline)
  data/              FPL API client with snapshots, historical loaders, offline input builders
  sim/               player score distributions, correlated scenarios        (empty)
  rank/              field model: EO by rank tier, points-to-rank            (empty)
  opt/               rank-objective formulations; toy.py is a spike
  eval/              backtesting harness                                      (empty)
vendor/open-fpl-solver/   unmodified upstream copy, pinned (see vendor/README.md)
scripts/             smoke test, upstream updater
tests/               pytest
docs/                roadmap, components list, research notes, decision records
data/                local only, git-ignored
```

## Credits and licence

The vendored solver is by Sertalp Bilal and contributors under Apache-2.0, dual-licensed with a
commercial licence; see [NOTICE](NOTICE). Historical data comes from
[vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League). This
project's own licence is not yet chosen (see `docs/decisions`).
