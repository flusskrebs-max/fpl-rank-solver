# Ownership dynamics v0 (B04)

> Archived 2026-10-06. B04's v0 model was never wired into `fplrank solve` and is superseded by the re-pick (`../eo-blend.md`: EO error 7.3 / 5.8 against persistence 11.6 / 8.5, where v0 gained about 20%). `model/ownership.py` and the notebook were removed in the spring clean (git history).

How elite effective ownership (EO) moves from one gameweek to the next, and a first forecast of
next-GW EO with an error bar. Code: `src/fplrank/model/ownership.py`. Analysis:
`notebooks/b04_ownership_dynamics.py` (needs local data). Data: 2026-27 GW1-5 for the overall top
1000 (B03, complete picks) and the Elite 64 groups AE64 / E64 (B01, listed players only).
Projections: Solio files from B02.

## Set-up

EO is split into parts that move for different reasons:

    EO = XI share + Bench Boost bench + captain share x (1 + Triple Captain share)

- **XI share** (share of the group starting the player) moves with transfers. A 4-parameter logistic
  transition, fitted on the top 1000, where every manager's XI is known.
- **Captain share** is a softmax over the projected points of the players the group starts, with one
  temperature per group.
- **Chips** (Triple Captain, Bench Boost) are an input, not a forecast. With no blanks or doubles in
  GW1-8, chip timing can't be modelled yet (Q3).

For AE64 / E64 the XI share is approximated as EO minus the captain part (the graphics give captain
counts, Triple Captain separately). On Bench Boost-heavy GWs (1-2) that wrongly includes benches.

## Q1: XI share from one GW to the next

Fitted on all top-1000 transitions (GW1→2 ... 4→5, 2,352 player-GWs):

    logit(XI[t+1]) = -2.59 + 0.69 logit(XI[t]) + 0.51 xpts[t+1] - 0.006 pts[t]

- **Projections drive it.** Each projected point for next GW multiplies the odds of being started by
  about 1.7. A player at 30% with 2 projected points falls to about 10%; at 6 points he rises to
  about 47%.
- **Last GW's points add nothing** once projections are known (coefficient ≈ 0 in every fold).
  Elite managers don't chase last week's haul beyond what the projections already reflect.
- **Strong pull towards projections** (0.69 < 1 on last week's share). That's right in busy weeks
  and wrong in quiet ones (see backtest, GW2).
- The coefficients are stable across leave-one-GW-out folds (a −2.2 to −2.9, b 0.63-0.77,
  c 0.46-0.57).
- Not tested yet: price changes (no per-GW prices stored; the collector's weekly bootstrap snapshots
  will build that history), fixture swing (already inside the projections), banked free transfers
  (only group-level counts; four transitions are too few).

Caveat: GW3-5 use the GW2 projection file (made 1-3 weeks earlier), the latest we have for those
GWs. Fresh files each week should sharpen this.

## Q2: captaincy

Temperature τ in `captain share ∝ XI share x exp(xpts / τ)`, fitted on GW1-5:

| group | τ | captaincy odds per extra projected point |
|---|---|---|
| top1000 | 0.62 | x5 |
| AE64 | 0.37 | x15 |
| E64 | 0.38 | x14 |

Both Elite 64 groups follow the projections for the armband much more tightly than the top 1000.
AE64 and E64 are almost the same, so the analytics/template split shows up in squads, not
captaincy. (Elite 64 rests on listed players and approximate XI shares; treat as indicative.)

## Q3: chip weeks

Top-1000 managers, XI places changed from the previous GW, by chip:

| chip this GW | XI places changed | manager-GWs |
|---|---|---|
| none | 1.9 | 1,978 |
| Bench Boost | 1.1 | 220 |
| Triple Captain | 2.6 | 699 |
| Wildcard | 7.3 | 295 |
| Free Hit | 8.5 | 469 |
| GW after a Free Hit | 8.0 | 339 |

A Free Hit moves EO twice: once into the Free Hit squad and once back. GW3 was the big chip week
(top 1000: 480 Triple Captains, 264 Free Hits, 144 Wildcards), which is why "next week = this week"
fails worst there. Predicting chip timing from chips remaining and the fixture calendar needs blank
and double GWs (none so far) and more weeks. For now chip use is an input to the forecast.

## Q4: does AE64 lead E64?

No evidence. On the 93 player-GWs listed in both groups, next week's E64 change doesn't follow this
week's AE64-E64 gap (slope −0.03, correlation −0.02). If anything AE64 drifts towards E64
(slope 0.31, correlation 0.16), but with four transitions that is noise-level. Re-test with more GWs
and our own Elite 64 collection (B03 `named_lists`) once the team ids are known.

## Forecast and backtest

`forecast_eo(group, gw_next, state, model)` returns `fpl_id, xi, cap, eo_mean, eo_low, eo_high`.
`state_for(group, gw_next)` builds the state from repo data, and `fit_default()` fits the model on
everything available. The band is the 10%-90% range of leave-one-GW-out errors, by forecast-EO bucket
and group.

Backtest: for each GW, fit on the other GWs, forecast from the previous GW, and compare with
"next week = this week". Scored on every player with EO in either GW (top 1000) or on the players
listed that GW (Elite 64). No chip information is given to the model. Mean absolute EO error:

| group | GW2 | GW3 | GW4 | GW5 | mean | persistence mean |
|---|---|---|---|---|---|---|
| top1000 | 0.018 (0.013) | 0.023 (0.035) | 0.023 (0.028) | 0.017 (0.026) | 0.020 | 0.026 |
| E64 | 0.121 (0.073) | 0.205 (0.293) | 0.187 (0.246) | 0.119 (0.194) | 0.158 | 0.201 |
| AE64 | 0.133 (0.069) | 0.294 (0.389) | 0.212 (0.291) | 0.144 (0.216) | 0.196 | 0.241 |

(persistence in brackets; EO 0.1 = 10 percentage points)

- The model beats persistence in every group for GW3-5, by 18-39%, and over GW2-5 by about 20%.
- It loses in GW2: almost nobody transferred after GW1 (0.75 XI changes per top-1000 manager), and
  the model's pull towards projections over-predicts change. A next step is to make the persistence
  weight depend on how many free transfers the group has banked.
- Telling the model next GW's chip use barely helps (top-1000 mean 0.019 vs 0.020); the gain comes
  from the transfer model, not from knowing chips.
- Elite 64 errors are larger because only the ~36 high-EO listed players are scored, and the model
  is fitted on the top 1000, not on those groups.
- Band coverage is 76-80% on these same GWs, as designed (in-sample, so optimistic for new GWs).

## Next steps

1. Fresh projection files every week (register them with B02), so xpts[t+1] is never stale.
2. Free transfers banked as a persistence modifier (fixes GW2-style quiet weeks).
3. Chip timing once blanks and doubles appear; until then pass expected chip rates in `state`.
4. Our own Elite 64 picks (B03 `named_lists`) to replace the approximate XI shares for AE64 / E64.
5. Re-run the backtest monthly as GWs accumulate; four transitions is very little.
