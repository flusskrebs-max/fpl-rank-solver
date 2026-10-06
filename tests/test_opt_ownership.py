"""S1 ownership-weighted solve: projection adjustment, plan scoring, and real solves on 2025-26 data."""

import gzip
import json
from itertools import pairwise
from pathlib import Path

import pandas as pd
import pytest

from fplrank.opt import ownership as ow


def _proj():
    return pd.DataFrame(
        {"ID": [1, 2, 3], "Pos": ["M", "M", "F"], "6_Pts": [6.0, 4.0, 2.0], "7_Pts": [5.0, 3.0, 1.0], "6_xMins": [90, 90, 90]}
    )


def test_adjust_is_identity_at_zero_and_neutral_at_eo_one():
    proj, eo = _proj(), pd.Series({1: 1.0, 2: 1.6})
    pd.testing.assert_frame_equal(ow.adjust_projections(proj, eo, 0.0), proj)
    adj = ow.adjust_projections(proj, eo, 0.2)
    assert list(adj["6_Pts"]) == pytest.approx([6.0, 4.0 * 1.12, 2.0 * 0.8])  # EO 1, 1.6, unlisted (0)
    assert list(adj["7_Pts"]) == pytest.approx([5.0, 3.0 * 1.12, 1.0 * 0.8])
    assert list(adj["6_xMins"]) == [90, 90, 90]


def test_load_eo_takes_latest_gw_and_prefers_collector(tmp_path):
    pd.DataFrame(
        {
            "season": "2026-27",
            "gw": [4, 5, 5, 5],
            "group": ["AE64", "AE64", "AE64", "top1000"],
            "fpl_id": [1, 1, 2, 1],
            "eo": [0.5, 0.7, 1.2, 0.1],
            "n_managers": 64,
        }
    ).to_parquet(tmp_path / "eo.parquet")
    eo, gw = ow.load_eo("AE64", 5, collected_dir=tmp_path)
    assert gw == 5 and eo[1] == 0.7 and eo[2] == 1.2
    eo, gw = ow.load_eo("top1000", collected_dir=tmp_path)
    assert gw == 5 and dict(eo) == {1: 0.1}
    with pytest.raises(ValueError):
        ow.load_eo("top1000", 3, collected_dir=tmp_path)


def _solution(captain_id, buy="-"):
    rows = []
    for w in (6, 7):
        for pid in (1, 2, 3):
            cap = int(pid == captain_id)
            rows.append(
                {
                    "id": pid,
                    "week": w,
                    "name": f"p{pid}",
                    "lineup": int(pid != 3),
                    "bench": 0 if pid == 3 else -1,
                    "captain": cap,
                    "multiplier": (1 + cap) * int(pid != 3),
                }
            )
    return {"picks": pd.DataFrame(rows), "statistics": {5: {"itb": 0}, 6: {"pt": 1}, 7: {"pt": 0}}, "buy": buy, "sell": "-", "chip": "-"}


def test_score_plan_uses_raw_xp_and_hits():
    proj, eo = _proj(), pd.Series({1: 0.5, 2: 1.5})
    s = ow.score_plan(_solution(captain_id=1), proj, eo)
    assert s["ev_next"] == pytest.approx(2 * 6 + 4 - 4)
    assert s["ev"] == pytest.approx(12 + 2 * 5 + 3)
    assert s["eo_held"] == pytest.approx(2 * 0.5 + 1.5)
    assert s["exposure"] == pytest.approx(1.5 * 6 + 0.5 * 4)
    assert s["captain"] == "p1"


def test_plan_key_tells_captains_apart():
    assert ow.plan_key(_solution(1)) == ow.plan_key(_solution(1))
    assert ow.plan_key(_solution(1)) != ow.plan_key(_solution(2))
    assert ow.plan_key(_solution(1)) != ow.plan_key(_solution(1, buy="Saka"))


