"""Full offline solve with the vendored upstream model. Downloads public historical data once."""

from collections import Counter

import pytest

from fplrank.baseline import solve_ev
from fplrank.data import historical, offline

SEASON = "2025-26"
NEXT_GW = 20


@pytest.mark.slow
@pytest.mark.network
def test_upstream_solver_picks_a_legal_squad():
    players = historical.players_raw(SEASON)
    teams = historical.teams(SEASON)
    fixtures = offline.build_fixtures(historical.fixtures(SEASON))
    bootstrap = offline.build_bootstrap(players, teams, NEXT_GW)
    gws = [NEXT_GW, NEXT_GW + 1]
    projections = offline.placeholder_projections(players, teams, fixtures, gws, games_played=NEXT_GW - 1)

    result = solve_ev(
        offline.preseason_team(),
        projections,
        bootstrap,
        fixtures,
        {"preseason": True, "horizon": 2, "use_wc": [NEXT_GW], "secs": 120, "xmin_lb": 0},
    )[0]

    squad = result["picks"][(result["picks"]["week"] == NEXT_GW) & (result["picks"]["squad"] == 1)]
    assert len(squad) == 15
    assert Counter(squad["pos"]) == {"GKP": 2, "DEF": 5, "MID": 5, "FWD": 3}
    assert max(Counter(squad["team"]).values()) <= 3
    prices = {e["id"]: e["now_cost"] for e in bootstrap["elements"]}
    assert sum(prices[int(i)] for i in squad["id"]) <= 1000
