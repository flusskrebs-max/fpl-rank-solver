# Decision records

One short file per decision that would be expensive to reverse. Number them in order; never
renumber. If a decision changes, add a new record that supersedes the old one and mark the old
one "Superseded by NNNN".

| # | Decision | Status |
|---|---|---|
| [0001](0001-vendor-upstream.md) | Vendor open-fpl-solver unmodified and build alongside it | Accepted |
| [0002](0002-highs-and-formulation-limits.md) | HiGHS via highspy as the solver; keep models LP/MILP | Accepted |
| [0003](0003-environment-and-data.md) | Python 3.14 + uv; snapshot all live data; vaastav for history | Accepted |
| [0004](0004-ownership-term-as-xp-adjustment.md) | Ownership weight as an xP adjustment (S1), equivalent to the community "risk" term; no vendor change | Accepted |
| 0005 | Licence for this repo | Open |
| 0006 | Objective v1: λ chosen by a normal approximation (S2) | To write when S2 ships (v0.2) |

## Template

```markdown
# NNNN: Title

Date: YYYY-MM-DD · Status: Proposed | Accepted | Superseded by NNNN

## Context
What forces are at play; what we know.

## Decision
What we're doing.

## Consequences
What gets easier, what gets harder, what we'll need to revisit.
```
