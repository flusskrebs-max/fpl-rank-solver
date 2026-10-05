# 0001: Vendor open-fpl-solver unmodified and build alongside it

Date: 2026-10-05 · Status: Accepted

## Context

open-fpl-solver already solves the full FPL multi-period problem (squad rules, transfers, free
transfer banking, selling prices, chips) with HiGHS. We want all of that, but with a different
objective. Upstream is not packaged for import (it relies on top-level `paths`/`utils` modules and the
working directory), and its model is one function that builds constraints and objective together.

Options considered: fork the repo and work inside it; git submodule; git subtree; plain vendored copy.

## Decision

Keep a plain, unmodified copy under `vendor/open-fpl-solver/`, pinned by commit in
`vendor/.open-fpl-solver-commit`, refreshed with `scripts/update_upstream.sh`. Our code lives in
`src/fplrank/`. `fplrank.baseline` calls upstream's `prep_data` and `solve_multi_period_fpl` with
the network and file reads swapped for in-memory inputs. When we need upstream's constraints with
a new objective, we port and refactor them into `src/fplrank/opt/` with attribution.

## Consequences

- Upstream updates are a clean replace plus `git diff`; no merge conflicts, no submodule commands.
- The EV baseline stays exactly what upstream users get, which keeps comparisons honest.
- Ported code can drift from upstream bug fixes; check the upstream changelog when updating.
- Apache-2.0 obligations: keep upstream's LICENSE, keep NOTICE, mark modified ported files.
