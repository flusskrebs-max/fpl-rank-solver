# Research notes

What we know, newest findings first. Scope: the EO projection and the λ choice; Sertalp's solver does the rest.

## Where things stand (2026-10-06)

**EO for next GW.** `fplrank solve --eo <group>` uses last GW's collected EO with that GW's chips taken out
(triple captain as a normal captain, bench-boost bench 0, free hitters back on their own squads): *fair
persistence*. On 2026-27 GW2-5 that cuts persistence's EO error by 14% (AE64) and 11% (E64). Re-picking each
manager's XI and captain on their current squad from next-GW xP does much better: EO error 7.3 (AE64) and 5.8
(E64) points against 11.6 and 8.5 for persistence, and slightly better than running Sertalp's solver on every
manager's squad (7.9, 6.1). `--eo` now uses that re-pick (EO1b), with the armband herded onto the consensus
captain as the elite do (E64 EO error 5.8 to 5.2, AE64 unchanged at 7.3). What the per-manager solve
still adds is transfers: it catches more of the 20+ point ownership moves. Four transitions only, so treat the
numbers as a first look. Details: [eo-blend.md](eo-blend.md), [eo-naive-field.md](eo-naive-field.md).

**How elite EO moves** ([eo-patterns-2025-26.md](eo-patterns-2025-26.md)): two thirds of the 8-week EO drift is
already there after one week (XI and captain re-picks); no momentum, except that big fallers keep falling; the
week after a free hit looks like the week before it; wildcard turnover scales with the wildcard share; groups
move together in the same week but their gaps persist (keep groups separate).

**Choosing λ.** P(reaching the target line) from a normal approximation of our score relative to the EO group:
variance from v(xP) by position and projection band ([variance-table.md](variance-table.md)), checked against the
realised spread of real managers' scores (ratio 0.82-0.99, so s = 1; [realised-spread.md](realised-spread.md)).
The gap uses the line now plus its drift against the EO group ([rank-cutoffs.md](rank-cutoffs.md) for end-of-season
lines). Drift and the line's spread are measured against the group over full seasons 2018-26 (top 10k: +1.2 a GW,
±11 over 33 GWs vs E64, ±42 vs AE64; the drift is a lower bound), and κ = 0.75: real managers' projected edges
come through at about 1:1 ([rank-goal-inputs.md](rank-goal-inputs.md)).

## Index

| Note | What it is |
|---|---|
| [problem-framing.md](problem-framing.md) | Why rank and points differ; options considered |
| [solver-design.md](solver-design.md) | The original design and test plan, with a note on where it stands |
| [data-sources.md](data-sources.md) | Which data we use and why |
| [eo-blend.md](eo-blend.md) | Next-GW EO: fair persistence, re-pick, per-manager solve and templates, blended (current) |
| [eo-naive-field.md](eo-naive-field.md) | Sertalp's solver on every AE64/E64 squad as an EO forecast |
| [eo-patterns-2025-26.md](eo-patterns-2025-26.md) | How elite EO moves week to week (exploration, no model) |
| [top1000-vs-elite64.md](top1000-vs-elite64.md) | Collector EO against the Elite 64 graphics |
| [variance-table.md](variance-table.md) | v(xP) by position and projection band (S2b) |
| [realised-spread.md](realised-spread.md) | S2's predicted sd against real managers' spread (V1) |
| [eo-horizon.md](eo-horizon.md) | λ on later GWs: `--eo_decay`, per-GW re-picked EO, d = 0 / 0.7 / 1 on a real team |
| [rank-goal-inputs.md](rank-goal-inputs.md) | Line spread and drift against the group, and κ, for P(target) |
| [rank-cutoffs.md](rank-cutoffs.md) | End-of-season points for top 100 / 1k / 10k / 100k |
| [archive/](archive/) | Superseded: EO projector proposal, EO flow model (failed), EO dynamics v0, scenario engine calibration, phase 1 notes |
