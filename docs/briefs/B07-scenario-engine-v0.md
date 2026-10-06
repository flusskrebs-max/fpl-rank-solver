# B07: Scenario engine v0 ([A] in solver-design)

Status: Done (2026-10-05) · Size: medium · Depends on: B02 (projection means)

> PR https://github.com/flusskrebs-max/fpl-rank-solver/pull/9 (branch `b07-scenario-engine`), not merged yet.
> `fplrank.sim.scenarios.simulate` (int16 [S, H, players]; shared team-goals draws; BPS-style bonus;
> means fitted per player-fixture), `fplrank.sim.calibration`, report `docs/research/scenario-calibration.md`.
> 10k x 6 GWs x 562 players: 35-45 s. vaastav 2025-26 xP is 0 in 27/38 GWs, so calibration uses the
> 10 populated GWs. Blanks and attacker correlation in band; hauls too frequent (P>=10 4.9% vs 3.5%),
> defence correlation low (0.33 vs 0.53), top captain candidates under their mean (8.0 vs 9.1).
> FPL bootstrap team strengths are all 0 this season; team xG comes from projections. pytest 44, ruff clean.

## Goal

Correlated simulated points for every player over the next H GWs (S scenarios), consistent with
the projection means. This is the "uncertainty" half of the rank objective.

## Do

1. `src/fplrank/sim/scenarios.py`: `simulate(projections, fixtures, S, H, seed) -> array[S, H, players]`.
2. Per player per fixture, a mixture model:
   - minutes state: 0 / 1–59 / 60+ (from projected xMins);
   - events: goals, assists (Poisson), clean sheet (Bernoulli for team), saves, bonus, defensive
     contributions (2025-26 rules), cards; FPL scoring by position.
   - Scale event rates so the simulated mean matches the projection mean per player per GW.
3. Correlation through shared team-fixture factors: one draw per fixture for team goals for/against,
   so a team's attackers rise together and its defenders share clean sheets.
4. Doubles = two fixtures; blanks = zero.
5. Calibrate against 2025-26 actuals (vaastav `merged_gw.csv`, using its `xP` as the "projection"):
   P(blank ≤2), P(≥10), P(≥15) by position and price band; within-team correlation of attacker
   points; captain-candidate haul rates.

## Checks (tests)

- Means match inputs within Monte Carlo error; no negative minutes; points are integers.
- Two players from the same team are positively correlated in attack, defenders share clean sheets.
- Report: `docs/research/scenario-calibration.md` with simulated vs actual frequencies and bootstrap bands.

## Done when

`simulate` runs 10,000 scenarios × 6 GWs × all players in under a minute on Alex's PC and the
calibration report is in the repo.
