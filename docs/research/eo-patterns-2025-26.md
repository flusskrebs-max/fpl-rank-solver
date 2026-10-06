# Elite EO patterns, week to week (2026-10-06)

Read-only exploration of how AE64 and E64 EO moves from one GW to the next, done for the cheap weekly blend
(`archive/eo-projector.md`, "Agreed approach"). No model is fitted here. Data: 2025-26 AE64/E64 from
`datasets/elite_ownership/`, and 2026-27 GW1-5 for all four groups from the collector. The two throwaway
scripts that produced the numbers were not kept; they only read those files and vaastav's 2025-26 fixtures.

How this has been used since: `eo-blend.md` found that re-picking each manager's XI and captain on next-GW xP
captures most of the week-one EO change described in section 1, so items 1, 4 and 6 of "What is stable enough"
are covered by fair persistence plus the re-pick. FH reversion (item 2) is built into fair persistence.
WC weight (3) and fallers continuing (5) are not used yet.

## Data used, and its limits

- 2025-26 AE64/E64: listed EO GW10-38 (unlisted treated as 0, so EO is slightly censored), rebuilt squad
  ownership GW1-38 (exact transfers, but squads after the GW4/6/32/35 wildcards are partly estimated),
  captain and chip tables GW1-38. Fixtures from vaastav.
- **There is no top 1k or top 10k data for 2025-26.** Those groups exist only for 2026-27 GW1-5 (collector),
  so section 6 is 4 transitions, early season, with a GW1 Bench Boost wave. Treat it as indicative.
- Doubles and blanks in 2025-26: DGW in GW26 (2 teams), GW33 (6), GW36 (2); BGW in GW31 (4), GW34 (6).
  Small, and GW33/34 overlap the BB and FH clusters.

## 1. Persistence and how EO drifts with horizon

| | AE64 | E64 |
|---|---|---|
| Players (>=5% owned) unmoved in a week, <1 pt / <3 pt (median GW) | 43% / 57% | 44% / 65% |
| Mean weekly ownership move | 6.6 pt | 5.4 pt |
| 20+ pt ownership moves per GW | 4.2 | 3.3 |
| Corr of a player's ownership change this week with next week | 0.08 | 0.11 |

Drift with horizon k (mean |x(t+k) − x(t)|, points):

| k | 1 | 2 | 3 | 4 | 6 | 8 |
|---|---|---|---|---|---|---|
| AE64 ownership | 6.6 | 11.8 | 15.8 | 19.0 | 23.0 | 24.8 |
| E64 ownership | 5.4 | 9.7 | 12.9 | 15.5 | 18.8 | 20.5 |
| AE64 listed EO | 20.8 | 22.6 | 24.6 | 25.4 | 27.7 | 29.7 |
| E64 listed EO | 15.9 | 17.9 | 19.8 | 20.9 | 22.4 | 23.7 |
| Top-15 EO overlap, AE64 / E64 | 67% / 68% | | | 57% / 55% | | 43% / 41% |

- **EO error is mostly week-one noise** (XI and captain re-picks): two thirds of the k = 8 EO gap is already
  there at k = 1. Ownership drift builds steadily and flattens after about six weeks.
- **The drift shape is the same in both groups.** As a share of the k = 8 drift: 0.27, 0.48, 0.64, 0.77,
  0.93 at k = 1, 2, 3, 4, 6 (AE64) and 0.26, 0.47, 0.63, 0.76, 0.92 (E64). No simple curve fits all of it (`1 − 0.73^k` matches k <= 3 but runs low after); use
  the table itself. **Usable as the starting shape for w(k)** before the overnight runs fit it.
- Week-to-week changes have no momentum on average (0.08-0.11), so the blend shouldn't extrapolate trends,
  with one exception (section 4).

## 2. Chip weeks

Mean weekly move by week type (week type = a chip used by 10%+ of the group):

