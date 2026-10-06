# EO naive field (idea 3): result (2026-10-06)

Idea 3 from `eo-projector.md`: forecast a group's next-GW ownership and EO by running Sertalp's solver
at λ = 0 (pure EV) on every member's real squad, then compare it with Alex's cheaper blend (current EO,
an EV-driven drift and a few template wildcard solves). Code: `src/fplrank/model/naive_field.py`, tests
in `tests/test_naive_field.py` (synthetic data only). Pass criteria are the ones fixed in
`eo-projector.md` before idea 1 was run.

**Verdict, in short**

- The per-manager run cuts EO error by about a third against persistence (36% AE64, 28% E64) and
  catches about half of the 20+ point ownership moves (49%, 57%). On the pre-set checks it passes EO
  error and quiet weeks for both groups, and passes surge recall for E64 but just misses for AE64
  (26 of 53 caught). Four transitions, three with a stale projection file: suggestive, not settled.
- Most of that gain is in **who starts and who is captain**, not in **who is owned**. Ownership error
  is about level with persistence (AE64 7.7 vs 8.5 points, E64 5.4 vs 5.2). Persistence also carries
  last week's chip EO (bench boosts, triple captains) into a week where most managers have no chip.
- The cheap blend is about as good as persistence on EO (AE64 10.8-11.9 vs 12.1; E64 8.4-9.3 vs 8.7).
  It is only a little closer to the per-manager forecast than persistence is (EO 8-12 points apart, vs
  11-14 for persistence). Its biggest gap is that it keeps last week's XI and captaincy. Re-picking
  those, as the per-manager solves do, is the next step (see "Agreed approach" in `eo-projector.md`).

## Data

| What | Detail |
|---|---|
| Groups | AE64 (league 1291919) and E64 (league 38543): 64 managers each, 4 in both, so 124 distinct managers |
| Squads | `data/collected/picks.parquet`, GW1-5 of 2026-27, every member, every GW (from the collector) |
| Transfers, chips | `data/collected/transfers.parquet` (with purchase and sale prices), `chips.parquet` |
| Actual EO | `data/collected/eo.parquet`, the collector's deadline EO (XI 1, captain 2, triple captain 3, bench-boost bench 1) |
| Actual ownership | share of the group's squads holding the player, from `picks.parquet` |
| Projections | Solio, via `projections.latest(gw)`: the newest file made at or before each deadline |
| Prices, teams, fixtures | latest `bootstrap-static` and `fixtures` snapshots (2026-10-06), with prices rolled back (below) |

