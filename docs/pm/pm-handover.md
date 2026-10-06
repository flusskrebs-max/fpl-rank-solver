# PM context (handed over from Cowork, 2026-10-06)

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

## Status and next steps

See `docs/roadmap.md` (releases) and `docs/tasks/TASKS.md` (the queue); they replace the status
tables that used to be here.

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

## Open questions for Alex (answered 2026-10-06)

- Current rank: doesn't matter. Build a general solver where current points/rank and the target rank
  are inputs and the risk weight follows from them.
- Elite 64 team ids: found. AE64 = FPL league 1291919, E64 = FPL league 38543 (64 each, 4 in both);
  the collector reads both leagues each run.
- Still open: a source of past seasons' top-1000 entries for top-100 cut-offs (low priority).

## About Alex

New to Claude Code and git: explain git/GitHub steps briefly. British spelling, concise, no
clichés or "great question" openers. He prefers historical-first progress over waiting for perfect
data, and wants to see what the data says (pages and tables) as the work goes.
