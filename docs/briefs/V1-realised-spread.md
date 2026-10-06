# V1: Realised-spread check for S2

Status: Ready · Size: small-medium · Release: v0.2 · Depends on: S2b, collector picks and points

## Why

S2's σ comes from a model (Σ (m − EO)² × v(xP), covariance ignored). Before λ is chosen from it, check
it against what actually happened to real managers this season (critical review, 2026-10-06).

## Do

1. For each top-1000 and Elite 64 manager and each collected GW this season: realised
   `Δ = Σ (m − EO) × pts` against their group's EO (picks, multipliers and points from the collector).
2. For the same squads, S2's predicted σ for that GW. Compare the spread of Δ with σ (ratio by GW and
   overall).
3. Within ~20% → s = 1; otherwise set s to match, and report it.
4. Also output the line's drift against each EO group (line GW gain − group mean GW points) and the
   per-GW σ²_base for S2c.

## Done when

A short report in `docs/research/` with the ratio, the chosen s, drift and σ²_base, and the numbers
stored where S2c reads them.
