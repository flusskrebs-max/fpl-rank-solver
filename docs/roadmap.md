# Roadmap

Phases are ordered by dependency, not by calendar. Each has an exit test so it is clear when it's done.
The season is live, so phases 2 and 3 should start collecting data early even while design continues.

## Phase 0: Setup ✅ (2026-10-05)

- Repo scaffold, upstream vendored at `ec65f5e` (2026-09-15), Python 3.14 + uv environment
- Upstream EV solver callable offline (`fplrank.baseline.solve_ev`), smoke test on 2026-27 data
- Toy spike: SAA probability objective in HiGHS picks differentials when chasing, template when level
- Docs: components list, problem framing, decision records, CLAUDE.md

**Exit:** `uv run pytest` green. ✅

## Phase 1: Define the objective (brainstorm)

- Pin down "rank X" (overall at season end? mini-league?), the decisions in scope (transfers,
  captaincy, bench order, chips, hits), and the planning horizon
- Decide what "better than baseline" means and how we'll measure it
- Choose the first formulation to build (see options in `research/problem-framing.md`)

**Exit:** ADR 0004 "Objective definition" written and agreed.

## Phase 2: Data foundations

- Live API client tested on a machine that can reach the API; weekly snapshot routine
- Sample managers near the target rank each GW → EO by tier, captaincy, chip usage
  - Started: Elite 64 EO, captains and chips for 2026-27 GW1-5 in `datasets/elite_ownership/`,
    loaded by `fplrank.data.elite` (B01)
- Points-to-rank thresholds from past seasons (what total did rank X need at GW t?)
- Projections ingestion for the chosen source(s)

**Exit:** for any GW this season, we can load: our team, projections, fixtures, EO at the target tier, and the current points gap to rank X.

## Phase 3: Uncertainty model

- Per-player per-GW score distributions consistent with projection means
- Correlations within teams and fixtures; scenario generator
- Calibration against last season's actual results

**Exit:** calibration report shows simulated event frequencies and tails in line with history.

## Phase 4: Field and rank model

- EO-weighted relative score per scenario
- Threshold model T_X and its uncertainty; check against historical rank curves

**Exit:** given a squad, we can estimate P(rank ≤ X after this GW) and it backtests sensibly.

## Phase 5: Rank-objective optimiser v1 (single GW)

- Refactor upstream constraints into a reusable model (objective-agnostic)
- First rank objective (likely generate-candidates-then-simulate, or an LP-friendly risk surrogate)
- Head-to-head against the EV baseline on the same inputs

**Exit:** for a set of historical GWs, v1 recommendations have higher estimated P(target) than EV recommendations, at a points cost we can quantify.

## Phase 6: Multi-period and chips

- Horizon planning under the rank objective; risk appetite as gap and GWs remaining change
- Chip timing (WC, FH, BB, TC) under the rank objective

**Exit:** backtested seasons show improved P(finish ≤ X) versus EV strategy.

## Phase 7: Weekly use

- One command (or scheduled task) that snapshots data, solves, and produces a short report:
  recommended moves, P(target) for each option, and the EV cost of the risk taken

**Exit:** used for real for 3 consecutive GWs.
