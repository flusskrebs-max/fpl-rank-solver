"""Run the vendored open-fpl-solver (expected-points objective) from Python.

This is our baseline: every rank-objective idea gets compared against "what would the
standard EV-maximising solver have done with the same inputs".

The upstream code fetches the FPL API and reads projection CSVs from its own data folder.
`solve_ev` swaps both for in-memory inputs, so the same call works offline, in tests and
in backtests. The vendored code itself is left unmodified.
"""

import copy
import json
import sys
from contextlib import contextmanager

import pandas as pd

from fplrank.paths import UPSTREAM_DIR


def _upstream():
    if str(UPSTREAM_DIR) not in sys.path:
        sys.path.insert(0, str(UPSTREAM_DIR))
    import dev.solver as upstream_solver

    return upstream_solver


def default_options() -> dict:
    """Upstream defaults (comprehensive_settings.json), quietened for programmatic use."""
    with open(UPSTREAM_DIR / "data" / "comprehensive_settings.json") as f:
        options = json.load(f)
    options.update({"verbose": False, "print_squads": False, "print_result_table": False, "print_transfer_chip_summary": False})
    return options


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


def solve_ev(
    my_data: dict,
    projections: pd.DataFrame,
    bootstrap: dict,
    fixtures: list[dict],
    options: dict | None = None,
) -> list[dict]:
    """Solve the standard multi-period EV problem and return upstream's list of solutions.

    my_data:     team state in the FPL /my-team/ shape (see fplrank.data.offline for helpers)
    projections: DataFrame in upstream CSV format (ID, Pos, {gw}_Pts, {gw}_xMins, ...)
    bootstrap:   /bootstrap-static/ payload (live or rebuilt from history)
    fixtures:    /fixtures/ payload
    options:     overrides on top of upstream defaults (horizon, chips, secs, ...)
    """
    solver = _upstream()
    opts = default_options()
    opts.update(copy.deepcopy(options or {}))
    responses = {
        "https://fantasy.premierleague.com/api/bootstrap-static/": bootstrap,
        "https://fantasy.premierleague.com/api/fixtures/": fixtures,
    }

    def offline_request(url):
        if url not in responses:
            raise KeyError(f"No offline response for {url}")
        return copy.deepcopy(responses[url])

    def in_memory_projections(_options, source=None):
        return projections.copy()

    with _patched(solver, cached_request=offline_request, read_data=in_memory_projections):
        data = solver.prep_data(copy.deepcopy(my_data), opts)
        return solver.solve_multi_period_fpl(data, opts)
