"""S2c: choosing λ from the gap with a normal approximation."""

import pandas as pd
import pytest

from fplrank.opt import rank_goal as rg


def test_level_with_the_field_is_a_coin_flip():
    assert rg.probability(0.0, 25.0, 0.0) == pytest.approx(0.5)
    assert rg.probability(0.0, 25.0, 0.0, sd_line=10) == pytest.approx(0.5)


def _plans():
    # λ = 0: best mean; cover (λ > 0) cuts variance a lot for a little mean; chase (λ < 0) adds variance
    return {
        0.0: {"moments": rg.Moments(mu=5.0, var=100.0, gws=5), "ev": 300.0},
        0.2: {"moments": rg.Moments(mu=4.0, var=40.0, gws=5), "ev": 296.0},
        -0.2: {"moments": rg.Moments(mu=3.0, var=250.0, gws=5), "ev": 293.0},
    }


def test_ahead_covers_behind_chases():
    ahead = rg.choose_lambda(gap=-80, gws_left=10, plans=_plans())
    behind = rg.choose_lambda(gap=120, gws_left=10, plans=_plans())
    assert ahead.iloc[0]["lam"] == 0.2 and behind.iloc[0]["lam"] == -0.2
    assert ahead.set_index("lam").loc[0.2, "ev_cost"] == pytest.approx(4.0)


def test_season_moments_use_base_for_later_gws():
    mu, var = rg.season_moments(rg.Moments(4.0, 40.0, 5), rg.Moments(5.0, 100.0, 5), gws_left=15)
    assert (mu, var) == (4.0 + 1.0 * 10, 40.0 + 20.0 * 10)


def test_plan_moments_relative_to_field():
    proj = pd.DataFrame({"ID": [1, 2, 3], "Pos": ["M", "M", "F"], "6_Pts": [6.0, 4.0, 2.0]})
    picks = pd.DataFrame({"id": [1, 2], "week": [6, 6], "multiplier": [2, 1]})
    sol = {"picks": picks, "statistics": {6: {"pt": 0}}}
    vtable = pd.DataFrame({"pos": ["M", "M", "M", "F", "F", "F"], "band": [1, 2, 3, 1, 2, 3], "pts_var": [1.0, 4.0, 9.0, 1.0, 4.0, 9.0]})
    eo = pd.Series({1: 1.5, 3: 0.5})
    m = rg.plan_moments(sol, proj, eo, vtable, kappa=1.0)
    # bands within the source: 2 -> 1, 4 -> 2, 6 -> 3 (three players, three bands)
    assert m.mu == pytest.approx((2 - 1.5) * 6 + 1 * 4 - 0.5 * 2)
    assert m.var == pytest.approx(0.5**2 * 9 + 1 * 4 + 0.5**2 * 1)
    assert rg.plan_moments(sol, proj, eo, vtable, kappa=0.3).mu == pytest.approx(0.3 * m.mu)


def test_plan_moments_read_long_position_codes_and_hit_cost():
    """FPL Review's GKP/DEF/MID/FWD reach us before his parser shortens them; hits use the solve's hit cost."""
    proj = pd.DataFrame({"ID": [1, 2, 3], "Pos": ["M", "M", "F"], "6_Pts": [6.0, 4.0, 2.0]})
    picks = pd.DataFrame({"id": [1, 2], "week": [6, 6], "multiplier": [2, 1]})
    vtable = pd.DataFrame({"pos": ["M", "M", "M", "F", "F", "F"], "band": [1, 2, 3, 1, 2, 3], "pts_var": [1.0, 4.0, 9.0, 1.0, 4.0, 9.0]})
    eo = pd.Series({1: 1.5, 3: 0.5})
    short = rg.plan_moments({"picks": picks, "statistics": {6: {"pt": 0}}}, proj, eo, vtable)
    long = rg.plan_moments({"picks": picks, "statistics": {6: {"pt": 0}}}, proj.assign(Pos=["MID", "MID", "FWD"]), eo, vtable)
    assert long == short and short.var > 0
    hit = rg.plan_moments({"picks": picks, "statistics": {6: {"pt": 1}}}, proj, eo, vtable, hit_cost=6)
    assert hit.mu == pytest.approx(short.mu - 6)
