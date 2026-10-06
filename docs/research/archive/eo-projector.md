# EO projector: proposal (2026-10-06)

> Archived 2026-10-06. The proposal behind the EO work: idea 1 failed (`eo-flow-v1.md`), idea 3 ran (`../eo-naive-field.md`), and the agreed blend ended in the XI and captain re-pick (`../eo-blend.md`). `model/ownership.py` and `--eo-forecast` named below have since been removed.

Status: proposal. Idea 1 built and tested 2026-10-06: fails the pass criteria (`eo-flow-v1.md`). Idea 3 built and tested 2026-10-06 (`eo-naive-field.md`); approach agreed below. Scope: this project builds only the EO projection and the λ
choice; Sertalp's solver runs unchanged. This note covers Alex's three ideas (thread "EO projector",
2026-10-06) and which to try first.

## Where we are

- `model/ownership.py` (B04, v0) forecasts next-GW EO for a group: XI share moves by a 4-parameter
  logistic on last week's share and next GW's xP; captaincy is a softmax on xP; chips are an input.
  `fit_default()` fits it, `forecast_eo()` returns EO with an 80% band. S1c (`--eo-forecast`) uses it.
- Fitted on 2026-27 GW1-5 only: four transitions of the top 1000. Each projected point multiplies
  the odds of being started by about 1.7; last week's points add nothing once xP is known.
- Backtest: about 20% lower error than "next week = this week" (persistence) over GW2-5, but worse
  in quiet GW2. Four transitions is very little (`docs/research/ownership-dynamics-v0.md`).
- Not yet used: the full 2025-26 Elite 64 season (37 transitions × 2 groups, exact transfer lists,
  rebuilt squad ownership) and this season's exact AE64/E64 picks from the collector. B04b in
  `TASKS.md` already plans the refit on these.

## The frame for all three ideas

    ownership[t+1] = ownership[t] + bought[t+1] − sold[t+1]

Persistence says bought = sold = 0. Each idea is a different guess at the flow terms. EO then
follows from ownership through v0's XI and captain parts (unchanged). Elite groups make only about
1.2 transfers per manager per GW, so most players barely move (mean weekly change ≈ 3.7 points of
ownership); the value is in the few big moves (AE64 had 149 moves of 20+ points in 2025-26).

## Idea 1: general response, "x EV change means y EO change"

One equation for every player and GW, fitted on 2025-26 (and 2026-27 as it grows):

    Δ logit(ownership) = a + b · ΔEV + c · gap + (chip-week and banked-FT terms)

- `ΔEV`: change in the player's projected points over the next few GWs since last week (news,
  fixtures, role). For 2025-26, FPL's `ep_next` from Core Insights (one GW only); for 2026-27, Solio.
- `gap`: projected points of the best same-position player within £0.5m above his price, minus his.
  A big positive gap is sell pressure on owners; a negative one is buy pull on non-owners.
- This is v0's equation with better inputs, so it is cheap: the data is in hand and the fit is a
  few parameters. The answer to "x EV means y EO" is the slope `b` (and the `gap` slope), which we
  can quote per position and price band.

Limit: it treats players one at a time, so it can't see that a sale funds a specific buy.

## Idea 2: GW-specific surges and falls (en-masse flows)

The big moves come in pairs, usually a premium sold to fund a premium. From 2025-26 (ownership
points, AE64 / E64):

| GW | out | in |
|---|---|---|
| 12 | Gabriel −93 / −91 | Virgil +54 / +72 |
| 18 | B.Fernandes −98 / −86 | Cunha +84 / +72, Ekitiké +34 / +69 |
| 22 | Cunha −96 / −72 | (spread) |
| 23 | Foden −59 / −65 | B.Fernandes +56 / +56 |
| 25 | Saka −72 / −56 | Rice +53 / +45 |

Two things make these predictable: the flows have to balance (each group's transfers in = out =
free transfers used, which we know per GW), and they follow fixtures and doubles more than hauls
(data-log, 2026-10-05). So the "this GW" view is: a small list of likely sells (held players with a
large `gap` or a bad run of fixtures) and likely buys (the best players they could be swapped into
for the same money), with the transfer budget split between them. I'd not build this as its own
model; idea 3 produces exactly this list, and idea 1's `gap` term captures most of it. These five
weeks become test cases: a projector that misses them isn't good enough.

