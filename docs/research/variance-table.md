# Points variance by position and projection band (S2b)

Generated 2026-10-06 by `fplrank.model.variance.build()` from 84,308 player-GWs: vaastav 2023-24 and
2024-25 (`xP`), and 2025-26 with FPL-Core-Insights `ep_next` as xP (GW2-38). Bands are within-season
quantiles of xP among players with xP ≥ 0.1 (band 0 = below 0.1), so another source (Solio) is banded
within itself before lookup.

## Variance of actual points, v(band)

|   band |    G |    D |    M |    F |
|-------:|-----:|-----:|-----:|-----:|
|      0 |  0.4 |  0.7 |  0.8 |  0.6 |
|      1 |  0.6 |  0.5 |  0.5 |  0.6 |
|      2 |  0.1 |  0.4 |  0.4 |  0.4 |
|      3 |  1.2 |  1.6 |  0.9 |  0.9 |
|      4 |  1.7 |  1.7 |  1.2 |  1.1 |
|      5 |  2.1 |  2.8 |  1.7 |  2.1 |
|      6 |  2.6 |  5.2 |  2.7 |  4.7 |
|      7 |  4.6 |  7.2 |  4.3 |  6.2 |
|      8 |  7.5 |  8.3 |  6.7 |  8   |
|      9 |  8.7 | 10.5 | 11   | 12.2 |
|     10 | 12   | 19.1 | 22.2 | 23.1 |

## Mean xP in each band

|   band |     G |     D |     M |     F |
|-------:|------:|------:|------:|------:|
|      0 | -0.14 | -0.1  | -0.07 | -0.07 |
|      1 |  0.34 |  0.28 |  0.28 |  0.28 |
|      2 |  0.5  |  0.5  |  0.5  |  0.5  |
|      3 |  0.78 |  0.77 |  0.77 |  0.77 |
|      4 |  1.05 |  1.09 |  1.09 |  1.09 |
|      5 |  1.5  |  1.49 |  1.5  |  1.5  |
|      6 |  1.98 |  1.97 |  1.96 |  1.97 |
|      7 |  2.53 |  2.54 |  2.52 |  2.56 |
|      8 |  3.24 |  3.25 |  3.26 |  3.24 |
|      9 |  4.25 |  4.28 |  4.28 |  4.29 |
|     10 |  6.62 |  6.97 |  7.23 |  7.49 |

## Stability: midfielders by season

|   band |   2023-24 |   2024-25 |   2025-26 |
|-------:|----------:|----------:|----------:|
|      0 |       0.4 |       1.4 |       0.6 |
|      1 |       0.5 |       0.4 |       0.5 |
|      2 |       0.5 |       0.5 |       0.4 |
|      3 |       0.7 |       0.8 |       1.1 |
|      4 |       1.1 |       0.9 |       1.7 |
|      5 |       1.4 |       1.6 |       2.2 |
|      6 |       2.4 |       2.2 |       3.3 |
|      7 |       3.9 |       3.6 |       5.2 |
|      8 |       7.2 |       6.1 |       6.7 |
|      9 |      10.3 |      10.2 |      12.4 |
|     10 |      23.8 |      24.2 |      18.2 |

Variance grows roughly like the mean in the low bands and faster at the top (top-band midfielders:
mean about 6.4 points, variance about 22, sd about 4.7). 2025-26's top band is lower (18 vs 24), which may be
defensive contribution points spreading returns, or `ep_next` vs `xP`. Covariance between players is
ignored here (S2 says so); V1 checks the resulting σ against realised spread.
