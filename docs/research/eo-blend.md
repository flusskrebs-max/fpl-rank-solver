# EO blend: one rough combined forecast (2026-10-06)

A group's next-GW EO forecast as a weighted average of five inputs, with non-negative weights summing to 1,
fitted per group (AE64, E64) leave-one-GW-out over GW2-5 of 2026-27. It also answers the critique of the naive
field run (`eo-naive-field.md`, PR #38) with the nine numbers it asked for. Code: `src/fplrank/model/eo_blend.py`,
tests in `tests/test_eo_blend.py` (synthetic data only).

**Verdict, in short**

- **Yes: input (b) alone matches the full per-manager solve, and slightly beats it.** Re-picking each manager's XI
  and captain on their current squad (no transfers, Solio xP for the next GW) gives EO error 7.3 (AE64) and 5.8
  (E64) points, against 7.9 and 6.1 for the per-manager `banked` solve and 11.6 / 8.5 for persistence. A manager
  bootstrap puts the solve 5-8% *worse* than the re-pick (90% intervals −10% to −5% AE64, −8% to −2% E64). The
  per-manager EO gain reported in #38 is the re-pick, not the transfers.
- **The fitted blend is the re-pick.** On non-chip manager-weeks the fit gives (b) all the weight for AE64 in every
  fold, and (b) 55-75% plus `banked` 0-35% for E64. The drift (k = 0 in every fold) and fair persistence get nothing
  of note. With wildcard templates added at the expected wildcard share, the full-group blend is *worse* than (b)
  alone (8.9 vs 7.3 AE64, 6.5 vs 5.8 E64): the templates only help in the big wildcard week (AE64 GW3).
- **What the solve adds is transfers**: it catches more 20+ point ownership moves (22 of 53 AE64, 12 of 28 E64,
  against 13 and 5 for the re-pick, which can't move ownership at all), but its ownership error is a little worse
  than holding squads (7.8 vs 7.3, 5.2 vs 4.8).
- **Fair persistence alone** (chips taken out, free hits reverted) cuts persistence's EO error by 14% (AE64) and 11%
  (E64), and explains 13 of AE64's 16 GW4 surges (GW3 free-hitters returning to their squads).
- **The sample is small.** Four transitions, three on a stale projection file, and very few manager-weeks without a
  chip in t or t+1 (21 AE64, 31 E64 over the four weeks; one manager per group in GW4). Treat the weights as a
  first look.

So the recommended rough forecast for next-GW EO is: **fair persistence, re-picked on next-GW xP**. It needs no
solver, runs in seconds, and is as good as the 50-minute per-manager run on these weeks. Transfers (ownership
moves) are the remaining gap, and the per-manager solve or something like it is still the only input that sees them.

## Data

As `eo-naive-field.md`: AE64 and E64 (64 managers each), picks, transfers and chips for GW1-5 of 2026-27 from the
collector, Solio file `GW02_20260822.csv` for every week (GW2 clean; GW3-5 one to three weeks stale), and the
per-manager solves saved by `naive_field backtest` (H5, 15 s cap, `banked` = each manager's real free transfers).

**Actual EO** here is rebuilt per manager from the deadline picks (`naive_field.deadline_rows`: XI 1, captain 2,
triple captain 3, bench-boost bench 1, autosubs undone), so it can be split by manager and resampled. It is the real
EO, chips included: Alex's point is that chip EO is real, but the blend shouldn't be fitted on it.

## Inputs

All five are known before the GW t+1 deadline. Group ownership = share of managers holding the player; group EO =
mean multiplier (`naive_field.group_table`).

| | Input | How |
|---|---|---|
| (a) | `fair`: fair persistence | GW t squads and lineups with chips stripped: XI 1, captain 2 (a triple captain counts 2), bench 0 (also under bench boost). A manager who free-hit in GW t is given their latest earlier non-free-hit squad and lineup, which is what they hold at the t+1 deadline. Same rule as `opt.ownership.chip_free_eo` (#39), kept per manager (`fair_rows`). |
| (b) | `repick`: XI and captain re-pick | (a)'s squads, no transfers. Each manager's XI is the best valid formation on Solio GW t+1 xP (1 GK, at least 3 DEF, 2 MID, 1 FWD: best keeper, best 3/2/1, then the best 4 other outfielders, which is optimal because every formation rule is a minimum); captain = highest-xP starter (`lineup`, `repick_rows`). |
| (c) | `drift`: EV drift | (a) moved by projected points over GW t+1..t+5: `own × exp(k × (EV − EV_ref))`, rescaled per position, EO scaled with ownership (`naive_field.cheap_forecast`, no templates). k from {0, 0.05, ..., 0.6}, fitted with the weights. |
| (d) | `banked`: per-manager solve | `naive_field` backtest's `banked` variant: his solver on every manager's real squad, bank and free transfers, no chips. No hindsight `mix`. |
| (e) | `templates`: wildcard average | Three wildcard squads solved from an empty team with the group's mean budget at horizons 3, 5 and 8 (`naive_field.compare`, now saved to `templates.parquet`), averaged. |

## Fitting

**What's fitted.** Weights for (a)-(d) and the drift's k, per group, by grid search: every weight vector on a 0.05
grid with non-negative entries summing to 1 (1,771 vectors), for each k. Objective: mean absolute EO error (points)
over the group's player set, averaged across the training weeks, weighted by the number of managers in each.

**On non-chip managers only** (Alex, 2026-10-06). For a target GW t+1, "chip" means any chip played in GW t or t+1:
week t's chip distorts the baseline, week t+1's the target. Each training week contributes its non-chip managers'
inputs and actual EO. These subsets are tiny:

| Non-chip managers (of 64) | GW2 | GW3 | GW4 | GW5 |
|---|---|---|---|---|
| AE64 | 4 | 3 | 1 | 13 |
| E64 | 8 | 4 | 1 | 18 |

For these managers (a) equals plain persistence, since they had no chip in GW t to strip.

**Wildcard templates (e)** describe wildcarders only, and wildcarders are never in the non-chip fit, so (e) is not
fitted. The full-group forecast is

    forecast = (1 − s) × Σ w_i × input_i  +  s × templates

with s the expected wildcard share: the group's mean wildcard share over the other three weeks (the same
leave-one-out). This keeps all weights non-negative and summing to 1. For reference, `blend_wcshare` uses the real
GW t+1 share instead (hindsight, as `mix` and `cheap_wcshare` do).

**Leave-one-GW-out.** Each week's weights, k and s come from the other three weeks only, so every number below is
out of sample. Also fitted: `blend_ab`, (a) and (b) only.

**Fitted weights** (non-chip fit; s = expected wildcard share):

| | GW2 | GW3 | GW4 | GW5 |
|---|---|---|---|---|
| AE64 | (b) 1.00; s 0.29 | (b) 1.00; s 0.08 | (b) 1.00; s 0.23 | (b) 1.00; s 0.26 |
| E64 | (b) 0.65, (d) 0.35; s 0.19 | (a) 0.05, (b) 0.55, (c) 0.05, (d) 0.35; s 0.09 | (b) 0.70, (d) 0.30; s 0.14 | (b) 0.75, (c) 0.25; s 0.16 |

k = 0 in every fold, which makes (c) identical to (a): the EV drift never helped, and the (a)/(c) split in E64 is
arbitrary. `blend_ab` puts 1.00 on (b) except E64 GW3 and GW5 (0.90 and 0.75).

## Scoring

**Fixed player set** (critique check 1): for each group, week and manager subset, every forecast is scored on the
same players: those owned or with EO in the actual EO, persistence or any input (including every drift k, the
templates and the cheap blend). Players: AE64 65 / 101 / 101 / 93, E64 82 / 112 / 116 / 115 (GW2-5, all managers).

Metrics, in points (×100):

- **EO error**: mean absolute difference from actual EO over the fixed set.
- **Summed EO error**: the same, summed rather than averaged (critique check 8).
- **xP-weighted EO error**: weighted by Solio GW t+1 xP (≥ 0), so errors on players who score count more (check 8).
- **Ownership error**: mean absolute ownership difference.
- **Gap to `banked`**: mean absolute EO difference from the per-manager solve.
- **Surge recall**: as before, 20+ point ownership moves caught among the 10 biggest predicted risers or fallers.

## Results

### All managers (real EO, chips included)

EO error by week, then the mean over GW2-5 (summed, xP-weighted and ownership error, gap to `banked`):

| AE64 | GW2 | GW3 | GW4 | GW5 | **mean** | summed | xP-wtd | own | gap to banked |
|---|---|---|---|---|---|---|---|---|---|
| persistence | 6.0 | 18.0 | 12.0 | 10.3 | 11.6 | 1,095 | 15.9 | 8.4 | 9.4 |
| (a) fair | 3.9 | 17.4 | 8.8 | 9.7 | 9.9 | 949 | 14.0 | 7.3 | 7.8 |
| (b) repick | **3.2** | 16.2 | **5.0** | **4.8** | **7.3** | **699** | **10.2** | 7.3 | 2.4 |
| (d) banked | 3.7 | 15.7 | 5.2 | 6.9 | 7.9 | 747 | 11.0 | 7.8 | 0 |
| (e) templates | 23.1 | 15.0 | 11.7 | 17.1 | 16.7 | 1,449 | 22.8 | 21.9 | 15.1 |
| blend | 8.2 | 15.5 | 6.1 | 6.0 | 8.9 | 816 | 12.4 | 10.0 | 3.9 |
| blend, real WC share | 8.2 | **14.3** | 6.8 | 6.7 | 9.0 | 822 | 12.2 | 10.2 | 6.2 |
| cheap (#38) | 13.5 | 15.7 | 9.7 | 8.1 | 11.7 | 1,048 | 16.3 | 12.1 | 9.1 |

| E64 | GW2 | GW3 | GW4 | GW5 | **mean** | summed | xP-wtd | own | gap to banked |
|---|---|---|---|---|---|---|---|---|---|
| persistence | 5.0 | 12.1 | 9.1 | 7.7 | 8.5 | 924 | 12.2 | 5.1 | 7.9 |
| (a) fair | 3.8 | 11.7 | 7.8 | 6.8 | 7.5 | 830 | 11.1 | 4.8 | 7.0 |
| (b) repick | **3.4** | 9.7 | 6.4 | **3.9** | **5.8** | **637** | **8.4** | 4.8 | 2.2 |
| (d) banked | 4.2 | 9.9 | **5.5** | 4.9 | 6.1 | 666 | 8.7 | 5.2 | 0 |
| (e) templates | 19.1 | 14.8 | 10.0 | 13.6 | 14.4 | 1,488 | 20.2 | 18.8 | 13.0 |
| blend | 5.7 | **9.5** | 6.1 | 4.5 | 6.5 | 692 | 9.2 | 6.1 | 2.6 |
| blend, real WC share | 5.7 | 10.0 | 6.4 | 5.0 | 6.8 | 727 | 9.6 | 6.7 | 3.5 |
| cheap (#38) | 8.8 | 11.4 | 8.2 | 6.9 | 8.8 | 938 | 12.9 | 7.3 | 7.5 |

(c) drift is identical to (a) at the chosen k = 0. `blend_ab` gives the same full-group means as `blend` (8.9,
6.5). The "cheap" row re-scores #38's cheap blend with its leave-one-out (k, w) on this player set.

The blend is worse than (b) alone because the templates come in at 8-29% in every week: they help only in GW3,
when 61% of AE64 wildcarded, and hurt in the other weeks. Even with the real share, they help only that week.

### Managers with no chip in t or t+1 (the fitting subset)

EO error, mean of GW2-5 (persistence = (a) here): AE64 persistence 13.8, (b) **7.7**, (d) 9.7, blend 7.7;
E64 persistence 13.5, (b) 15.5, (d) 16.3, blend 15.9. The E64 numbers are dominated by GW4, where one manager is
the whole subset (persistence 18.8, (b) 37.5, (d) 37.5). Without GW4: E64 (b) 8.2, (d) 9.2, persistence 11.8.

### Critique checks

**1. Players per row.** In #38's tables each forecast had its own player set (union of t, t+1 and that forecast),
so persistence was scored on 2-6 fewer players than the solves:

| | GW2 | GW3 | GW4 | GW5 |
|---|---|---|---|---|
| backtest AE64 (1ft / 2ft / banked / wc) | 62 / 62 / 62 / 66 | 100 / 100 / 100 / 101 | 98 / 100 / 100 / 95 | 91 / 91 / 91 / 94 |
| compare AE64 (persistence / mix / cheap) | 61 / 62 / 65 | 99 / 101 / 101 | 92 / 98 / 95 | 90 / 92 / 93 |
| backtest E64 (1ft / 2ft / banked / wc) | 78 / 79 / 78 / 82 | 111 / 111 / 111 / 112 | 115 / 115 / 115 / 114 | 112 / 112 / 111 / 116 |
| compare E64 (persistence / mix / cheap) | 77 / 78 / 82 | 110 / 112 / 112 | 113 / 115 / 114 | 111 / 114 / 114 |

Adding zero-error players lowers a mean, so this slightly favoured the forecasts with more players. Everything in
this report uses the fixed set above. On it the `banked` gain over persistence is 32% (AE64) and 27% (E64), close
to #38's 32% and 27%: the player sets didn't change the conclusion.

**2. Fair persistence (B1) vs persistence.** EO error 9.9 vs 11.6 (AE64), 7.5 vs 8.5 (E64), summed 949 vs 1,095 and
830 vs 924. Gain 14% and 11% (bootstrap 90%: 12-16%, 9-13%). Most of it is GW2 (GW1's bench boosts) and GW4 (GW3's
free hits).

**3. Chip split, chip in t or t+1.** Managers with a chip: AE64 60 / 61 / 63 / 51, E64 56 / 60 / 63 / 46. EO
error, mean of GW2-5:

| | AE64 chip | AE64 no chip | E64 chip | E64 no chip |
|---|---|---|---|---|
| persistence | 12.2 | 13.8 | 9.0 | 13.5 |
| (a) fair | 10.4 | 13.8 | 8.0 | 13.5 |
| (b) repick | **7.9** | **7.7** | **6.2** | **15.5** |
| (d) banked | 8.4 | 9.7 | 6.6 | 16.3 |

With chips in t or t+1, almost every manager is in the chip group, so its numbers are close to the all-manager
ones. The no-chip group is too small to read on its own (see the E64 GW4 note above).

**4. B2 (re-pick) vs persistence.** See (b) above: 7.3 vs 11.6 (AE64), 5.8 vs 8.5 (E64); bootstrap gain over (a)
26% (24-28%) and 23% (19-25%).

**5. Surges.** 20+ point ownership moves, t to t+1, and how many are still 20+ when measured from (a) (free hits
reverted):

| | GW2 | GW3 | GW4 | GW5 |
|---|---|---|---|---|
| AE64 rises / falls | 0 / 0 | 19 / 15 | 6 / 10 | 2 / 1 |
| AE64 still 20+ from (a) | 0 | 34 | **3** | 3 |
| AE64 free-hitters in GW t | 0 | 0 | 21 | 0 |
| E64 rises / falls | 0 / 0 | 10 / 7 | 4 / 4 | 2 / 1 |
| E64 still 20+ from (a) | 0 | 17 | **5** | 3 |
| E64 free-hitters in GW t | 0 | 0 | 12 | 4 |

**GW4: 13 of AE64's 16 surges and 3 of E64's 8 are GW3 free-hitters reverting**, which (a) already knows. That
matches last season's pattern (free hits revert the next week). Surge recall over GW2-5 (of 53 AE64, 28 E64): `banked`
22 / 12, blend 25 / 14, templates 21 / 14, cheap 21 / 16, (a) and (b) 13 / 5 (only the free-hit reversions;
neither can make a transfer).

**6. Captain concentration.** Top captain's share of managers, actual vs forecast:

| | GW2 | GW3 | GW4 | GW5 |
|---|---|---|---|---|
| AE64 actual | Fernandes 98% | Haaland 97% | Palmer 98% | Haaland 75% |
| AE64 (b) repick | Fernandes 98% | Isak 67% | Palmer 78% | Haaland 66% |
| AE64 (d) banked | Fernandes 98% | Isak 67% | Palmer 89% | Haaland 66% |
| E64 actual | Fernandes 89% | Haaland 100% | Palmer 95% | Haaland 91% |
| E64 (b) repick | Fernandes 95% | Haaland 50% | João Pedro 52% | Haaland 83% |
| E64 (d) banked | Fernandes 95% | Haaland 53% | Palmer 64% | Haaland 83% |

The elite herd harder than the solves: real top-captain shares are 75-100%, the solves' 50-98%. The solves get the
right top captain in 7 (`banked`) and 6 (re-pick) of 8 weeks; the misses are on the stale file (GW3 AE64: Isak;
GW4 E64 re-pick: João Pedro).
The top captain changed in 3 of 4 weeks in both groups (last season: 62% AE64, 43% E64 of weeks). Persistence
keeps last week's captain, so it was wrong in those 3 weeks. Captain herding is where a better (b) would gain most:
a captain softmax that concentrates more than "everyone picks their own highest xP" (v0's τ) is the obvious next step.

**7. MIP gaps.** See "Solve quality" below.

**8. Summed and xP-weighted EO error.** In the tables above. The order is the same on every measure: (b) best, then
(d), blend, (a), cheap, persistence, templates. xP weighting raises every error (errors concentrate on the
high-xP players the elite own and captain) without changing the ranking.

**9. Bootstrap over managers** (1,000 resamples of each group's 64 managers with replacement, the same managers in
every GW; gain = 1 − error(a) / error(b), errors averaged over GW2-5, all managers, real EO):

| Gain | AE64 | 90% | E64 | 90% |
|---|---|---|---|---|
| banked vs persistence | 32% | 29 to 34% | 27% | 24 to 30% |
| banked vs (a) fair | 21% | 18 to 23% | 18% | 14 to 21% |
| banked vs (b) repick | **−8%** | −10 to −5% | **−6%** | −8 to −2% |
| (b) repick vs (a) fair | 27% | 24 to 28% | 23% | 19 to 25% |
| (a) fair vs persistence | 14% | 12 to 16% | 11% | 9 to 13% |

The bootstrap covers manager sampling only, not week-to-week variation (four weeks, one projection file), which is
the larger uncertainty.

## Solve quality (critique check 7)

50 random `banked` states (manager × GW, seed 0: 9 / 15 / 12 / 14 from GW2-5), re-solved with the backtest's
settings (H5, 15 s cap, 6 workers on Alex's PC) with HiGHS's own report recorded after each solve (`gaps`):

| | |
|---|---|
| Proven optimal within 15 s | 19 of 50 |
| Stopped at the time limit | 31 of 50 |
| Relative MIP gap: median / 90th pct / max | 0.20% / 0.70% / 1.31% |
| Gap ≤ 1% | 49 of 50 |
| Objective minus bound (his objective, about 5 GWs of decayed points): mean / max | 0.7 / 3.3 points |
| Same GW t+1 squad and multipliers as the saved backtest solve | 50 of 50 |

So most solves are cut off by the time limit, but with a good incumbent: the plan is within about 1% of the best
possible on his objective, and re-solving gives the identical next-GW team every time. The GW t+1 squad (what the EO
uses) is settled long before the horizon's later weeks are. The 15 s cap is not what limits the solve's EO.

## Patterns from last season, and how they were used

| Pattern (2025-26) | Used? |
|---|---|
| Free hits revert the next week | Yes: built into (a); explains 13 of 16 AE64 GW4 surges. |
| Top captain changes in 62% (AE64) / 43% (E64) of weeks | As a check: 3 of 4 weeks here. (b) catches the change when the projection does. |
| Drift reaches 27/48/64/77/93% of the 8-GW move at k = 1/2/3/4/6 | Not used: that is a multi-GW lag; for one GW ahead the fit chose no drift. Relevant for the longer-horizon EO. |
| Turnover ≈ 5 + 25 × WC share | Not used directly; the expected WC share sets the template weight. |
| 20+ fallers keep falling by 13-17% | Not used: too few surges here to fit a follow-on term. |

## Caveats

- Four transitions; GW3-5 used the 22 August projection file. GW3 (61% AE64 wildcards) and GW4 (61% / 41% triple
  captains) dominate the all-manager means.
- The non-chip fit has 21 (AE64) and 31 (E64) manager-weeks. Small, but it points the same way as every other cut:
  (b) does the work.
- The expected wildcard share is a crude leave-one-out mean (8-29%), so the template term is close to a constant.
  A better share forecast (chips remaining, international breaks) would help only in wildcard weeks.
- Triple captains, bench boosts and free hits in GW t+1 are in the actual EO and in no forecast.
- (b) can't move ownership. In a week with many transfers (not wildcards) the solve should help more than here.

## Fixes to #38 in this PR

- `cheap_wcshare` leave-one-GW-out: its w is each week's wildcard share, so grouping by (k, w) across weeks matched
  nothing and took k from a single other week. It now fits k only (`naive_field.pick_lowo`). Mean EO error moves
  from 10.8 to 10.7 (AE64) and stays 8.4 (E64); `eo-naive-field.md` updated.
- Hits: his `weekly_hit_limit` is 0, so the solves take no hits (the 4-point `hit_cost` never applies). Wording fixed.
- `compare` saves its templates to `data/derived/naive_field/templates.parquet` (re-solved for this PR; the
  time-capped solves differ slightly from #38's, moving the cheap blend's numbers by up to 0.1).

## Reproduce

Needs `data/` on Alex's PC and the naive-field outputs:

    uv run python -m fplrank.model.naive_field compare     # templates + cheap blend (~7 min)
    uv run python -m fplrank.model.eo_blend backtest       # inputs, blend, checks 1-6, 8, 9 (~1 min)
    uv run python -m fplrank.model.eo_blend gaps           # check 7: 50 re-solves (~10 min)

Outputs (git-ignored) in `data/derived/eo_blend/`: `blend_table.csv` (every group × GW × manager subset ×
forecast), `weights.csv`, `surges.csv`, `captains.csv`, `bootstrap.csv`, `n_players.csv`, `mip_gaps.csv`.

## Next

- Use (a) + (b) as the next-GW EO for `--eo` (seconds, no solver), with real chip EO left out of the fit.
- Improve (b)'s captaincy: the elite concentrate more than independent highest-xP picks (check 6).
- Keep the per-manager solve (or the clustered version) for ownership moves; score GW6 with the fresh file after
  Saturday's deadline, the second clean week.
