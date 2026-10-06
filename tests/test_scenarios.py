"""Scenario engine v0 on a small synthetic league (no data downloads)."""

import numpy as np
import pandas as pd
import pytest

from fplrank.sim import scenarios as sc

XPTS = {"G": 3.5, "D": 3.8, "M": 4.5, "F": 5.0}
SHAPE = {"G": 1, "D": 4, "M": 4, "F": 2}


def _league():
    """4 teams. GW1: 1v2, 3v4. GW2: 1v3, 2v4, 1v4 (teams 1 and 4 double). GW3: 1v3 only (2 and 4 blank)."""
    rows, pid = [], 0
    for team in (1, 2, 3, 4):
        for pos, k in SHAPE.items():
            for _ in range(k):
                pid += 1
                for gw in (1, 2, 3):
                    rows.append({"gw": gw, "fpl_id": pid, "pos": pos, "team_id": team, "xmins": 88.0, "xpts": XPTS[pos]})
    proj = pd.DataFrame(rows)
    doubles = proj["team_id"].isin([1, 4]) & (proj["gw"] == 2)
    proj.loc[doubles, ["xmins", "xpts"]] *= 2
    blanks = proj["team_id"].isin([2, 4]) & (proj["gw"] == 3)
    proj.loc[blanks, ["xmins", "xpts"]] = 0.0
    fixtures = pd.DataFrame({"event": [1, 1, 2, 2, 2, 3], "team_h": [1, 3, 1, 2, 1, 1], "team_a": [2, 4, 3, 4, 4, 3]})
    return proj, fixtures


@pytest.fixture(scope="module")
def simulated():
    proj, fixtures = _league()
    return proj, sc.simulate(proj, fixtures, S=6000, H=3, seed=7)


def test_shape_and_integer_points(simulated):
    proj, pts = simulated
    assert pts.shape == (6000, 3, proj["fpl_id"].nunique())
    assert np.issubdtype(pts.dtype, np.integer)
    assert pts.min() >= -6 and pts.max() < 60


def test_means_match_projections(simulated):
    proj, pts = simulated
    report = sc.match_report(proj, pts, 3)
    live = report[report["xpts"] > 0]
    tolerance = 5 * live["se"] + 0.1  # Monte Carlo error here plus in the rate fit
    assert ((live["sim_mean"] - live["xpts"]).abs() <= tolerance).all(), live.assign(d=live["sim_mean"] - live["xpts"]).sort_values("d")


def test_blanks_score_zero_and_doubles_score_more(simulated):
    proj, pts = simulated
    players = sc.player_index(proj)
    team = proj.drop_duplicates("fpl_id").set_index("fpl_id")["team_id"].reindex(players).to_numpy()
    assert (pts[:, 2, np.isin(team, [2, 4])] == 0).all()  # GW3 blank
    gw1, gw2 = pts[:, 0, team == 1].mean(), pts[:, 1, team == 1].mean()
    assert gw2 > 1.7 * gw1  # GW2 double


def test_team_mates_rise_together_and_defenders_share_clean_sheets():
    proj, fixtures = _league()
    gw1 = proj[proj["gw"] == 1]
    players = sc.player_index(gw1)
    rules, params = sc.RULES["2026-27"], sc.DEFAULT_PARAMS
    sl = sc._gw_slots(gw1, fixtures[fixtures["event"] == 1], players, rules, params)
    rng = np.random.default_rng(3)
    pts, parts = sc._simulate_slots(sl, sc._fit_rates(sl, rng, rules, params), 20000, rng, rules, params, detail=True)
    team = gw1.set_index("fpl_id")["team_id"].reindex(players).to_numpy()[sl.player]
    pos = sl.pos
    attackers = np.flatnonzero((team == 1) & (pos >= 2))
    a, b = attackers[0], attackers[-1]
    assert np.corrcoef(pts[:, a], pts[:, b])[0, 1] > 0.02  # shared team goals
    rival = np.flatnonzero((team == 2) & (pos >= 2))[0]
    assert np.corrcoef(pts[:, a], pts[:, rival])[0, 1] < np.corrcoef(pts[:, a], pts[:, b])[0, 1]
    d1, d2 = np.flatnonzero((team == 1) & (pos == 1))[:2]
    both_full = parts["full"][:, d1] & parts["full"][:, d2]
    assert (parts["clean"][both_full, d1] == parts["clean"][both_full, d2]).all()  # same clean sheet
    assert not (parts["full"] & parts["sub"]).any()  # one minutes state each


def test_minutes_states_are_probabilities():
    p0, p1, p2 = sc.minutes_states([0, 10, 45, 70, 90, 120])
    np.testing.assert_allclose(p0 + p1 + p2, 1)
    assert (np.array([p0, p1, p2]) >= 0).all()
    assert p0[0] == 1  # xMins 0 = out
    assert (np.diff(p2) >= 0).all() and 0.85 < p2[4] < 1  # even nailed starters miss some games (2023-24 table)


def test_with_team_ids_matches_name_variants():
    teams = [
        {"id": 1, "name": "Leeds", "short_name": "LEE"},
        {"id": 2, "name": "Ipswich Town", "short_name": "IPS"},
        {"id": 3, "name": "Man City", "short_name": "MCI"},
    ]
    proj = pd.DataFrame({"team": ["Leeds United", "Ipswich", "Man City", "MCI"]})
    assert sc.with_team_ids(proj, teams)["team_id"].tolist() == [1, 2, 3, 3]
    with pytest.raises(ValueError):
        sc.with_team_ids(pd.DataFrame({"team": ["Atlantis"]}), teams)