| | AE64 own | AE64 EO | E64 own | E64 EO |
|---|---|---|---|---|
| normal (23 GWs) | 5.4 | 16.1 | 4.9 | 12.8 |
| WC | 16.4 | 37.1 | 9.7 | 28.3 |
| FH | 6.9 | 31.1 | 4.3 | 25.6 |
| BB | 4.5 | 26.7 | 5.1 | 18.8 |
| TC | 2.9 | 18.3 | 3.2 | 12.8 |

- **Wildcard turnover scales with the WC share**: weekly ownership move ≈ 5.1 + 27 × WC share (AE64,
  corr 0.80), 4.1 + 24 × WC share (E64, 0.71). The week after a WC week is still busier (8.1 vs 5.4 AE64,
  6.1 vs 4.9 E64). **Usable**: weight `EO_wc` in the blend by the expected WC share.
- **Free Hit weeks revert.** EO the week after a FH matches the week before far better than the FH week:
  GW34 (81% FH, AE64): |EO(t+1) − EO(t−1)| 11.9 vs |EO(t+1) − EO(t)| 34.4; E64 GW34 11.5 vs 26.6; GW13
  13.8 vs 26.3 (AE64), 8.4 vs 24.8 (E64). **Usable rule**: forecast the week after a FH from the week
  before it, not from the FH week; and only the FH share of the group should move to a FH template.
- **BB** adds about 90 EO points to the listed total (1243 vs 1155 AE64) and **TC** barely moves anything
  but the captain. Both are mechanical given the chip share; no pattern needed.
- Chip clusters repeat: WC GW6/GW32, FH GW13/GW34, BB GW33, TC GW17/GW26. In 2026-27 the first cluster
  came earlier (WC 39/64 AE64, 20/64 E64 in GW3).

## 3. Doubles and blanks (small sample: 3 DGW weeks, 2 BGW weeks)

Mean ownership change for players already >=5% owned, in GWs where some team has a double or blank:

| | AE64 | E64 |
|---|---|---|
| Two GWs before the double (bought early) | +17.6 (median +14.6) | +13.4 (+10.2) |
| In the double GW itself | +12.1 | +8.2 |
| The GW after a double (unwind) | −2.0 | −2.1 |
| In a blank GW | −3.4 | −3.6 |
| EO / ownership, double vs single vs blank | 1.35 / 0.83 / 0.01 | 1.48 / 0.81 / 0.04 |

- **Direction is clear and usable**: doubles are bought two weeks ahead and over the deadline, not sold
  after; doubled players carry about 1.4-1.5× their ownership as EO (captaincy), against about 0.8.
- **Magnitudes are not stable enough to use**: three DGWs, and the GW33 double / GW34 blank overlap the BB
  and FH cluster (blank-week owners Free Hit rather than sell). The naive-field solves see fixtures
  directly, so leave doubles to them.

## 4. How quickly players become template

- 35 (AE64) and 32 (E64) players went from <10% to >=50% ownership. **AE64 does it in one week 46% of the
  time, E64 25%**; E64 more often takes 2 weeks (28% vs 17%). 20-28% take 5+ weeks (slow creep: Timber,
  Thiago, Lacroix, Anderson, Wilson).
- **Fallers keep falling; risers don't keep rising.** After a 20+ point one-week fall, next week averages
  −4.9 (AE64) / −6.9 (E64), with a further 5+ point fall 35% / 45% of the time and a 5+ point recovery
  almost never (1% / 0%). After a 20+ point rise, AE64 is flat next week (+0.0; 17% up, 20% down) while E64
  keeps buying (+2.8; 30% up, 14% down). **Usable as a small add-on**: carry part of a big fall into next
  week; for E64 only, a little of a big rise.
- **The two groups move in the same week, not one after the other.** Correlation of weekly ownership
  changes: 0.82 same week, 0.10 / 0.09 with a one-week lag. Of 20+ point surges, the other group moved 10+
  the same way the same week 81-85% of the time, the week before only 15%. So **one group's move can't be
  used to forecast the other's**; it is the same information arriving at both.