# --- real solves (upstream MILP on 2025-26 history) ------------------------------------------

SEASON, GW = "2025-26", 20


@pytest.fixture(scope="module")
def setup():
    from fplrank.data import historical, offline

    players, teams = historical.players_raw(SEASON), historical.teams(SEASON)
    fixtures = offline.build_fixtures(historical.fixtures(SEASON))
    bootstrap = offline.build_bootstrap(players, teams, GW)
    proj = offline.placeholder_projections(players, teams, fixtures, [GW], games_played=GW - 1)
    opts = {"preseason": True, "horizon": 1, "use_wc": [GW], "secs": 120, "xmin_lb": 0, "keep_top_ev_percent": 30, "gap": 0}
    return offline.preseason_team(), proj, bootstrap, fixtures, opts


def _xp_weighted_eo(sol, proj, eo):
    xp = proj.set_index("ID")[f"{GW}_Pts"]
    rows = sol["picks"][sol["picks"]["week"] == GW]
    return sum(r.multiplier * xp[r.id] * eo.get(r.id, 0.0) for r in rows.itertuples())


@pytest.mark.slow
@pytest.mark.network
def test_lambda_zero_is_the_ev_plan(setup):
    from fplrank.baseline import solve_ev

    my_data, proj, bootstrap, fixtures, opts = setup
    eo = pd.Series(dict.fromkeys(proj.nlargest(30, f"{GW}_Pts")["ID"], 1.4))
    ev = solve_ev(my_data, proj, bootstrap, fixtures, opts)[0]
    s0 = ow.solve_with_ownership(my_data, proj, eo, 0.0, bootstrap, fixtures, opts)
    assert ow.plan_key(s0) == ow.plan_key(ev)


@pytest.mark.slow
@pytest.mark.network
def test_rising_lambda_trades_ev_for_field_cover(setup):
    my_data, proj, bootstrap, fixtures, opts = setup
    # a field that owns some good-but-not-best players heavily
    ranked = proj.sort_values(f"{GW}_Pts", ascending=False)["ID"].tolist()
    eo = pd.Series({**dict.fromkeys(ranked[5:25], 1.0), **dict.fromkeys(ranked[25:40], 0.8), ranked[10]: 1.8})
    sols = [ow.solve_with_ownership(my_data, proj, eo, lam, bootstrap, fixtures, opts) for lam in (0.0, 0.1, 0.2, 0.3)]
    cover = [_xp_weighted_eo(s, proj, eo) for s in sols]
    evs = [s["ev"] for s in sols]
    assert all(b >= a - 1e-6 for a, b in pairwise(cover))
    assert all(b <= a + 1e-6 for a, b in pairwise(evs))
    assert cover[-1] > cover[0] and evs[-1] < evs[0]


@pytest.mark.slow
@pytest.mark.network
def test_captain_flips_to_the_high_eo_player(setup):
    my_data, proj, bootstrap, fixtures, opts = setup
    s0 = ow.solve_with_ownership(my_data, proj, pd.Series(dtype=float), 0.0, bootstrap, fixtures, opts)
    rows = s0["picks"][s0["picks"]["week"] == GW]
    cap = int(rows.loc[rows["captain"] == 1, "id"].iloc[0])
    other = int(rows[(rows["lineup"] == 1) & (rows["captain"] == 0)].sort_values("xP")["id"].iloc[-1])
    proj = proj.copy()
    cap_xp = proj[f"{GW}_Pts"].max() + 1  # placeholder projections have ties: make the captain clear
    proj.loc[proj["ID"] == cap, f"{GW}_Pts"] = cap_xp
    proj.loc[proj["ID"] == other, f"{GW}_Pts"] = cap_xp - 0.2  # slightly worse than our EV captain...
    eo = pd.Series({cap: 0.3, other: 1.6})  # ...but the field captains him

    def captain(lam):
        s = ow.solve_with_ownership(my_data, proj, eo, lam, bootstrap, fixtures, opts)
        r = s["picks"][s["picks"]["week"] == GW]
        return int(r.loc[r["captain"] == 1, "id"].iloc[0])

    assert captain(0.0) == cap
    assert captain(0.1) == other


