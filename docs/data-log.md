# Data log

What data we have, where it lives, and first observations. Newest first. Maintained in the repo by
Claude Code (PM + developer) since 2026-10-06; earlier entries were written by the Cowork PM.

## 2026-10-06: Data sources review

- vaastav has stopped weekly updates; its 2025-26 `xP` is filled only for GWs 1-6, 8, 9, 24, 29 and 38.
- FPL-Core-Insights `playerstats.csv` has FPL's `ep_next` for every 2025-26 GW (and 2026-27 so far);
  it tracks vaastav `xP` closely (correlation 0.92-0.97, mean absolute difference 0.2-0.45 points on
  the GWs where both exist). Basis for D1, S1b, S2b and B04b. Details: `docs/research/data-sources.md`.
- FBref lost its Opta xG on 2026-01-20; not a source for us.

## 2026-10-06: Elite 64 collected directly (2026-27 GW1-5)

- The collector now reads AE64 (FPL league 1291919) and E64 (league 38543) each run: 64 managers
  each, 4 in both. First run: all 128 managers, GW1-5, no failures (`data/collected/`, sets AE64/E64).
- Check against the transcribed graphics (360 listed player-GWs): mean absolute EO gap 0.5 / 0.7
  percentage points (AE64 / E64), correlation 1.00 / 0.998. So the graphics transcription is good and
  the collected EO can replace it from now on.
- Three rows disagree and look like transcription or id slips in `elite64_eo_2026-27.csv`: O'Reilly GW3
  (11% in both groups vs 0 collected), João Pedro GW5 E64 (28% vs 0), Kinsky GW1 E64 (64% vs 52%).
  Worth fixing when B04b uses the data.

## 2026-10-05: Elite 64 2025-26, full season transcribed

- Source: Alex's folder of Solio graphics (`Downloads\Ae64E64 data 2025`). Transcribed all of it:
  EO GW10–38, captains/FTs/chips/hits/full transfer lists GW1–38, GW1 squad ownership, GW6 WC picks.
  Names matched to FPL ids (vaastav 2025-26). Files in `datasets/elite_ownership/elite64_*_2025-26.csv`
  (ingested by B06; derived ownership and calculated EO built by `scripts/elite64/`). Validation: transfers in = out every GW; in = Σ k·managers(k) fails in GW3/4/7/25 as well as GW38, and a few
  partition tables are off by 1-2 (all listed with exact values in `KNOWN_QUIRKS`, tests/test_elite_data.py).
- Page: "Elite 64 Flows 2025-26" artifact (https://claude.ai/artifact/2EoksQZ4ZW1GPNsvXYJwNp).
- Season averages (AE64 / E64): 1.15 / 1.19 transfers per GW; 33% / 30% roll; 2.6 / 2.2 FTs banked;
  hits on 0.8% / 5.5% of manager-weeks; top captain held by 87% / 84% (≈1.4 / 1.6 effective
  captains); 9.5 / 8.4 players at ≥50% EO; groups diverge by ~240 EO points a week.
- Pile-ins are forward-looking: after a 15+ haul, mean net inflow next GW was +1.7% / +3.2% of the
  group; only 6–7% of hauls drew ≥10% of a group. The largest single-week moves (Bowen GW38, Cunha
  GW18, Virgil GW12, Rice GW25, Cherki GW36) followed fixtures/doubles/captaincy. Input for B04.
- Chip clusters: WC GW6 and GW32; FH GW13 and GW34; BB GW33 (and GW5/7 early); TC GW17, GW26, GW36.
- Listed EO covers 91–100% of expected total EO (mean 96% AE64, 94% E64) → residual for B01b ≈ 4–6%.
- AE64 outscored E64 by ~97 points on listed players GW10–38 (censored, indicative).
- Source quirks kept as-is: one AE64 manager deactivated GW29 (n=63); GW1 E64 sums to 62; GW3 E64
  "no chip" 62 (should be 57); GW38 captains 62/63 and FT table inconsistent with transfer lists.

## 2026-10-05: End-of-season rank thresholds

- Objective is final rank. Design updated: G = T_X(now) − our points; per-GW historical rank curves
  are not needed (only for the spread term). Winners: 2023/24 2799, 2024/25 2810, 2025/26 2582
  (13.1m players). B03b measured them from the `past` field of today's top 1000: 2025-26 top 1k ≈ 2448,
  top 10k ≈ 2399, top 100k ≈ 2326; 2024-25 top 10k ≈ 2600; 2023-24 top 10k ≈ 2573 (the 2380 figure
  I'd quoted from a web article was wrong). Top 100 not covered by the sample.

## 2026-10-05: GW6 projections (Solio export "projection 8")

- Covers GW6-17, 562 players, BV reflects current prices (so made this week, before GW6 deadline).
  IDs consistent with FPL 2026-27 IDs (51 mismatches vs the GW1 vaastav snapshot are summer/late
  signings, IDs > 616).
- Versus pre-season baseline (projection 2), GW6-17 totals:
  - Biggest genuine form/role risers among premiums: Isak +11 (xMins 58→78), Havertz +13 (63→80),
    Saka +10, João Pedro +8, Rogers +8, Mbeumo +6. Haaland −2.5.
  - Huge swings for transferred/injured players (N.Jackson now Villa, Grealish Everton, Delap Forest,
    Rashford Man Utd), so "projection change" mostly reflects minutes/role, not quality.
  - Team totals: Chelsea +37, Everton +38 up; Fulham −90, Ipswich −74, Liverpool −73 down.
- GW6 projected top 5: B.Fernandes 6.38, Saka 6.24, Palmer 6.10, Rogers 5.55, Haaland 5.48.

### Elite GW5 EO vs GW6 projection (first look at "where the elite disagree with the model")

| Player | AE64 EO | E64 EO | GW6 xP (rank) |
|---|---|---|---|
| Haaland | 150% | 181% | 5.48 (5th) |
| Palmer | 89% | 83% | 6.10 (3rd) |
| Szoboszlai | 81% | 56% | 4.29 (29th) |
| Saka | 56% | 23% | 6.24 (2nd) |
| B.Fernandes | 44% | 23% | 6.38 (1st) |
| Van Hecke | 58% | 8% | 2.29 (203rd, 65 xMins) |
| Kinsky | 11% | 48% | 2.69 (180th) |
| Calafiori | 31% | 80% | 4.51 (22nd) |

Takeaways: Haaland's EO is captaincy-driven (150-181%) while he is only 5th by GW6 projection, a
classic rank decision (captain Fernandes/Saka vs cover Haaland). E64 is underweight on the two
highest projected GW6 players.

## 2026-10-05: Pre-season projections (projection 1, 2, 3)

- Solio export format, means only. All pre-GW1 (start at GW1, BV = starting price). Order 1 → 2 → 3
  by newest player IDs. Files 1-2: GW1-19; file 3: GW1-8. Useful as a baseline.

## 2026-10-05: Elite 64 graphics, GW1-5 (Downloads\AE64E64 data 2026)

- Solio/@FPL_Spaceman graphics for AE64 (analytics) and E64 (#Elite64, template). Per GW: EO for top
  ~7-10 per position, captains, chips active/remaining, FTs used/remaining, hits, transfers in/out.
  Transcribed (`datasets/elite_ownership/elite64_*_2026-27.csv`).
- 48/64 in both groups Bench Boosted GW1.