- **Group gaps are persistent**: a player's AE64 − E64 ownership gap next week ≈ 0.89 × this week's
  (half-life about 6 GWs). Keep separate persistence per group; don't pool groups.

## 5. Captaincy

| | AE64 | E64 |
|---|---|---|
| Top captain share, median GW | 97% | 91% |
| GWs with top captain >=80% | 76% | 74% |
| Effective number of captains (median) | 1.07 | 1.19 |
| Same top captain as last GW | 38% | 57% |
| Same top captain in both groups | 89% of GWs | |

- Concentration is very stable; the splits (40-60%) come when two premiums are close: GW12 Saka/Haaland,
  GW23 Saka/Haaland, GW29-30 Haaland/Fernandes, GW37-38. The four GWs the groups disagree are all such
  splits (GW12, 14, 19, 23).
- **Captaincy changes most weeks**, so it must be forecast each week, not carried (this matches
  `archive/eo-flow-v1.md`, where the captain part was the only gain). **Usable**: "one captain takes ~90-97%" is a
  safe default; spread it only when the top two projections are close.
- 2026-27 GW1-5: top 1k and top 10k are much less concentrated (top captain 41-95%, e.g. 46% / 41% in GW4)
  than AE64 (75-98%).

## 6. How the groups differ

2025-26, AE64 vs E64 (half the sum of |EO_A − EO_E| over listed players, EO points per GW):
GW10-19 mean 253, GW20-29 268, GW30-38 201. Stable through the season, except **it halves after a shared
wildcard** (GW32 132, GW33 120) and reopens over the next few weeks (184, 190, 232). A player's EO gap
persists at 0.60 a week (corr 0.67, lower than ownership because of captaincy). Weekly EO changes of the
two groups correlate 0.89.

2026-27 GW1-5, four groups (same measure, mean over GW1-5):

| | E64 | top 1k | top 10k |
|---|---|---|---|
| AE64 | 362 | 506 | 501 |
| E64 | | 329 | 298 |
| top 1k | | | 97 |

- **Top 10k ≈ top 1k** (gap 97; top10k = 1.01 × top1000 fits with mean error 1.0 EO point). E64 is the
  elite group closest to them; AE64 is the outlier.
- All four move in the same week (weekly EO change vs top 10k: corr 0.85 AE64, 0.93 E64, 0.99 top 1k), and
  the broad groups move a bit less (EO moved per GW about 75-85% of E64's).
- Gaps to top 10k persist at 0.57-0.63 a week. Only four transitions, early season, after a GW1 BB wave:
  indicative only.

## What is stable enough for the cheap blend

1. **Persistence per group as the base**, with **w(k) shaped like the ownership drift: 0.27, 0.48, 0.64, 0.77, 0.93 of the k = 8 move at k = 1, 2, 3, 4, 6** to start (same in both
   groups). Fit the scale overnight as planned.
2. **FH reversion**: the week after a FH cluster comes from the week before it.
3. **WC weight from WC share**: turnover ≈ 5 + 25 × WC share, so mix in `EO_wc` in proportion to the
   expected WC share (and a little the week after).
4. **Captaincy re-forecast each week**, concentrated (~90-97% on one) unless the top two are close.
5. **Fallers continue**: carry 13-17% of a 20+ point fall into next week (falls average −39 / −40 points, then −4.9 / −6.9 more); for E64, a little of a
   big rise.
6. **Groups separate, never pooled or lagged** against each other; top 10k ≈ top 1k.

## What isn't

- Double/blank magnitudes (3 + 2 weeks, confounded with chip clusters). Direction only; leave to the solves.
- Rise momentum (differs between groups, small).
- Any group-to-group lead (none found).
- Elite vs top 1k/10k gaps beyond 2026-27 GW1-5; recheck at about GW10.
- 2025-26 GW1-9 EO (only calculated, not listed) wasn't used for EO numbers.