# --- S1b: offline run on a saved real team (rank 1 overall, before the GW6 deadline) with ep_next -----

FIXTURE = Path(__file__).parent / "fixtures" / "gw6_live"


def _gw6():
    with gzip.open(FIXTURE / "bootstrap-static.json.gz", "rt", encoding="utf-8") as f:
        bootstrap = json.load(f)
    with gzip.open(FIXTURE / "fixtures.json.gz", "rt", encoding="utf-8") as f:
        fixtures = json.load(f)
    return json.loads((FIXTURE / "my_data.json").read_text()), bootstrap, fixtures


def test_ep_next_projections_follow_fixture_counts():
    from fplrank.data.projections import from_ep_next

    _, bootstrap, fixtures = _gw6()
    proj = from_ep_next(bootstrap, fixtures, horizon=4)
    assert [c for c in proj.columns if c.endswith("_Pts")] == ["6_Pts", "7_Pts", "8_Pts", "9_Pts"]
    assert len(proj) == len(bootstrap["elements"]) and proj["ID"].is_unique
    raya = proj.set_index("ID").loc[1]
    assert raya["6_Pts"] == pytest.approx(float(next(e["ep_next"] for e in bootstrap["elements"] if e["id"] == 1)))


@pytest.mark.slow
def test_s1_runs_offline_on_a_real_team_with_ep_next():
    from fplrank.baseline import solve_ev
    from fplrank.data.projections import from_ep_next

    my_data, bootstrap, fixtures = _gw6()
    proj = from_ep_next(bootstrap, fixtures, horizon=4)
    opts = {"horizon": 4, "secs": 120, "gap": 0}
    ev = solve_ev(my_data, proj, bootstrap, fixtures, opts)[0]
    eo = pd.Series({e["id"]: 1.5 for e in bootstrap["elements"][:40]})
    s0 = ow.solve_with_ownership(my_data, proj, eo, 0.0, bootstrap, fixtures, opts)
    assert ow.plan_key(s0) == ow.plan_key(ev)


def test_solio_eo_matches_names_and_varies_by_gw(tmp_path):
    bootstrap = {
        "teams": [{"id": 1, "short_name": "CHE"}, {"id": 2, "short_name": "MCI"}],
        "elements": [{"id": 165, "web_name": "João Pedro", "team": 1}, {"id": 411, "web_name": "Haaland", "team": 2}],
    }
    path = tmp_path / "eo.csv"
    rows = [
        "Name,Team,Price,Avg EO %,GW6 EO %,GW7 EO %",
        '"Haaland",MCI,15.6,150,147,166',
        '"Joao Pedro",CHE,7.7,70,69,71',
        '"Nobody",ARS,4,0,0,0',
    ]
    path.write_text("\ufeff" + "\n".join(rows) + "\n", encoding="utf-8")
    eo = ow.load_solio_eo(bootstrap, path)
    assert eo.loc[411, 7] == pytest.approx(1.66) and eo.loc[165, 6] == pytest.approx(0.69) and len(eo) == 2
    proj = pd.DataFrame({"ID": [411, 165], "6_Pts": [6.0, 4.0], "7_Pts": [6.0, 4.0], "8_Pts": [6.0, 4.0]})
    adj = ow.adjust_projections(proj, eo, 0.1)
    assert adj.loc[0, "6_Pts"] == pytest.approx(6 * (1 + 0.1 * 0.47))
    assert adj.loc[0, "7_Pts"] == pytest.approx(6 * (1 + 0.1 * 0.66))
    assert adj.loc[0, "8_Pts"] == adj.loc[0, "7_Pts"]  # beyond the forecast: last GW reused