## Idea 3: a "naive field" from Sertalp's solver

Run his solver with λ = 0 (pure EV) as a sensible manager would, and read off who it buys and sells:

- 2026-27: for each AE64/E64 manager we collect (real squads, bank and FTs), run `solve_regular` on
  the latest Solio file with his default settings. The share of the group the solver moves from A
  to B is a predicted flow. That is 64 short solves per group per GW (kept quick with
  a short horizon and time limit). Selling prices are approximate (current price) unless the
  collector stores purchase prices.
- Variants Alex suggested: 1 FT, 2 FTs, banked FTs, and a wildcard run. The wildcard run is the
  useful one for wildcard weeks (GW6/GW32-style clusters), where idea 1 is weakest.
- 2025-26 can't be done the same way: we only have GW1 squads (later squads are rebuilt in aggregate)
  and only one-GW `ep_next`, which makes the solver short-sighted. A cut-down version (one modal
  "group template" squad per GW, horizon 1) is possible but weak.
- Use: either as the forecast itself ("solver flow"), or as one more input in idea 1 (Δ logit
  ownership on solver-predicted flow). The second is safer: the field doesn't follow a solver exactly.

## Agreed approach (Alex, 2026-10-06)

`fplrank solve` applies λ to the next GW only, and EO for GW+2 onwards only enters plan scoring. So solver time goes on the next GW, and the long horizon only needs the field's direction of travel.
- Weekly (~10 min): cluster the AE64+E64 squads (deduped on squad, bank, FTs) to ~20 representatives weighted by count; one H3 solve each with a time limit, giving next-GW flows, blended with persistence. Then ~4 H8 wildcard solves with varied settings, averaged into EO_wc. EO for GW+k = next-GW EO + w(k) × (EO_wc − next-GW EO), with w(k) fitted.
- Occasionally (overnight): the full every-squad H8 run with variants, on 2-3 deadlines to fit the persistence weight and w(k), then every ~5 GWs to check. The blend only has to approximate it. Score on xP-weighted EO error.
- Time-limit every field solve: the field isn't optimal, so near-optimal plans are fine and the runtime stops growing steeply with horizon.

First evidence for it (`eo-naive-field.md`): the per-manager run's EO gain over persistence comes mostly from re-picking XI and captain, which the H3 representative solves keep; a blend that only scales current EO and mixes in wildcard templates stays close to persistence.

## Recommendation: what to try first

1. **Idea 1 first** (it is B04b-1a with `ΔEV` and `gap` added). Data in hand, no solves, small
   change, and it gives the general "x EV → y EO" answer straight away.
2. **Idea 3 next**, on 2026-27 only, once there are 3-4 GWs of collected AE64/E64 squads and Solio
   files for the same weeks. Add its predicted flow to idea 1 and keep it only if the backtest says so.
3. Idea 2 isn't a separate build: it is the test set, plus the `gap` term.

## How we'd test it (pass criteria fixed before looking)

- Baseline: persistence (last week's ownership and EO carried forward). Also report v0.
- Out of sample by GW: fit on all other GWs, forecast the held-out GW, for AE64 and E64 separately;
  2025-26 GW2-38 (EO scored on GW10-38, where listed EO exists), then train on 2025-26 and test on
  2026-27 as GWs arrive.
- Metrics: mean absolute error of next-GW EO; and **surge recall**: of moves of 20+ ownership points,
  the share that appear in our top-10 predicted risers or fallers that GW.
- Pass: at least 15% lower EO error than persistence over the season, no worse than persistence in
  quiet weeks, and surge recall of 50% or more, including the five weeks in the table above.
- Report separately for normal, double/blank and chip weeks (wildcard weeks may need idea 3).

## Out of scope

Changing Sertalp's solver; multi-GW EO beyond one step (B04b-2, after this); chip timing.
