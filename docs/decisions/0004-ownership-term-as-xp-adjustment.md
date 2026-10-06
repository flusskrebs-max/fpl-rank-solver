# 0004: Ownership weight as an xP adjustment, not a new objective term

Date: 2026-10-06 · Status: Accepted (Alex, 2026-10-06)

## Context

The community "risk" knob (Sertalp's AlpsCode post "On FPL, Optimization, and Ownership Weights";
FPL Review's "Risk Position", about ±0.15) adds `w × EO × xP` for every player owned: positive `w`
covers the template, negative `w` chases differentials. The vendored open-fpl-solver has no such
setting (checked: no risk, ownership or EO option anywhere in `vendor/`). Alex asked whether we should
instead feed EO and xP (e.g. from Solio) into a solve with an explicit weight on EO.

## Decision

Keep S1's mechanism: scale the projections before the upstream EV solve,

    xP' = xP × (1 + λ(EO − 1)) = (1 − λ) × xP + λ × EO × xP

which is the community term plus a uniform rescaling of xP by (1 − λ). The objective is linear, so it
behaves like an explicit EO term: the captain counts ×2 and Triple Captain ×3 in both. Three small
differences, all accepted:

1. Upstream's bench weights (0.03-0.21) and vice-captain weight (0.1) also see the adjusted xP.
2. Upstream's player-pool pre-filter (top EV percent) runs on adjusted xP.
3. The (1 − λ) rescaling shifts the trade-off between points and hits/FT value by a few percent.

An explicit term would need edits to `vendor/` (against ADR 0001) for no material gain.

EO sources: any EO table can feed S1 (`--eo`). Solio EO becomes a source once we have an export that
contains it (none of the five registered exports does). Our EO modeller covers what Solio doesn't:
the target group (AE64, top 10k) and GWs beyond the next (B04b).

## Consequences

- No vendor changes; S1 stays a thin wrapper and λ maps directly onto the community "risk" scale
  (λ ≈ w, apart from the rescaling).
- If an export with Solio EO arrives, it may replace S1c (EO at the deadline) for the next GW.
- S2 (choosing λ) is unaffected; its objective will be recorded separately when it ships.
