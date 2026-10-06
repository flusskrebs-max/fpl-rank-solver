"""Run the vendored open-fpl-solver (expected-points objective) from Python.

This is our baseline: every rank-objective idea gets compared against "what would the
standard EV-maximising solver have done with the same inputs".

Every solve goes through Sertalp's own entry point, `run/solve.py::solve_regular`, the same way his
`run/simulations.py` calls it: our projections are written to his data folder as a projection file
(`data/fplrank.csv`, datasource `fplrank`) and everything else is a runtime option on top of his
settings files (comprehensive_settings.json + user_settings.json). He prints and saves his usual
output; we take his list of solutions back. The vendored code itself is left unmodified.
"""

import copy
import json
import sys
from contextlib import contextmanager

import pandas as pd

from fplrank.paths import UPSTREAM_DIR

SOURCE = "fplrank"  # the projection file we hand him: {UPSTREAM_DIR}/data/fplrank.csv


def _upstream():
    if str(UPSTREAM_DIR) not in sys.path:
        sys.path.insert(0, str(UPSTREAM_DIR))
    import dev.solver as upstream_solver

    return upstream_solver


def _solve_module():
    """His `run/solve.py`, imported as `solve` the way `run/simulations.py` does."""
    _upstream()
    run_dir = str(UPSTREAM_DIR / "run")
    if run_dir not in sys.path:
        sys.path.insert(0, run_dir)
    import solve

    return solve


@contextmanager
def _patched(module, **replacements):
    originals = {name: getattr(module, name) for name in replacements}
    for name, value in replacements.items():
        setattr(module, name, value)
    try:
        yield
    finally:
        for name, value in originals.items():
            setattr(module, name, value)


@contextmanager
def _bare_argv():
    """His parser reads sys.argv; simulations.py clears it before calling solve_regular, and so do we."""
    argv = sys.argv
    sys.argv = argv[:1]
    try:
        yield
    finally:
        sys.argv = argv


def solve_ev(
    my_data: dict,
    projections: pd.DataFrame,
    bootstrap: dict,
    fixtures: list[dict],
    options: dict | None = None,
) -> list[dict]:
    """Solve with his `solve_regular` and return his list of solutions (one per iteration, as he returns them).

    my_data:     team state in the FPL /my-team/ shape (passed as his `team_data: json_string`)
    projections: DataFrame in his CSV format (ID, Pos, {gw}_Pts, {gw}_xMins, ...), written to data/fplrank.csv
    bootstrap:   /bootstrap-static/ payload (live snapshot or rebuilt from history)
    fixtures:    /fixtures/ payload
    options:     runtime options on top of his settings files (horizon, chips, secs, ...)
    """
    solve = _solve_module()
    from dev import data_parser, solver

    projections.to_csv(UPSTREAM_DIR / "data" / f"{SOURCE}.csv", index=False, encoding="utf-8")
    runtime = {"datasource": SOURCE, "team_data": "json_string", "team_json": json.dumps(my_data), **copy.deepcopy(options or {})}
    responses = {
        "https://fantasy.premierleague.com/api/bootstrap-static/": bootstrap,
        "https://fantasy.premierleague.com/api/fixtures/": fixtures,
    }

    def snapshot_request(url):
        if url not in responses:
            raise KeyError(f"No snapshot for {url}")
        return copy.deepcopy(responses[url])

    # solve_regular returns only a summary table, so keep the full solutions on the way through
    solved = []
    original = solve.solve_multi_period_fpl

    def keep(data, opts):
        response = original(data, opts)
        solved.append(response)
        return response

    with (
        _patched(solve, cached_request=snapshot_request, solve_multi_period_fpl=keep),
        _patched(solver, cached_request=snapshot_request),
        _patched(data_parser, cached_request=snapshot_request),
        _bare_argv(),
    ):
        solve.solve_regular(runtime)
    return solved[0]
