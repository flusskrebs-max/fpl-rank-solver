# PM handover (from Cowork, 2026-10-06)

Until now planning ran in a Cowork project and building in Claude Code, linked by an inbox folder.
From now on Claude Code does both (see "How we work" in `CLAUDE.md`). This note is the PM context.

## Goal and agreed decisions

- Maximise **P(final overall rank ≤ X)** with X an input. Develop and validate at 1k/10k (top 100 is
  too rare to test directly), then run at 100. The target is **end of season**, so the solver needs
  today's points gap to the rank-X line, not historical per-GW rank curves (solver-design §4).
- Account for our chips and the target group's remaining chips; forecast the target group's EO,
  including captaincy-driven pile-ins; always report the EV given up for any risk taken.
- Architecture (solver-design §4): [A] correlated points simulator → [B] field/EO model → [C] MILP
  candidate plans across ownership weights (the community "risk position" knob) → [D] simulate each
  candidate's relative score Δ = Σ (our multiplier − EO) × points − hits → value function
  V(gap, GWs left, chips) → [E] pick the best, with its EV cost. HiGHS has no MIQP, so risk is handled by
  simulation, not inside the MILP.
- Historical first: build from what we've assembled (2025-26 Elite 64 season, vaastav seasons,
  collector data) rather than waiting a season.

## Where things stand

| Piece | State |
|---|---|
| Data: Elite 64 2025-26 (EO, captains, chips, FTs, full transfer lists, rebuilt ownership, calculated EO), 2026-27 GW1-5, collector (top 1000, twice weekly), projection loader, rank cut-offs | Done |
| [B] field model v0 (`model/ownership.py`) | Built on 2026-27 GW1-5 only (4 transitions); beats persistence by ~20%. **B04b** (refit on full 2025-26) not started |
| [A] simulator (`sim/scenarios.py`) | v0 merged. **B07b → PR #11, not merged**: tuned 2023-24, tested 2024-25. Event engine has the best log score but ordinary players haul too often (10+: 4.0% vs 2.9%); the empirical benchmark gets haul rates and premium means right. Report recommends the benchmark for haul-sensitive use for now |
| [C]-[E] | Not started |

## Next, in order

1. Merge PR #10 (design doc thresholds) and review/merge PR #11.
2. **Decide [A] for v1:** use the empirical benchmark as the default simulator (tails matter most for a
   rank objective) and keep the event engine as research. Its biggest known fix is projected minutes
   for old seasons (xP band × recent minutes). Record the choice as an ADR.
3. **B04b:** refit and backtest the field model on all of 2025-26 (brief in `docs/tasks/briefs/`).
   Must beat "next week = this week" overall and in double/blank/chip weeks.
4. **Brief and build the single-GW solver ([C] + [D])**:
   - Inputs: latest Solio projection (B02 registry), our squad/bank/FTs/chips (API snapshot), the
     target group's forecast EO (B04), the simulator.
   - Candidates: upstream MILP with objective xP + λ·EO·xP for λ on a grid (about −0.3 to 0.3), plus
     captain alternatives, roll vs use FT, chip on/off. 20-60 candidates.
   - Evaluate each: simulate Δ for the GW and report mean, spread, P(Δ ≥ g) for a few gaps g, and EV
     cost vs the EV-best plan. No value function yet.
   - Known-answer tests from solver-design §5b: copying the field gives Δ ≡ 0; λ = 0 equals the EV
     solve; "haul then pile-in" keep/sell cases; captain switch point moves with the gap.
5. Value function V by simulating season remainders; then policy backtests on 2025-26 (solver-design §5d).

## Data and findings worth remembering (details in `docs/data-log.md`)

- End-of-season cut-offs 2025-26: top 1k ≈ 2448, top 10k ≈ 2399, top 100k ≈ 2326 (winner 2582).
  2024-25 top 10k ≈ 2600; 2023-24 ≈ 2573. Top 100 not measured (the top-1000 `past` sample doesn't reach it).
- Elite 64 2025-26: pile-ins follow fixtures and captaincy, not last week's points (after a 15+ haul
  only +2-3% net inflow); the top captain takes ~85% of a group; chips cluster (WC 6/32, FH 13/34,
  BB 33, TC 17/26/36); the two elite groups differ by ~2-3 players' worth of EO a week, so the target
  group is a real input. The overall top 1000 is much less template than either elite group.
- EO from the graphics is the top ~10 per position; listed EO covers 91-100% of the total.
  Squad ownership is rebuilt exactly from transfers between wildcards; calculated EO is within
  ~5 points of the graphics outside Free Hit weeks.
- vaastav `xP` is missing (zero) for 27 of 38 GWs in 2025-26 but populated for 2023-24 and 2024-25.
- Solio projections: means only (`{gw}_xMins`, `{gw}_Pts`); paid, never committed.
- Elite 64 Flows 2025-26 page (charts and per-GW EO tables): https://claude.ai/artifact/2EoksQZ4ZW1GPNsvXYJwNp

## Open questions for Alex

- Current overall rank, and whether the target is this season or next (sets X and urgency).
- Who the Elite 64 managers are (team ids would let the collector track those groups directly).
- Top 100 cut-offs: a source of past seasons' top-1000 entries.

## About Alex

New to Claude Code and git: explain git/GitHub steps briefly. British spelling, concise, no
clichés or "great question" openers. He prefers historical-first progress over waiting for perfect
data, and wants to see what the data says (pages and tables) as the work goes.
