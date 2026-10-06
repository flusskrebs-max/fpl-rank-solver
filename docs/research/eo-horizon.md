# λ across the horizon: `--eo_decay` (2026-10-06)

How `fplrank solve` applies the EO weighting to GWs after the next one, and a first comparison on a real team.

## The rule

xP' = xP x (1 + λ_k x (EO_k - 1)), with λ_k = λ x d^k for the GW k weeks after the next (d = `--eo_decay`,
default 0.7; d = 0 is the old next-GW-only rule).

- **Order with Sertalp's decay.** We scale his projections when he reads them (`read_data`), before his
  objective discounts each GW by `decay_base`^k (0.9 in Alex's settings). So the EO term already decays with xP;
  `d` is extra. With d = 0.7 the EO term falls by 0.63 a GW (0.9 x 0.7), xP by 0.9: by GW+4 the EO term is at
  16% of its next-GW weight, xP at 66%. This is the bug McSpoish described (EO term not decayed while EV is)
  avoided twice over.
- **EO_k per GW.** The collector group's current squads, XI and captain re-picked on each GW's xP
  (`ownership.repick_eo` with an xP frame). Before this, every GW reused next GW's EO, so later GWs carried next
  GW's captain (e.g. Haaland at 198% EO in a GW where the field would captain someone else).
- **What λ·d^k means.** Equal to pulling every player's EO towards 100% by d^k. That is a sensible shrink for a
  180% captain, but not for a 0% differential or a 95%-owned defender, whose EO won't drift to 100%. First
  version; a per-player shrink towards an expected level would be the next step if it matters.

## Choosing d

EO itself persists well. 2025-26 elite EO (`datasets/elite_ownership/elite64_eo_calculated_2025-26.csv`, GW5+),
regression slope of EO - 1 at t + k on EO - 1 at t:

| k | 1 | 2 | 3 | 4 | 5 | 6 | 8 |
|---|---|---|---|---|---|---|---|
| AE64 | 0.79 | 0.75 | 0.70 | 0.65 | 0.59 | 0.57 | 0.52 |
| E64 | 0.82 | 0.77 | 0.73 | 0.68 | 0.61 | 0.60 | 0.55 |

So forecast quality alone would argue for d ≈ 0.95 a GW (relative to next GW). The rank-goal maths gives no
reason for λ to fall with distance by itself: there is one price of variance per GW. 0.7 is deliberately harder:
we re-solve every week with fresh EO, so a later GW's EO only matters through this week's moves, and it stops a
plan buying into EO it can't act on yet. It is a judgement, which is why `--eo_decay` is a flag.

## Team 157924, target top 10k, AE64 (Solio GW06_20261005, horizon 8, his settings)

Line 398 after GW5, we have 358, gap 80 ± 42 over 33 GWs. GW6 moves; EV over the horizon, undiscounted.

| d | chosen λ | P(top 10k) | EV plan's P | EV cost | GW6 moves at the chosen λ | P at λ = -0.3 / +0.3 |
|---|---|---|---|---|---|---|
| 0 | 0 | 30.3% | 30.3% | 0 | Palmer, Gonzalo, De Cuyper in; Isak, Wirtz, Calafiori out; B.Fernandes (c) | 29.5 / 30.2% |
| 0.7 | -0.2 | 30.6% | 30.3% | 0.7 | Gonzalo, Barnes, De Cuyper in; Isak, Szoboszlai, Konsa out; B.Fernandes (c) | 30.2 / 29.6% |
| 1 | 0 | 30.3% | 30.3% | 0 | (EV plan) | 27.2 / 27.3% |

- **Plans change**, P barely does. With d = 0.7 the chosen plan swaps Palmer for Barnes and sells Szoboszlai and
  Konsa instead of Wirtz and Calafiori; positive λ brings in Saka (captain) for Gabriel instead of Palmer. But P
  moves by 0.3 points, well inside the model's noise: this week λ is close to irrelevant for this team.
- **d = 1 shows the failure mode**: at λ = ±0.3 the plans give up 7-17 points of horizon EV (464 vs 481) and P
  falls to 27%. With d = 0.7 the worst plan gives up 2 points.
- **Hits at λ < 0** (the (1 - λ) uplift on low-EO players now applies across the horizon): the negative-λ plans
  make 3-4 moves against 3 for the EV plan. P is scored on raw xP, so a plan that buys cheap hits is penalised
  there; worth watching, not acted on.
- `score_plan`'s EV is undiscounted while his solver maximises discounted points, so a λ plan can show a slightly
  higher EV than λ = 0 (d = 1, λ = 0.05: 481.7). Left as is; it only affects the reported EV cost.

One team, one GW: no conclusion about d beyond "0.7 avoids the d = 1 blow-up and changes plans at the margin".
The 2025-26 replay (RP1) is where to test it properly.
