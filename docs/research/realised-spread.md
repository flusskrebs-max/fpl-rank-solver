# Realised spread vs S2's predicted sd (V1)

Generated 2026-10-06 by `fplrank.eval.spread` from the collector (2026-27 GW1-5; AE64, E64 and the top
1000 exactly, the top 10k as a 1-in-10 sample). Pass criterion from the S2 brief, written first: S2's
sd within about 20% of the realised spread → keep s = 1; otherwise set s to the ratio.

**Method.** For each group and GW, each member's realised relative score Δ = Σ (m − EO) × pts − (hits −
group mean hits), using FPL's multipliers after automatic subs. S2's prediction for the same squads at
the deadline: mean_i = Σ (m − EO) × xP and var_i = Σ (m − EO)² × v(xP) (xP from the newest Solio file
made for that GW, v from the S2b table), so predicted var(Δ) = var(mean_i) + average var_i. Covariance
between players is ignored, as in S2.

## Result: s = 1 (within 20% for every group)

| group   |   gws |   sd_real |   sd_pred |    s |
|:--------|------:|----------:|----------:|-----:|
| AE64    |     5 |      8.74 |     10.61 | 0.82 |
| E64     |     5 |      9.78 |     11.34 | 0.86 |
| top1000 |     5 |     12.4  |     12.56 | 0.99 |
| top10k  |     5 |     12.06 |     12.37 | 0.97 |

The top 1000 and top 10k match almost exactly (ratio 0.97-0.99). The elite groups spread a little less
than predicted (0.82-0.86): they are more alike than our variance model assumes, probably because shared
picks of the same team move together (the ignored covariance cuts both ways). Per GW the ratio ranges
from 0.63 to 1.20, so five GWs pin s down only roughly; re-run as GWs come in.

## Per GW

| group   |   gw |    n |   sd_real |   sd_pred |   sd_mean |   ratio |
|:--------|-----:|-----:|----------:|----------:|----------:|--------:|
| AE64    |    1 |   64 |      8.72 |     11.7  |      6.72 |    0.75 |
| E64     |    1 |   64 |     10.87 |     12.88 |      6.59 |    0.84 |
| top1000 |    1 | 1000 |     14.28 |     14.69 |      7.97 |    0.97 |
| top10k  |    1 | 1000 |     13.66 |     14.37 |      8.13 |    0.95 |
| AE64    |    2 |   64 |      9.5  |     10.59 |      6.87 |    0.9  |
| E64     |    2 |   64 |      9.35 |     10.88 |      5.34 |    0.86 |
| top1000 |    2 | 1000 |     14.35 |     12.37 |      6    |    1.16 |
| top10k  |    2 | 1000 |     15    |     12.49 |      6.67 |    1.2  |
| AE64    |    3 |   64 |      7.01 |      9.97 |      2.82 |    0.7  |
| E64     |    3 |   64 |      7.87 |     11.54 |      4.71 |    0.68 |
| top1000 |    3 | 1000 |      9.56 |     12.18 |      4.62 |    0.78 |
| top10k  |    3 | 1000 |      9.31 |     11.95 |      4.53 |    0.78 |
| AE64    |    4 |   64 |     10.81 |      9.52 |      3.51 |    1.13 |
| E64     |    4 |   64 |     11.63 |     10.33 |      4.52 |    1.13 |
| top1000 |    4 | 1000 |     11.66 |     11.58 |      4.28 |    1.01 |
| top10k  |    4 | 1000 |     10.56 |     11.39 |      4.31 |    0.93 |
| AE64    |    5 |   64 |      7.01 |     11.1  |      1.79 |    0.63 |
| E64     |    5 |   64 |      8.72 |     10.87 |      2.74 |    0.8  |
| top1000 |    5 | 1000 |     11.5  |     11.75 |      3.1  |    0.98 |
| top10k  |    5 | 1000 |     10.83 |     11.42 |      3.07 |    0.95 |

`sd_mean` is the spread of the projected edge alone (no κ). Per-GW realised sd is 9-15 points, so over
33 GWs the season sd is about 55-85 points, which matches S2c's live output (about 72).

## Drift of the line against each group (points a GW, GW2-5)

|         |   top 1,000 |   top 10,000 |   top 100,000 |
|:--------|------------:|-------------:|--------------:|
| AE64    |         4.1 |          2.5 |           0.2 |
| E64     |         5.7 |          4.2 |           1.8 |
| top1000 |        -8.4 |        -10   |         -12.3 |
| top10k  |        -5.8 |         -7.3 |          -9.7 |

Positive means the rank line pulls away from the group's average manager. The top-1000 and top-10k
numbers are biased low: those sets are *today's* top managers, chosen for having scored well so far.
For S2 prefer the fixed lists (AE64, E64) or a sample re-drawn each week.
