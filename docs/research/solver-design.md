# Solver design and test plan (v0.1)

Written 2026-10-05 in Cowork after the Phase 1 brainstorm. Nothing here is final; it is the plan we test against.

**Where this stands (2026-10-06).** Built: S1 (the λ knob, `opt/ownership.py`) and S2 (λ from a normal
approximation of the relative score, `opt/rank_goal.py`), run through Sertalp's solver by `fplrank solve`. Our scope is
only the EO projection and the λ choice; his solver does the team, projections, the MILP and his simulations. The EO
used today is last GW's collected EO with chips taken out (fair persistence); the next step is to re-pick each
manager's XI and captain on next-GW xP (`eo-blend.md`). [A] our own points simulator was built, parked and removed;
[D] rollout and V are not planned. Release order is in `docs/roadmap.md`. The sections below are the original plan.

## 1. What already exists (prior art)

| Who | What | How it treats rank |
|---|---|---|
| Sertalp (AlpsCode blog, "On FPL, Optimization, and Ownership Weights") | Adds an ownership term to the EV objective with a weight `w` | Penalty = Σ over *unselected* players of EO × xP. Since that equals a constant minus Σ EO·xP over *selected* players, it is a linear bonus `w·EO_p·xP_p` for owning templated players: a cover/safety knob. Fixed `w`, chosen by the user. |
| FPL Review solver ("Risk Position", ±0.15) | Same idea: risk ≈ EV × EO from a reference sample | Negative = more exposure to risk (chase), positive = cover. User sets the value. |
| DFS literature (Hunter, Vielma & Zaman 2016; Haugh & Singal 2021) | Maximise P(win a top-heavy contest) using means, variances, covariances and opponents' picks | Closest in spirit; single-slate, no transfers, no season dynamics. |
| Academic FPL work (e.g. Santoro thesis, Bologna; arXiv 2505.02170) | ML projections + MILP | Pure points; notes that multistage/dynamic optimisation is the missing piece. |

Takeaways:
- The community standard is a **linear EV×EO term with a hand-set sign and weight**. Our contribution is
  to *derive* that weight each week from the rank situation (gap, GWs left, chips) and to replace the
  linear proxy with an actual probability where it matters.
- Nobody public models **future** EO (the field's response) or path dependency. Discord discussion
  may exist but isn't searchable.

## 2. The core quantity

For GW t, your multiplier `m_pt` (0, 1, 2, 3) vs the target group's effective ownership `EO_pt`:

```
Δ_t = Σ_p (m_pt − EO_pt) · pts_pt  −  (your hits_t − group's average hits_t)
```

Success = Σ_t Δ_t over the remaining season ≥ G, the current points gap to the rank-X line. Everything
the solver does is about the distribution of Σ Δ_t.

Two facts that shape everything:

1. **Variance contribution of a player** ≈ (m − EO)² · Var(pts). Owning a 90%-EO player contributes
   (0.1)²σ²; *not* owning him contributes (0.9)²σ². So not owning a template player is a very large
   bet, and owning a 5% differential is also a large bet. Covariance terms matter for stacks.
2. **Relative points accrue only while ownership differs.** If you buy a player at 10% EO and the field
   piles in after he hauls, the relative gain from that haul is already banked. From then on he is
   nearly "neutral" for rank.

## 3. The "player hauls, everyone piles in" question

Say you own player P at 15% elite EO, he hauls, and next week elite EO jumps to 80%.

- **Keeping him** is now low-variance: you've become template on him. His future points move you
  very little relative to the field.
- **Selling him** turns him into a large *anti-template* bet: (0 − 0.8)² of his variance, betting he
  blanks. It costs an FT (or a hit) and usually some EV, since post-haul projections tend to rise a little.
- **So:** you usually shouldn't sell just because the field piled in. Selling him is one of the strongest
  *variance-raising* levers available, so it's worth it only when (a) you're well behind and need
  variance, and (b) his EV is close to the replacement's, so the variance is cheap. The solver should
  find this automatically. It's the same maths as captaining against the template.
- **The real lesson is about timing.** The value of a differential comes from owning him *before* EO
  rises. That makes the EO forecast central: buying a player the week before the pile-in captures the
  relative gain; buying the week after captures almost none, but still costs you the transfer.
- **Path dependency:** the field's EO next week depends on what happens *this* week (hauls, injuries,
  price moves). So the field model has to be simulated *per scenario*, not as one forecast.
  This is the main thing that makes the problem dynamic, and the reason a single static solve isn't enough.

