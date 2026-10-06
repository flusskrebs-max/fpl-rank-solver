# fpl-rank-solver

A Fantasy Premier League solver that picks the plan with the best **chance of finishing at or above a
target rank**, not the most expected points. It runs Sertalp's
[open-fpl-solver](https://github.com/solioanalytics/open-fpl-solver) (vendored, unchanged) and adds two
things: a projection of the field's effective ownership (EO), and the choice of how much to weigh it (λ).

Why that matters: your rank depends on your points *relative to the managers around the target rank*.
A manager who is ahead should cover popular picks; one who is behind needs variance. An EV-maximiser
does neither. See [docs/research/problem-framing.md](docs/research/problem-framing.md).

## How it works

Each projection is scaled by how much the chosen group owns the player, for the next GW only:

    xP' = xP × (1 + λ × (EO − 1))

λ > 0 covers the field's picks, λ < 0 favours differentials. `fplrank solve` runs his solver once per λ
from −0.3 to 0.3, scores each plan on the raw projections, and keeps the λ with the best P(reaching the
target line), from a normal approximation of our score relative to the group. It prints his normal
output for that plan, the EV it gives up, and P for every λ.

## Install

Needs [uv](https://docs.astral.sh/uv/), which installs Python 3.14 and the dependencies.

```bash
uv sync --group dev
```

## Run

```bash
uv run fplrank solve --team_id <your team id> --eo AE64 --target 10000
```

| Flag | Meaning |
|---|---|
| `--eo GROUP` | Whose EO to weigh against: `AE64`, `E64`, `elite` (the two averaged), `top1000`, `top10k` (all from the collector, last GW's EO with its chips taken out) or `solio` (Solio's EO export) |
| `--target RANK` | Choose λ for the best P(finishing in the top RANK) |
| `--lam λ` | Fix λ instead of choosing it (0 = his EV plan) |
| `--points N` | Our total points now (default: looked up from `--team_id`) |
| `--sims N` | Then run his simulations N times at the chosen λ and print his summary |

All of his `solve.py` flags (`--horizon`, `--use_wc`, `--banned`, `--team_data json`, ...) and his
settings files work unchanged. With no `--eo`, `--target` or `--lam` it is exactly his solver.

Before each deadline: put the Solio projections where his solver reads them, load your team, run the
command. The step-by-step version for Alex's PC is [docs/weekly-run.md](docs/weekly-run.md). The EO and
the target line come from the collector (`src/fplrank/collect/`), which runs twice a week on Alex's PC
([docs/collect-schedule.md](docs/collect-schedule.md)).

## Tests

```bash
uv run pytest                 # add -m "not slow" to skip real solves
uv run ruff check .
```

## Layout

```
src/fplrank/
  cli.py          `fplrank solve`: his solve.py plus the EO and λ choice
  upstream.py     imports his solver and patches it for one call (vendored code untouched)
  opt/            λ weighting, EO loading and plan scoring (ownership.py); λ choice (rank_goal.py)
  rank/           the target line and its drift against the EO group
  model/          variance table v(xP); EO research: naive field (his solver per manager) and the EO blend
  collect/        collector: picks, chips, transfers and ranks for top 1000, top 10k sample, AE64, E64
  data/           FPL API client with snapshots, vaastav and Core Insights loaders, Elite 64 data, Solio files
  eval/           realised-spread check of the λ choice's variance
vendor/open-fpl-solver/   his solver, pinned (never edited; scripts/update_upstream.sh updates it)
datasets/         small committed datasets (Elite 64 EO transcriptions)
docs/             roadmap, task queue, research notes, decision records
data/             local only, git-ignored (collector output, downloads, paid Solio files)
```

Where we are and what is next: [docs/roadmap.md](docs/roadmap.md), [docs/tasks/TASKS.md](docs/tasks/TASKS.md),
and the research summary in [docs/research/README.md](docs/research/README.md).

## Credits and licence

The vendored solver is by Sertalp Bilal and contributors under Apache-2.0, dual-licensed with a
commercial licence; see [NOTICE](NOTICE). Historical data comes from
[vaastav/Fantasy-Premier-League](https://github.com/vaastav/Fantasy-Premier-League). This
project's own licence is not yet chosen (see `docs/decisions`).
