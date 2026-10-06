# Design notes (Phase 1 brainstorm, 2026-10-05)

> Archived 2026-10-06. Historical record only.

Historical record of the first PM brainstorm. Decisions that stuck are in `solver-design.md` and
`docs/decisions/`.

## Alex's vision

- Inputs per GW: projected points (as distributions) and projected ownership, per rank bracket.
- Forecast *future* ownership too, with wide error bars, learned from last season's week-by-week
  history. Captaincy drives it: a player lightly owned in GW6 who is the obvious GW8 captain will
  gain ownership by GW8.
- Use those to compute probabilities of the target outcome.
- Target: maximise P(win overall) or P(top 100), evaluated every week (season-end objective).
- Core trade-off: how much EV to pay for risk.
- Open question: include covariance (e.g. 3 defenders from one team) and individual player point
  distributions? Alex's prior: individual distributions less important.

## PM responses / proposals

1. **Target tier.** Top 100 of 10m+ is a 1-in-100,000 tail. Fine as the goal, but too rare to tune
   or backtest against directly. Objective = P(finish ≤ X) with X a parameter; develop and validate
   at X = 10k/1k, then run at 100. The EO tier should match X (elite EO, not overall).
2. **Individual distributions matter** for a top-100 target: you get there through hauls, so the
   right tail (and captaincy of high-ceiling players) is the signal. Covariance matters within your
   squad (defensive and attacking stacks) and against the field (owning the team-mate of a template player).
3. **Elite field as noisy solvers.** Model the top tier's future squads by running the EV solver on
   perturbed projections (upstream has a randomised mode); captaincy as a softmax over owned
   players' projections; calibrate both on history.
4. **Season objective via a value function.** V(gap to rank-X threshold, GWs left) = P(finish ≤ X) by
   simulation; each week maximise E[V(new gap, GWs left − 1)]. Risk appetite falls out (behind → seek
   variance, ahead → cover).
5. **v1 architecture:** scenario generator → field/EO model → candidate plans from the MILP → simulate
   each candidate's relative score → V lookup → pick the best, reporting each option's EV cost.
6. **Collect elite-tier picks** now via the API (done: B03 collector).

## Decisions from Alex (second round)

- Coding in Claude Code on Alex's PC; the Cowork project is PM.
- Target rank is an input, not hard-coded to top 100.
- The solver accounts for our remaining chips and the field's (chip weeks move EO).

## Data noted at the time

- Projections: Solio-format CSVs (`Pos, ID, Name, BV, SV, Team, {gw}_xMins, {gw}_Pts`), means only;
  three pre-season vintages and a GW6 file. Never committed (paid).
- Elite ownership: Solio/@FPL_Spaceman graphics for AE64 and E64 (see `docs/data-log.md`).