## 4. Architecture (v1)

```
            projections (means)                 elite EO history, chips, FTs
                   │                                     │
     [A] Scenario engine                         [B] Field engine
     correlated player points,                   EO_t+1 | EO_t, scenario outcome_t,
     S paths × H GWs                             projections, chips left, FTs banked
                   │                                     │
                   └────────────► [D] Evaluator ◄────────┘
                                   relative score per path,
                                   end-of-horizon gap → V(gap, GWs left, chips)
                                          ▲
     [C] Candidate generator ─────────────┘
     MILP (upstream constraints) with xP_p + λ·EO_p·xP_p,
     λ swept over e.g. [−0.3, 0.3], plus captain/vice options,
     forced/banned players, roll vs use FT, chip on/off
                                          │
                                   [E] Decision
                                   pick the candidate with the highest P(target);
                                   report its EV cost vs the EV-best plan
```

- **[A] Scenario engine:** per-player mixtures (minutes: 0 / 1-59 / 60+; returns: goals, assists, clean
  sheets, bonus, saves, defensive contributions) scaled to match projection means. Shared team/fixture
  factors give correlation. Calibrated on last season's actuals.
- **[B] Field engine:** see B04. Two parts, ownership and multiplier (captaincy/TC/BB), conditioned on
  each scenario path's outcomes. Error bars come from sampling its parameters.
- **[C] Candidate generator:** reuses the upstream MILP. The λ·EO·xP term is exactly the community
  "risk position" knob, so we get its full range for free. Typically 20–60 candidates per week.
  As built in S1 (`opt/ownership.py`, 2026-10-06): xP' = xP·(1 + λ·(EO − 1)), a linear proxy for the
  variance of the relative score. Centring at EO = 1 is a scale choice (adjusted xP stays near raw xP,
  so λ mostly changes which players are picked, not the value of hits), not a neutral point: for
  variance, owning once is neutral at EO 0.5 and captaining at EO 1.5. Equivalent to the community
  `w·EO·xP` term plus a (1 − λ) rescaling of xP; the small differences are listed in ADR 0004.
- **[D] Evaluator:** for each candidate, simulate its first-week action and then a default policy for
  the rest of the horizon (re-solve with λ chosen by the value function: a "rollout"). At the end of
  the horizon, convert the gap to a probability with V.
- **Value function V(gap, GWs left, chips_you, chips_field):** precomputed by simulating many seasons'
  remainders with the rollout policy. It encodes how much variance you can still generate. It answers
  "how far behind is too far" and drives λ.
- **Rank-X line (end of season).** The target is final overall rank, not rank in any one GW. Success
  means finishing with at least the points of the rank-X manager at GW38. Write that line as
  `T_X(38) = T_X(now) + R_X`, where `T_X(now)` is today's rank-X total (live standings, available for
  the current season) and `R_X` is what the rank-X manager scores from here. Because the rank-X
  manager is, on average, a member of the target group, `R_X ≈` the group's template score plus its
  remaining chips, which is exactly what Δ is measured against. So the quantity the solver needs is
  just **G = T_X(now) − our points now**, plus a spread term for the fact that the rank-X line is a
  moving order statistic (whoever sits at rank X in May is an above-average member of the group).
  Per-GW historical rank curves are therefore *not* needed for the objective. They would only help
  calibrate that spread term, and we can get it another way: sample managers' `entry/{id}/history`
  (current-season rank by GW) from B03 as this season goes, and use end-of-season totals from the
  `past` field for previous seasons.
