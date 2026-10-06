# EO flow model v1 (idea 1): result (2026-10-06)

Idea 1 from `eo-projector.md`: refit v0 on the 2025-26 Elite 64 data with ΔEV and the price-band
gap, one fit per group (AE64, E64). Code: `src/fplrank/model/eo_flow.py`; rerun with
`uv run python -m fplrank.model.eo_flow` (needs the cached Core Insights and vaastav files).

**Verdict: fails for both groups.** It is barely better than persistence (AE64) or worse (E64) on
EO error, and it catches about 4 in 10 big moves, not the 5 in 10 required. The only part that
helps is the captain model, which is v0's and needs no flows.

## What was tested

    logit(own[t+1]) = a + b·logit(own[t]) + c·xp + d·pts + e·ΔEV + f·gap + g·wc + h·wc·xp

- `own`: squad ownership (rebuilt, GW1-38). `xp`: FPL `ep_next` for the next GW (Core Insights).
  `ΔEV` = change in `xp` since last week; `pts` = last GW's points; `wc` = share wildcarding.
- `gap`: best `xp` of another same-position player costing at most £0.5m more, minus his.
- Flows balance: forecasts are shifted per position so every manager still owns 2/5/5/3.
- EO = last week's EO minus its captain part, plus the forecast ownership change, plus v0's
  captain softmax on the forecast ownership.
- Leave-one-GW-out per group. Pass criteria as fixed in `eo-projector.md`. "Quiet weeks" (defined
  before running): wildcard + free hit under 10% of the group and no 20-point ownership move.
- Baselines: persistence; "captain only" (ownership held, captaincy forecast); v0's form
  (`a, b, c, d` only, refitted per group).

## Results (EO and ownership in percentage points)

| AE64 | persistence | captain only | v0 form | v0 + ΔEV + gap | gap split (post-hoc) |
|---|---|---|---|---|---|
| EO MAE, GW11-38 | 16.41 | **15.62** | 16.29 | 16.09 | 16.08 |
| ... chip weeks | 24.94 | 23.53 | 24.04 | 23.60 | 23.48 |
| ... normal weeks | 11.91 | **11.45** | 12.21 | 12.13 | 12.17 |
| ... quiet weeks | 10.86 | | 10.86 | 10.65 | 10.68 |
| Ownership MAE, GW2-38 | **3.68** | | 4.74 | 4.67 | 4.73 |
| Surge recall (153 moves of 20+) | | | 35% | 39% | 41% |

| E64 | persistence | captain only | v0 form | v0 + ΔEV + gap | gap split (post-hoc) |
|---|---|---|---|---|---|
| EO MAE, GW11-38 | 14.92 | **14.83** | 15.80 | 15.49 | 15.55 |
| ... chip weeks | 22.95 | 22.84 | 23.48 | 22.86 | 22.91 |
| ... normal weeks | 11.34 | **11.26** | 12.36 | 12.19 | 12.27 |
| ... quiet weeks | **5.26** | | 8.50 | 8.18 | 8.25 |
| Ownership MAE, GW2-38 | **2.68** | | 3.55 | 3.54 | 3.57 |
| Surge recall (122 moves of 20+) | | | 30% | 39% | 38% |

| Pass check (pre-registered model) | AE64 | E64 |
|---|---|---|
| EO error ≥15% below persistence | fail (2% below) | fail (4% above) |
| No worse in quiet weeks | pass (10.65 vs 10.86) | fail (8.18 vs 5.26) |
| Surge recall ≥50% | fail (39%) | fail (39%) |
| ≥50% in GW12/18/22/23/25 | fail (26%, 5 of 19) | fail (29%, 4 of 14) |

Missed in the test weeks include Gabriel −93 (GW12), Fernandes −98 / Cunha +84 (AE64 GW18),
Cunha −96 (GW22), Foden −59 and Fernandes +56 (GW23). Caught: Ekitiké (GW18), Saka −72 (GW25),
Fernandes −86 (E64 GW18), Rice +45 (E64 GW25).

## Why it fails, and what the fit says

- **The input can't see what drives the moves.** `ep_next` is FPL's form-based estimate for one
  GW. The big moves follow fixture runs, doubles and news (data-log, 2026-10-05), which it doesn't
  carry. Its ΔEV slope is negative (−0.12 AE64, −0.10 E64): a jump in form-based xP is mostly a
  past haul, which the elite don't chase.
- **The gap term is real but small.** Pooled, its slope is about zero. Split by who holds the
  player (added after the first run, so not part of the test), owners do sell when a better
  player is affordable (−0.17 per point of gap, AE64; −0.15 E64), but EO error barely changes.
- **Smooth forecasts lose on absolute error.** Two thirds of owned players don't move in a week.
  Persistence is exactly right for them; a probability model shaves a little off everyone.
- **Groups differ as expected.** AE64 responds more to xP and wildcards (xp +0.20, wildcard·xp
  +0.20 vs +0.18, +0.14) and its quiet weeks are noisier. E64 barely moves in quiet weeks (5.3
  points EO error for persistence), so any flow model there costs more than it gains.
- **The captain part is the only consistent gain**: 5% lower EO error than persistence for AE64,
  1% for E64, with no ownership flows at all.

## What this means

- Keep persistence for squad ownership and v0's captain part for EO. Don't use this flow model.
- The "x EV → y EO" answer from 2025-26 is "not much, with form-based EV": +0.2 logit per point of
  next-GW xP, and owners sell at about 0.17 logit per point of gap (AE64).
- Idea 3 (solver-predicted flows on 2026-27 with Solio projections) is the next test: it uses real
  multi-GW projections and fixtures, which is what this input lacked. Test it with the same criteria.
- Not tried, to keep this small: Solio projections for 2025-26 (we have none), multi-GW xP, a
  "most players don't move" mixture model.
