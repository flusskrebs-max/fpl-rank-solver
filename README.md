# fpl-rank-solver

A Fantasy Premier League solver whose objective is **the probability of finishing at or above a
target rank**, not expected points. Built on [open-fpl-solver](https://github.com/solioanalytics/open-fpl-solver)
and the [HiGHS](https://highs.dev) MILP solver.

Why that is a different problem: your rank depends on your points *relative to the managers
around the target rank*, and on the spread of that relative score, not just its average. A
manager who is ahead should cover popular picks; one who is behind needs variance. An
EV-maximiser does neither. See [docs/research/problem-framing.md](docs/research/problem-framing.md).

## Status

v0.1 in progress: an ownership-weighted EV solver (S1, done) with a risk knob λ; next, choosing λ
from your rank goal (v0.2). Releases and the weekly loop: [docs/roadmap.md](docs/roadmap.md); the
full design: [docs/research/solver-design.md](docs/research/solver-design.md).

## Quick start

Needs [uv](https://docs.astral.sh/uv/). It installs Python 3.14 and all dependencies.

```bash
uv sync --group dev                       # create .venv with everything
uv run pytest                             # ~15 s; add -m "not slow" to skip real solves
uv run python scripts/smoke_baseline.py   # offline end-to-end EV solve on this season's data
uv run python -m fplrank.opt.toy          # EV vs rank-probability toy comparison
uv run python -m fplrank.opt.ownership --team <id> --eo AE64 --sweep   # plans across λ (live FPL API)
```

## Layout

```
src/fplrank/
  baseline.py        upstream EV solver, callable with in-memory inputs (works offline)
  data/              FPL API client with snapshots, historical loaders, offline input builders
  collect/           elite picks collector (top 1000, AE64, E64), rank cut-offs
  model/             elite EO dynamics (ownership.py)
  sim/               correlated scenario engine and its calibration (parked)
  opt/               ownership-weighted solver (ownership.py); toy.py is a spike
  rank/, eval/       placeholders (empty)
vendor/open-fpl-solver/   unmodified upstream copy, pinned (see vendor/README.md)
scripts/             smoke test, upstream updater
tests/               pytest
docs/                roadmap, task queue and briefs, research notes, decision records
data/                local only, git-ignored
```

## Credits and licence

The vendored solver is by Sertalp Bilal and contributors under Apache-2.0, dual-licensed with a
commercial licence; see [NOTICE](NOTICE). Historical data comes from
[vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League). This
project's own licence is not yet chosen (see `docs/decisions`).