- **Reference thresholds** (end of season, from B03b's `past` sample of today's top 1000): 2025-26
  top 1k ≈ 2448, top 10k ≈ 2399, top 100k ≈ 2326 (winner 2582); 2024-25 top 1k ≈ 2656,
  top 10k ≈ 2600; 2023-24 top 10k ≈ 2573. Top 100 isn't covered by the sample yet. 2025-26 was a
  low-scoring season, about 200 points below the two before it.

Why not one big stochastic MILP? HiGHS has no mixed-integer quadratic, and the spike showed big-M
probability models are slow even when tiny. Generate-then-simulate keeps the MILP linear, makes each
piece testable on its own, and is easy to parallelise.

## 5. Test plan

### 5a. Invariants (unit tests, run on every push)

- Copy the field exactly (m = EO for all players, same hits) ⇒ Δ = 0 in every scenario.
- λ = 0 candidate equals the upstream EV solution.
- Scenario means match projection means within Monte Carlo error; no negative minutes, etc.
- Field engine: ownership in [0, 1], 15 owned per manager, EO totals = 1100% + captain + chips (± tolerance).
- Monotonicity: as the gap G grows, the chosen plan's σ(Δ) does not fall; as G becomes negative
  (you're ahead), σ(Δ) does not rise.
- Symmetry: two identical players produce identical decisions up to tie-breaks.

### 5b. Known-answer scenarios (small, hand-checkable)

- The toy spike (level → copy, behind → differentials) generalised to a 15-man squad.
- "Haul then pile-in": a synthetic player whose EO jumps from 15% to 80%. Check: ahead ⇒ keep;
  far behind with an equal-EV alternative ⇒ sell; far behind with a much better EV ⇒ keep.
- Captaincy: a 180% EO captain vs a 6.4 xP alternative at 20% EO; the switch point should move with G.

### 5c. Component calibration (against history)

- **Scenario engine:** P(≥10 pts), P(blank), position-level variance and within-team correlations vs
  2025-26 actuals. Pass if within the bootstrap bands of history.
- **Field engine:** forecast next-GW EO vs realised (Elite 64 and, later, top-1000 collector data).
  Must beat naive persistence ("next week = this week") on MAE, especially in the weeks after hauls.
- **Rank line:** predicted final rank-X total vs what it turned out to be, once we have a season of `T_X(now)` snapshots.

### 5d. Policy backtests (the real test)

- Replay 2025-26 (and this season as it goes) with the field taken from data where we have it and
  simulated where we don't. Start simulated managers at a grid of gaps and GWs left.
- Compare policies: pure EV, fixed λ (±0.1, ±0.2), and the full solver. Metric: P(finish ≤ X),
  plus the EV given up. Use X = 10k and 1k for statistical power; report 100 as a sanity check.
- Thousands of simulated seasons per cell, with confidence intervals. A policy "wins" only if its
  interval clears the EV policy's.

### 5e. Performance

- Weekly solve end to end in under ~10 minutes on Alex's PC (candidate MILPs in parallel, simulation
  vectorised with numpy).

## 6. Biggest risks

1. **Field data is thin** (64-manager samples, top-10 lists). Mitigation: the B03 collector; treat
   EO as uncertain everywhere.
2. **Projection means only.** Distributions are our own model. Mitigation: calibrate on history and
   keep the scenario engine simple at first.
3. **Top 100 is too rare to validate directly.** Mitigation: validate at 1k/10k and trust the maths.
4. **Overfitting the field model** to a few weeks of data. Mitigation: 2–4-parameter models, out-of-sample checks.
5. **Compute.** Mitigation: candidates are cheap MILPs (seconds each), simulation is vectorised.

## 7. Build order

Superseded on 2026-10-06 by the releases in `docs/roadmap.md`.