Transitions scored: GW1→2, 2→3, 3→4, 4→5 (GW6 picks aren't public until its deadline on 10 October).

Only two Solio files exist for these weeks: `GW02_20260822.csv` (made 22 August, six days before the
GW2 deadline, covers GW2-13) and `GW06_20261005.csv`. So:

- **GW2 is the only clean week**: the right file, made before its deadline.
- **GW3, GW4 and GW5 reuse the GW2 file**, 1-3 weeks stale. It knows nothing of injuries, form,
  price changes or news after 22 August, which is exactly what drives many real transfers. These weeks
  understate what the method could do with fresh files.

What happened in these weeks, which matters for reading the results:

| GW | AE64 wildcards | E64 wildcards | Other chips (both groups) | 20+ point moves (AE64 / E64) |
|---|---|---|---|---|
| 2 | 0 | 0 | 19 bench boosts | 0 / 0 |
| 3 | 39 (61%) | 20 (31%) | 31 free hits, 29 triple captains | 34 / 17 |
| 4 | 10 | 10 | 61 triple captains, 4 free hits | 16 / 8 |
| 5 | 6 | 7 | 9 free hits | 3 / 3 |

GW1 also had 93 bench boosts among the 124, so GW1's EO includes most benches.

## Method: per-manager ("naive field") run

### Squad state at a past deadline

For each manager and each target GW t+1 we rebuild what the FPL "my team" page would have shown
just before the t+1 deadline, using **his own `generate_team_json`** (vendor `dev/solver.py`) with its
API calls served from our collected tables instead of the live API (`team_state`):

- First-GW squad from `picks` (GW1), then every transfer made for a GW ≤ t from `transfers`, newest
  first as the API returns them. His code skips free-hit transfers, tracks purchase prices
  (`element_in_cost`) and computes the bank from £100.0m.
- Free transfers: his `calculate_fts` on the same transfer list and the chip history up to GW t (one
  added per GW, at most 5, unchanged across wildcard and free-hit weeks).
- Selling prices: his rule (purchase price plus half of any rise, rounded down) against the market
  price at the deadline.
- Market price at a past deadline (`market_prices`): the API only gives today's price, so we use the
  median price paid by collected managers (top 1000, top 10k sample, AE64, E64) for transfers into
  that player made for GW t+1; else the latest earlier such price; else the start price. Players
  nobody bought rarely move, so the fallback error is small. `bootstrap_at` writes these into a copy of
  the bootstrap and sets GW t+1 as the next event.
- His chip history is cleared in the team state; chips come from the variant (below).

### Solver runs

Every state goes through his `run/solve.py::solve_regular`, called the way his `run/simulations.py`
calls it (`_solve_one`): projections written to his data folder, `team_data = json_string`, API
payloads served from our snapshots, his result CSVs sent to a temp folder. His settings files are
used unchanged (decay 0.9, FT values, no transfers in the last 2 GWs of the horizon, hits allowed at 4
points, no chips unless forced, `gap` 0) except:

| Option | Value | Why |
|---|---|---|
| `horizon` | 5 (his default 8) | at horizon 8, HiGHS often found **no** feasible solution within 10 s, and a 20 s cap made the full run 2-3 hours; horizon 5 with 15 s solved every state |
| `secs` | 15 | time limit per solve; all 1,375 states returned a solution (0 failures) |
| `override_next_gw` | t+1 | plan from the target GW |
| printing, images | off | |

Four transfer settings ("variants"), each applied to every manager:

| Variant | Free transfers | Chip |
|---|---|---|
| `1ft` | forced to 1 | none |
| `2ft` | forced to 2 | none |
| `banked` | the manager's real count (his `calculate_fts`) | none |
| `wc` | (irrelevant) | wildcard forced in GW t+1 (`use_wc = [t+1]`) |

Plus, in the comparison, **`mix`**: the `wc` solve for managers who really wildcarded in GW t+1 and the
`banked` solve for everyone else. This uses known chip use in GW t+1 as an input (as v0 does with chip
rates); it isn't a pure forecast.

124 managers × 4 GWs × 4 variants = 1,984 solves; identical states (same squad, selling prices, bank,
free transfers and wildcard flag) are solved once, leaving 1,375. Six worker processes on Alex's PC
(12 cores), 3,020 s in all.

### From solves to group ownership and EO

From each solve we take the GW t+1 squad and his `multiplier` per player (XI 1, captain 2, bench 0).
For a group: **ownership** = share of members whose solved squad holds the player; **EO** = mean
multiplier (`group_table`). The solver never triple-captains or bench-boosts here, so its EO has no
chip part.

## Method: cheap blend (Alex's suggestion)

The question was whether something much cheaper can approximate the per-manager run: current EO,
moved by a function of future EV, plus a few "default" wildcard squads.

1. **Drift** (non-wildcarders). For players owned at t:
   `own'[i] = own[t, i] × exp(k × (EV_i − EV_ref))`, then rescaled within each position so the group
   still owns 2/5/5/3 per manager, capped at 1. `EV_i` = Solio points over GW t+1 to t+5 (the same
   file as the per-manager run); `EV_ref` = the ownership-weighted mean EV of that position in the
   group. EO scales with ownership: `eo'[i] = eo[t, i] × own'[i] / own[t, i]`. Unowned players can't
   enter through this step.
2. **Templates** (wildcarders). One wildcard squad per horizon in {3, 5, 8}, solved by his solver from
   an empty squad with the group's mean budget (bank plus selling value) at that deadline, 30 s cap.
   Averaged: template ownership = share of the 3 squads holding the player; template EO = mean
   multiplier. 3 solves per group per GW, 24 in all.
3. **Blend**: `forecast = (1 − w) × drift + w × templates`.

Three versions, with `k` from {0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.6} and `w` from
{0, 0.05, 0.1, 0.2, 0.3, 0.5}:

| Version | k | w | Fitted to |
|---|---|---|---|
| `cheap` | fitted | fitted | actual EO |
| `cheap_wcshare` | fitted | share of the group that wildcarded in t+1 (known chip use, like `mix`) | actual EO |
| `cheap_approx` | fitted | fitted | the per-manager `mix` EO (Alex: it only has to approximate the intensive run) |

**Out of sample:** each GW's `k` and `w` are chosen on the other three GWs only (leave-one-GW-out), so
every number below is out of sample. With four GWs the fitted values are noisy (`k` 0-0.4, `w` 0.1-0.5).

## Metrics

All in percentage points (EO ×100, ownership ×100), per group and transition (`score`, `eo_gap`):

- **EO error**: mean absolute difference between forecast and actual deadline EO over every player
  owned at t, owned at t+1, or in the forecast. Unlisted players count as 0. Persistence uses the same
  player set.
- **Ownership error**: the same for squad ownership.
- **Surge recall**: moves of 20+ ownership points from t to t+1 that appear among the 10 biggest
  predicted risers (for rises) or fallers (for falls).
- **Gap to the per-manager run**: mean absolute EO difference between a forecast and the `mix` (or
  `banked`) forecast, over players owned at t or in either.
- **Quiet weeks** (defined before eo-flow-v1 ran): wildcards plus free hits under 10% of the group and
  no 20-point move. Only GW2 qualifies.
- **Pass criteria** (eo-projector.md): ≥15% lower EO error than persistence over the scored weeks, no
  worse in quiet weeks, surge recall ≥50%. Alex has since said the blend doesn't need to pass these;
  it only has to approximate the per-manager run, so the blend is reported as numbers.

## Results

### Per-manager run, by variant (mean over GW2-5)

| | AE64 own | AE64 EO | E64 own | E64 EO |
|---|---|---|---|---|
| persistence | 8.5 | 11.8 | 5.1 | 8.6 |
| `1ft` | **7.6** | **7.7** | **5.1** | **6.2** |
| `2ft` | 8.0 | 8.0 | 5.6 | 6.5 |
| `banked` | 7.9 | 8.0 | 5.3 | 6.3 |
| `wc` (everyone wildcards) | 21.8 | 16.8 | 19.2 | 14.6 |
| `mix` (real wildcarders wildcard) | 7.7 | 7.5 | 5.4 | 6.2 |

(Persistence differs by a few hundredths between rows because the scored player set includes the
forecast's players.)

### By week: persistence vs per-manager `mix` vs cheap blends

EO error (points); ownership error in brackets.

| AE64 | GW2 (clean) | GW3 | GW4 | GW5 | mean |
|---|---|---|---|---|---|
| persistence | 6.4 (0.1) | 18.4 (20.3) | 13.2 (9.4) | 10.7 (5.2) | 12.1 (8.8) |
| per-manager `mix` | **3.8** (0.9) | **13.8** (17.4) | **5.7** (5.8) | **6.7** (6.6) | **7.5** (7.7) |
| `cheap` | 13.5 (16.2) | 15.7 (17.5) | 10.3 (8.7) | 8.1 (6.6) | 11.9 (12.3) |
| `cheap_wcshare` | 7.9 (5.0) | 14.8 (17.1) | 11.2 (8.9) | 9.2 (4.7) | 10.8 (8.9) |
| `cheap_approx` | 13.5 (16.6) | 14.8 (16.4) | 10.1 (11.8) | 9.3 (11.9) | 11.9 (14.2) |

| E64 | GW2 (clean) | GW3 | GW4 | GW5 | mean |
|---|---|---|---|---|---|
| persistence | 5.3 (0.2) | 12.3 (10.3) | 9.3 (6.1) | 8.0 (4.2) | 8.7 (5.2) |
| per-manager `mix` | **4.4** (1.4) | **9.6** (9.9) | **5.6** (5.3) | **5.1** (5.0) | **6.2** (5.4) |
| `cheap` | 8.8 (9.1) | 11.4 (9.8) | 8.4 (5.8) | 7.0 (4.6) | 8.9 (7.3) |
| `cheap_wcshare` | 7.4 (4.6) | 10.9 (10.0) | 8.2 (6.2) | 7.1 (4.1) | 8.4 (6.2) |
| `cheap_approx` | 11.3 (13.3) | 10.5 (9.6) | 7.8 (7.1) | 7.7 (9.0) | 9.3 (9.7) |

GW2, the clean week, is the quietest: the elite barely changed squads (ownership moved 0.1 / 0.2
points on average). The solver made transfers they didn't (ownership error 0.9 / 1.4), but its EO is
still better because GW1's bench-boost EO drops away and it re-picks the captain.

### Pass checks (GW2-5)

| | AE64 `mix` | AE64 `banked` | E64 `mix` | E64 `banked` |
|---|---|---|---|---|
| EO error vs persistence | −36% (pass) | −32% (pass) | −28% (pass) | −27% (pass) |
| Quiet week (GW2) | 3.8 vs 6.3 (pass) | 3.8 vs 6.3 (pass) | 4.4 vs 5.2 (pass) | 4.4 vs 5.2 (pass) |
| Surge recall | 49%, 26 of 53 (fail, just) | 42% (fail) | 57%, 16 of 28 (pass) | 43% (fail) |

The cheap blends catch 40% (AE64, 21 of 53) and 50-57% (E64) of surges. Their EO error runs from 1% worse to 9% better
than persistence for AE64, and from 9% worse to 2% better for E64.

### How closely the cheap blend approximates the per-manager run

Mean EO gap to the per-manager forecasts, GW2-5 (points):

| | AE64 gap to `mix` | AE64 gap to `banked` | E64 gap to `mix` | E64 gap to `banked` |
|---|---|---|---|---|
| persistence | 14.3 | 11.2 | 10.6 | 9.3 |
| `cheap` | 12.1 | 10.4 | 9.7 | 8.6 |
| `cheap_wcshare` | **9.8** | 11.4 | 8.5 | 8.4 |
| `cheap_approx` | 10.2 | **9.9** | **8.1** | **8.4** |
| `banked` (for scale) | 4.7 | 0 | 2.5 | 0 |

The blend closes only a fifth to a third of the gap between persistence and the per-manager run. Two
reasons are visible in the numbers:

- **XI and captain**: the blend scales last week's EO, so last week's captain choices, bench boosts
  and triple captains carry over. The per-manager run re-picks them. This is where most of the
  per-manager EO gain comes from (its ownership error is close to persistence).
- **Templates are a blunt instrument for non-wildcard weeks**: fitted `w` of 0.2-0.5 pulls in a full
  template squad even in GW2, when nobody wildcarded, which is why the fitted blends are worst in GW2
  (ownership error 9-17 points against 0.1 for persistence).

## Runtimes and scaling

| Run | Solves | Wall time (Alex's PC, 6 workers) |
|---|---|---|
| Per-manager, 4 GWs × 4 variants, H5, 15 s cap | 1,375 unique (1,984 jobs) | 50 min (about 13 s per solve per worker) |
| Per-manager, one deadline, 4 variants | ~350 | ~13 min |
| Cheap blend templates, 4 GWs × 2 groups × 3 horizons, 30 s cap | 24 | 6.4 min (one process) |
| Cheap blend, one deadline | 6 | ~1.5 min |
| Drift step and scoring | none | seconds |

Scaling the per-manager run to his default H8: in a quick test, 10 s at H8 found no feasible plan for
3 of 4 squads and 20 s was enough for all four, against 3-10 s at H4. Solve time grows steeply with
horizon, so a full H8 run needs a cap of 20-30 s: about 30-45 minutes per deadline for one variant set
of 124 squads on 6 workers, or 2-3 hours for a four-week backtest like this one. Clustering squads
(the agreed approach) cuts the count from ~124 to ~20 per deadline.

## Caveats

- **Four transitions, three on a stale file.** GW3-5 used projections from 22 August. GW3 was a
  wildcard week (61% of AE64), so it dominates the means. Treat all of this as a first look.
- **EO gain is mostly lineup and captaincy, not transfers.** A fairer baseline would hold ownership and
  re-pick XI and captain (eo-flow-v1's "captain only" baseline gained 1-5% over persistence on
  2025-26). We didn't build that here.
- **Chip weeks**: the solver never triple-captains or bench-boosts, so it can't match GW4's 61 triple
  captains; persistence carries last week's chips forward instead. Both are wrong in chip weeks.
- **`mix` and `cheap_wcshare` use real wildcard use in t+1**, which isn't known at the deadline.
  `banked` and `cheap` don't.
- **Prices before a deadline are estimated** from what collected managers paid; players few bought
  can be off by £0.1-0.2m. This only affects which transfers are affordable.
- **Horizon 5 and a 15 s cap**, not his H8 default, for runtime. The solver is meant as a sensible
  field, not an optimal one, so near-optimal plans are fine, but the shorter horizon sees less of each
  fixture run.
- **Fitting with four weeks**: `k` and `w` are out of sample but come from three weeks each.

## Reproduce

Needs the collected data on Alex's PC (`data/collected/`, `data/projections/`, snapshots):

    uv run python -m fplrank.model.naive_field backtest --workers 6     # per-manager run, ~50 min
    uv run python -m fplrank.model.naive_field compare                  # cheap blends + gaps, ~7 min
    uv run python -m fplrank.model.naive_field forecast --gw 6          # GW6 forecast, to score after 10 Oct

Outputs (git-ignored): `data/derived/naive_field/backtest_solves.parquet`, `backtest_table.csv`,
`compare_table.csv`, `forecast_GW{n}.csv`. Defaults: horizon 5, 15 s cap, all four variants.

## Next

The agreed approach (`eo-projector.md`) takes this forward: ~20 clustered representatives with short
H3 solves (which re-pick XI and captain) blended with persistence for next-GW EO, a few H8 wildcard
templates for the longer horizon, and the full per-manager run occasionally as the yardstick. The GW6
forecast with the fresh `GW06_20261005.csv` can be run now and scored after Saturday's deadline; it
would be the second clean week.
