# Vendored code

## open-fpl-solver

An unmodified copy of [solioanalytics/open-fpl-solver](https://github.com/solioanalytics/open-fpl-solver)
(originally by Sertalp Bilal, maintained by Chris Musson). The pinned commit is in
`.open-fpl-solver-commit`.

- **Do not edit files in here.** Our code wraps it (`src/fplrank/baseline.py`) or ports pieces of it
  into `src/fplrank/` with attribution. Keeping it untouched means updates are a clean replace.
- **To update:** `scripts/update_upstream.sh` (or `scripts/update_upstream.sh <commit>`), review the
  diff, run the tests, commit.
- **Licence:** Apache-2.0, dual-licensed with a commercial licence. Upstream states that commercial
  use requires a licence from info@fploptimized.com. See `open-fpl-solver/LICENSE` and the
  project-level `NOTICE`.
