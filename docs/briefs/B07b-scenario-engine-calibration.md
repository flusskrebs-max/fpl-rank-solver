# B07b: Scenario engine, fix the tails and calibrate out of sample

Status: Ready · Size: medium · Depends on: B07 (branch `b07-scenario-engine`; merge it first, tests pass)

## Review of B07 (2026-10-05)

The structure is right (team-goal draws shared by team-mates, minutes states, 2025-26 scoring,
mean matching). Three problems matter for a rank objective, where the tails decide everything:

1. **Hauls are 1.4-2.5x too frequent** (10+: 4.9% vs 3.5%; 15+: 1.5% vs 0.6%). Too-fat tails make
   differentials look better than they are, so the solver would take too much risk.
2. **Captain candidates are wrong in both mean and shape**: simulated mean 7.95 vs xP 9.13, and blank
   rate 24% vs 12%. The goal-share caps (`MAX_GOAL_SHARE`, `MAX_RATE`) bind, and `_fit_rates` then
   pushes the remainder into minutes. Captaincy is the biggest single decision, so this has to be right.
3. **Defence correlation too low** (0.33 vs 0.53): understates the risk of doubling up on a defence.

And the calibration can't be trusted yet: it uses 10 GWs (vaastav only has 2025-26 xP for 11 GWs),
the same GWs used to set `SHARED_WEIGHT` and to eyeball the other constants, with only ~50
captain-candidate rows. "18/30 pass" is in-sample.

**Better data exists:** vaastav's 2023-24 has xP in 37/38 GWs and 2024-25 in 35/38.

## Do

1. **Rules by season.** A `rules` argument (2023-24/2024-25 = no defensive contributions; 2025-26 =
   with). Everything else unchanged.
2. **Proper split.** Fit/tune on 2023-24, test on 2024-25, final check on 2025-26 (11 GWs). Write the
   pass criteria in the report *before* running the test season, and don't retune after looking.
   List every tunable constant in one place with where it was fitted.
3. **Mean matching must not change minutes.** Minutes come only from xMins. If the rate cap binds,
   lift the cap (top players genuinely take 50-60% of their team's goal involvements in good fixtures)
   rather than giving more minutes; if non-attacking points exceed xP, accept the overshoot and
   report it. `match_report` should show the share of player-GWs with |sim mean − xP| > 0.2, and
   for the top 10 by xP each GW separately.
4. **Fix the tails.** Likely causes to test one at a time, measuring P(≥10)/P(≥15) by position each time:
   the independent extra team-goals draw (the 30% non-shared path adds variance), clean sheet +
   defensive contribution + bonus being independent, and the BPS noise.
5. **Defence correlation.** Make defensive contributions depend on the opponent's attack (busy
   defenders concede more), and goals conceded / clean sheets shared exactly within a side.
6. **Benchmark against a simple empirical model** (in the same report): points = draw from the
   empirical distribution of actual points for the same position × xP band × xMins band
   (from 2023-24), plus a shared team factor for correlation. If the event engine doesn't beat it on
   the held-out season (log score per player-GW, P(≥10)/P(≥15), and the three correlations), use the
   empirical one for now.
7. Score each version with one number as well as the table: mean log score (or CRPS) per player-GW
   on the test season.

## Done when

`docs/research/scenario-calibration.md` shows, on 2024-25 (held out): hauls within bands for every
position, top-10-xP mean within 0.2 of xP and blank rate within band, defence correlation within
band, and the comparison with the empirical benchmark.
