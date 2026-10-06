# Rank-goal inputs: line spread, drift and κ (2026-10-06)

What `fplrank solve --target` uses to turn a plan into P(reaching the target line), and the evidence. Read-only
analysis on Alex's PC: `data/collected/` (end-of-season cut-offs 2006-07..2025-26 from managers' `past` totals,
ranks GW1-5 2026-27), Solio GW01_20260820 / GW02_20260822, FPL live GW1-5 snapshots, vaastav 2025-26.
Code: `rank.target.season_drift` (drift and spread), `opt.rank_goal.KAPPA`.

## 1. Line uncertainty: measure it against the group

The gap is relative to the EO group, so its uncertainty must be too. The old `sd_line` was the spread of the
line's absolute pace across seasons, which also counts the common part (a high-scoring season lifts the group
as well): double counting.

| sd over 33 GWs (after GW5) | top 10k | top 1k |
|---|---|---|
| Absolute line, season-to-season pace, last 3 seasons (old) | ±95 | ±99 |
| Same, 20 seasons | ±163 | ±154 |
| **Line relative to E64**: sd of (line - group mean) / 38 over 2018-26, x 33 | **±11** | ±11 |
| Line relative to AE64, same | ±42 | ±48 |

Weekly drift (GW2-5) has sd 5 (E64) / 10 (AE64) a GW, but season means vary far less than that implies
(differences of an interpolated line are negatively autocorrelated), so the weekly sd is not scaled by √GWs.

## 2. Drift: full seasons, a lower bound

Drift per GW = the line's gain minus the group's mean net points.

| | vs E64 | vs AE64 |
|---|---|---|
| **Top 10k, full seasons 2018-26: mean (range)** | **+1.2** (0.7..1.7) | +1.2 (-0.5..3.3) |
| Top 10k, 2025-26 | +1.1 | +0.4 |
| Top 10k, this season GW2-5 (old) | +4.2 | +2.5 |
| Top 1k, full seasons 2018-26 | +2.8 | +2.9 |

Over 33 GWs, +1.2 against +4.2 is about 100 points of gap, the biggest single input. GW2-5 is four noisy weeks
(sd of the mean about 2.6). The full-season figure is biased low: today's E64/AE64 members were chosen on past
results, so their past seasons score high. The size of that bias is unknown, so treat the drift as a lower
bound (P(target) reads optimistic).

## 3. κ: about 1 in the data, 0.75 by default

| test | κ | 95% interval |
|---|---|---|
| Managers' edge over AE64 EO, Solio, GW1-5 (top 1000 + top 10k sets, 8,988 manager-GWs) | **1.05** | 0.60..1.50 |
| Same, fresh projections only (GW1-2) | 1.30 | 0.69..1.92 |
| Same vs E64 | 1.04 | 0.59..1.49 |
| Players: points on fresh Solio xP, GW1-2 | 1.00 | 0.88..1.12 |
| Players: points on 1-3 GW old Solio xP, GW3-5 | 0.81 | 0.72..0.90 |
| 2025-26, AE64 minus E64 edge on FPL's xP, 38 GWs | 0.94 | 0.28..1.60 |

Intervals treat players as independent (managers share player outcomes), so they are too narrow. Real
managers' projected edges over the field come through at about 1:1; the old 0.3 is outside every Solio
interval. Not measured: the optimiser's winner's curse (our solver picks exactly where Solio disagrees most
with the field, so its edges should shrink more). 0.75 sits inside the intervals and allows for that;
`--kappa` overrides it. Pinning it down needs a replay of our solver over many GWs (RP1).

## Can't be estimated from our data

- The line's spread given where it is now: no past in-season line paths (FPL history gives past totals only).
- Drift without selection bias: needs the E64/AE64 lists as they stood each season.
- κ for the solver's own (optimised) plans: needs RP1.
- Only 5 GWs of this season, 2 with fresh Solio files, so the κ intervals are wide.
