# Data sources for fpl-rank-solver

Written 2026-10-06 from web research plus a read of the repo (`main`, after PR #12). Scope: data that
helps S1 (ownership-weighted solver), S2 (λ from the rank goal) and B04b (elite EO forecast). Favours
things that ship quickly. "Checked" means I downloaded and looked at the data; anything else is from
the provider's own pages.

## What we already have

| Need | Source in the repo |
|---|---|
| Elite EO now (exact) | Collector `fplrank.collect.elite_picks`: top 1000, AE64, E64 picks, chips, transfers, ranks (Tue/Fri on Alex's PC) |
| Elite EO history | Elite 64 2025-26 (GW1-38 transcribed) and 2026-27 GW1-5 |
| T_X now | Collector `thresholds` table (ranks 100/1k/10k) |
| Past cut-offs | `past` field of today's top 1000 (`rank-cutoffs.md`); top 100 not covered |
| Projections | Solio CSVs (paid, never committed) |
| History / calibration | vaastav 2023-24, 2024-25, 2025-26 via `fplrank.data.historical` |

## Findings that change current plans

1. **vaastav has stopped weekly updates** (notice on the repo since the end of 2024-25: updates only at
   season start, after January and at season end). Its 2025-26 `merged_gw.csv` is complete for results,
   but `xP` is filled for only 11 GWs (1-6, 8, 9, 24, 29, 38; checked), which is why B04b plans a proxy.
   For 2026-27 in-season data, don't rely on vaastav.
2. **FPL-Core-Insights fills that gap** ([github.com/olbauday/FPL-Core-Insights](https://github.com/olbauday/FPL-Core-Insights)).
   Free CSVs, refreshed twice a day, FPL ids, seasons up to 2026-27. `data/2025-2026/playerstats.csv`
   (9.7 MB, 29,978 rows) is a per-GW snapshot of the FPL `elements` record for every player, GW1-38,
   with `ep_next`, `ep_this`, `selected_by_percent`, `transfers_in_event`, `transfers_out_event`,
   `now_cost`, `cost_change_event`, status/news, set-piece order and defensive contribution (checked).
   Its `ep_next` at gw = N tracks vaastav `xP` for GW N closely (correlation 0.92-0.97, mean absolute
   difference 0.2-0.45 points over the 10 GWs where both exist; checked; D1 re-checks the offset). The exact snapshot time isn't
   documented, so treat it as "FPL's own xP, roughly at the deadline" and say so in reports.
   2026-27 GW1-5 is there too. No licence file; the author asks for a link back.
   - **B04b**: use this `ep_next` as the projection for every 2025-26 GW instead of building a
     points-per-90 proxy (step 2 of the brief). Saves work and is closer to what managers saw.
   - **B04b**: `selected_by_percent` and `transfers_in/out_event` per GW give overall ownership and
     transfer flow for the same weeks as the Elite 64 data, a candidate covariate for elite moves.
   - **S2**: 2025-26 was the first season with defensive contribution points, so a `v(xP)` variance
     table built only from 2023-24/2024-25 misses that scoring. Add 2025-26 (vaastav results + this
     `ep_next` as xP) to the table.
3. **FBref lost its Opta advanced stats** (xG, progressive passes etc.) on 2026-01-20 after a dispute
   with Stats Perform. Don't plan anything on FBref xG; Understat and the FPL API's own
   `expected_goals`/`expected_assists` remain.
4. **The FPL site has an official price change predictor this season** (Price Changes tab, updated every
   15 minutes, players can move up to £0.3m in a GW). No public API is documented, but it reads official
   data, so our own daily `bootstrap-static` snapshots carry the same inputs.

## Sources by need

### Elite / rank-tier EO (S1 now, B04b later)

| Source | Gives | Access | Verdict |
|---|---|---|---|
| **Our collector, extended** | Exact EO for any manager set | FPL API, already running | **P1, v0.1 (C1)**, since this season's top-10k history can't be backfilled later. Add a sampled top-10k set (e.g. 1 in 10 of ranks 1-10,000 from standings pages, ~1,000 managers) and, if wanted, top 100k (1 in 100). A 1,000-manager sample gives EO to about ±1.5 points at 50%. Cost: one more collector run of the same size as top 1000; config change plus a sampling option in `members()` |
| [LiveFPL rank tiers](https://plan.livefpl.net//rank_tiers) / [Top 10k](https://plan.livefpl.net//top10k) | Live EO for overall, top 100, 1k, 10k, 100k and wider brackets; top-10k captaincy and chip use | Free web pages, no API or published method; current GW only | **P2, manual check only.** Use to sanity-check our sampled top-10k EO for a GW or two. Don't scrape it into the pipeline |
| [FPL Review Elite 1000](https://docs.fplreview.com/team-analysis/elite-1000/) | Ownership, EO, captaincy and chips for a fixed list of 1,000 long-run elite managers | Web; CSV export is a premium (Patreon) feature | **P3.** Overlaps what the collector does; only worth it if we want their fixed "all-time elite" list, which LiveFPL also shows ([All-Time Best](https://plan.livefpl.net/league_stats/elite)) |
| Historical top-10k EO (past seasons) | n/a | The FPL API only returns picks for the current season, and I found no public archive | **Not available.** 2025-26 elite history stays limited to the Elite 64 graphics; from now on the collector builds our own archive, so keep it running every GW |
| **Collector picks + per-GW points** | Realised relative score Δ = Σ (m − EO) × pts per manager per GW | Have | **P1, S2 calibration (V1)**: checks S2's σ against what real top-1000 and Elite 64 squads did |

Collector EO for GW N exists only after the GW N deadline, so EO *at* the deadline is a forecast: S1c
uses B04's one-step forecast for the GW being decided.

### Rank cut-offs (S2)

| Source | Gives | Verdict |
|---|---|---|
| Collector `thresholds` | T_X every GW this season | Have (rank 100,000 added by C0). S2 uses the line's **drift against the EO group** this season (line GW gain − group mean GW points), not past cut-offs, for the gap; past per-GW cut-off curves aren't available anywhere |
| `past` field of entry history | Final points of today's managers in past seasons | Have. Only gives the indicative absolute line at GW38 for the report (`rank.target.target_line`). Top 100 coverage is thin (parked B03b leftover) |
| LiveFPL rank tiers | Live average points per tier | Manual cross-check only |

### Projections (S1)

| Source | Gives | Access | Verdict |
|---|---|---|---|
| Solio | Multi-GW xP, our main input; EO possibly (Alex has access; none of the registered exports has it yet) | Paid, local only | Keep. EO from Solio would be an S1 source (S1d, ADR 0004) |
| **FPL `ep_next`** | One-GW xP for every player | Free, in `bootstrap-static` (and Core Insights history) | **P1 as a fallback / test input**: lets S1's CLI and tests run when no Solio file is present, and in cloud sessions via Core Insights |
| [FPL Review](https://docs.fplreview.com/getting-started/premium-features/) | Multi-GW xP, "Massive Data" model, 14-GW horizon | Free planner; CSV export is premium | **P3**: a second opinion if we want to test sensitivity of λ to the projection source. Same export shape as Solio is likely, since open-fpl-solver reads both |
| Fantasy Football Hub, Fantasy Football Fix, FPL Copilot | Projections | Paid (Hub, Fix); Copilot free table, no documented export | Skip for now |

`ep_next`, vaastav `xP` and Solio are not on one scale, so anything keyed on xP across sources (S2b's
variance table) bands by within-source quantile, not raw xP.

### Team strength and fixtures (B04b multi-GW, projection sanity)

| Source | Gives | Access | Verdict |
|---|---|---|---|
| FPL `fixtures` endpoint | Fixtures, FDR, blanks/doubles | Have (`fpl_api.fixtures`) | Enough for blank/double flags in B04b |
| [ClubElo](http://api.clubelo.com/Fixtures) | Elo ratings and win/draw/loss probabilities for upcoming fixtures, free CSV API | Free; couldn't reach it from the cloud container, check on the PC | **P2**: a cheap fixture-strength feature for the EO forecast (elite pile-ins follow fixtures). Core Insights already carries team Elo per match |
| [football-data.co.uk](https://www.football-data.co.uk/) | Historical results with bookmaker 1X2 and over/under odds, free CSV per season | Free | **P3**: clean-sheet and goal expectations for past seasons if the simulator work resumes |
| [The Odds API](https://the-odds-api.com/sports-odds-data/epl-odds.html) | Live EPL 1X2, totals, BTTS; history from mid-2020 | Free key with a small quota; paid above | **P3**. No player goalscorer markets for EPL listed, so it doesn't help player projections |

### Transfers and prices

| Source | Gives | Verdict |
|---|---|---|
| FPL `bootstrap-static` | `transfers_in_event`, `transfers_out_event`, `selected_by_percent`, `cost_change_event`, `chip_plays`, `most_captained` per event | **Have**: the collector already saves a `bootstrap-static` snapshot each run, so overall transfer flow and prices are archived twice a week. Worth turning into a small per-GW table when B04b needs it |
| Core Insights per-GW `playerstats` | The same fields for every past GW of 2025-26 and this season | P1 for B04b history |
| Official price predictor, LiveFPL, OneFPL, fplstatistics | Price-change predictions | Skip. Price changes barely affect λ or EO; revisit only if the solver starts trading on team value |

### FPL API endpoints worth knowing

All under `https://fantasy.premierleague.com/api/`; unofficial and undocumented, so keep the collector's
rate limit (2 requests a second) and cache snapshots. It can't be reached from the cloud containers
(blocked by the proxy), so it runs on Alex's PC.

- `bootstrap-static/`: players, teams, events (incl. `chip_plays`, `most_captained`, `highest_score`, `average_entry_score`)
- `fixtures/` (optionally `?event=N`), `event/{gw}/live/`, `event-status/`
- `element-summary/{id}/`: a player's per-GW history this season (incl. `selected`, `transfers_in`) and upcoming fixtures
- `entry/{id}/`, `entry/{id}/history/` (incl. `past` and `chips`), `entry/{id}/event/{gw}/picks/`, `entry/{id}/transfers/`
- `leagues-classic/{id}/standings/?page_standings=N` (overall league 314; 50 per page)
- `dream-team/{gw}/`, `team/set-piece-notes/`

## Suggested order (small, shippable pieces)

1. **B04b input swap** (before or as part of B04b): add a loader for Core Insights `playerstats.csv`
   (2025-26, 2026-27) to `fplrank.data.historical`; use its `ep_next` as the 2025-26 projection. Cache under
   `data/` (not committed), like vaastav.
2. **Collector: sampled top 10k (and 100k) EO set, plus rank 100,000 in `threshold_ranks`**. Gives S1 a
   "top 10k" EO option (`--eo top10k`) and S2 a wider T_X curve. Config plus a small sampling option.
3. **S1 fallback projections from FPL `ep_next`** so the CLI and tests run without a Solio file.
4. **S2 variance table including 2025-26** (defensive contribution season).
5. Later, if the EO forecast needs it: ClubElo fixture probabilities as a feature; FPL Review export as a
   second projection source.

## Sources

- vaastav/Fantasy-Premier-League: https://github.com/vaastav/Fantasy-Premier-League
- FPL-Core-Insights: https://github.com/olbauday/FPL-Core-Insights
- LiveFPL rank tiers: https://plan.livefpl.net//rank_tiers ; top 10k: https://plan.livefpl.net//top10k
- FPL Review Elite 1000: https://docs.fplreview.com/team-analysis/elite-1000/ ; premium: https://docs.fplreview.com/getting-started/premium-features/
- Official price change predictor: https://www.premierleague.com/en/news/4680462/whats-new-in-202627-fantasy-price-change-predictor
- FBref loss of Opta data: https://www.theixsports.com/the-ix-soccer/fbrefs-loss-advanced-stats-womens-soccer-data-accessibility/
- The Odds API (EPL): https://the-odds-api.com/sports-odds-data/epl-odds.html
- ClubElo API: http://api.clubelo.com/ ; football-data.co.uk: https://www.football-data.co.uk/
