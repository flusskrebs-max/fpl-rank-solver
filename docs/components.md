# What we'll need

Everything a rank-probability solver depends on, grouped by layer. Status: ✅ done, 🟡 partial, ⬜ not started.

## 1. Data

| Need | Why | Source options | Status |
|---|---|---|---|
| Live game state: players, prices, ownership %, fixtures, deadlines | Inputs to every solve | FPL API `bootstrap-static/`, `fixtures/` | 🟡 client written, untested live |
| Your team: squad, bank, FTs, chips, rank history | Starting state; current gap to target | FPL API `entry/{id}/history/`, `my-team` (auth) or upstream's `generate_team_json` | 🟡 via upstream |
| Projections (means): xPts and xMins per player per GW | Core of any FPL solve | Solio, FPL Review, Mikkel, or our own | ⬜ need to choose |
| Projection *uncertainty*: distributions, not just means | The rank objective lives on variance and correlation | Rarely provided; likely our own model on top of the means | ⬜ |
| Historical player results by GW (points, minutes, price, selected) | Backtesting; calibrating distributions | vaastav/Fantasy-Premier-League | ✅ loader |
| Points needed for rank X, by GW, past seasons | Turns "rank X" into a points threshold and its uncertainty | Our own collection; community archives | ⬜ |
| Effective ownership (EO) at the target rank tier | Rank moves with *relative* points; top-10k EO ≠ overall EO | Sample managers near rank X via `leagues-classic/314/standings/` + their picks | ⬜ |
| Field chip usage and transfer behaviour | EO shifts on BB/TC/FH weeks and as the template evolves | Same manager sample, tracked weekly | ⬜ |
| Snapshot store | Live data disappears; solves must be reproducible | `data/snapshots/` locally, maybe cloud storage later | 🟡 |

## 2. Models

| Need | Notes | Status |
|---|---|---|
| Player score distribution per GW | Mixture: plays or not, 60+ mins, goals, assists, clean sheet, saves, bonus, defensive contributions. Fat right tail matters (hauls). | ⬜ |
| Correlation structure | Same team (CS shared by GK+DEF, goal ↔ assist), opponents (your striker vs their keeper), match tempo. Drives how much a stack raises variance. | ⬜ |
| Scenario generator | S joint samples of all player points over the horizon, consistent with the means we're given | ⬜ |
| Field model | EO per player by rank tier, captaincy share (EO > 100%), how the field's squad changes over the horizon | ⬜ |
| Rank model | Map my total and the field's distribution to a rank. Simple version: random threshold T_X; fuller: rank from the field's score distribution per scenario | ⬜ |
| Risk appetite rule | How aggressive to be given gap to target and GWs remaining (the dynamic part) | ⬜ |

## 3. Optimisation

| Need | Notes | Status |
|---|---|---|
| EV baseline (upstream MILP) | Comparison point and candidate generator | ✅ `fplrank.baseline` |
| Reusable constraint model | Upstream builds constraints and objective in one 850-line function; we need squad/transfer/chip constraints separable from the objective | ⬜ port + refactor |
| Probability objective, exact-ish | Sample average approximation with per-scenario binaries (toy works, but 20-40 s for 12 players and 400 scenarios: will not scale naively) | 🟡 spike |
| Probability objective, scalable | Candidates to test: LP-friendly risk terms (MAD, CVaR, downside deviation of relative score), generate-many-plans-then-simulate, decomposition, smaller candidate pools | ⬜ |
| Multi-period and chips under the rank objective | Rolling horizon; when to take risk; chip timing | ⬜ |
| Optional: Gurobi | Upstream supports it via MPS files; free academic licences exist. Only if HiGHS is too slow | ⬜ |

## 4. Evaluation

| Need | Notes | Status |
|---|---|---|
| Backtest harness | Replay a past season week by week with only the information available at the time | ⬜ |
| Strategy comparison | Same start, EV strategy vs rank strategy, across many simulated seasons; compare P(finish ≤ X) | ⬜ |
| Calibration checks | Are the score distributions honest? (event frequencies, tail calibration) | ⬜ |

## 5. Engineering and project setup

| Need | Status |
|---|---|
| Git repo with upstream vendored and pinned | ✅ |
| Python 3.14 + uv environment, highspy, pandas, numpy, scipy | ✅ |
| Tests (pytest) and lint (ruff) | ✅ |
| Docs: roadmap, decisions, research notes, CLAUDE.md | ✅ |
| GitHub remote (private) + issues as backlog | ⬜ needs GitHub connected |
| CI: run tests on each push (GitHub Actions) | ⬜ |
| Somewhere that can reach the FPL API (your machine, or allow the domain for cloud sessions) | ⬜ |
| Weekly data collection job (snapshots, field sample) | ⬜ |
| Output: a weekly report or small dashboard of recommended moves and their P(target) | ⬜ |

## 6. Decisions only Alex can make

1. **What exactly is "rank X"?** Overall rank at season end (most likely), a mini-league finish,
   a GW rank, or something like "top 10k at any point"? Each is a different objective.
2. **Projection source.** Which service do you subscribe to, if any? Our uncertainty model sits on top of it.
3. **Where it runs.** Cloud sessions (need fantasy.premierleague.com allowed) or your computer.
4. **Licence for this code.** Private for now is fine; upstream's commercial clause matters only if you'd ever sell it.
