"""S1 ownership weighting: projection adjustment, plan scoring and the EO loaders. Real solves are in test_cli."""

import gzip
import json
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


# --- S1b: FPL ep_next as projections, on the saved GW6 payloads -----------------------------------

FIXTURE = Path(__file__).parent / "fixtures" / "gw6_live"


def _gw6():
    with gzip.open(FIXTURE / "bootstrap-static.json.gz", "rt", encoding="utf-8") as f:
        bootstrap = json.load(f)
    with gzip.open(FIXTURE / "fixtures.json.gz", "rt", encoding="utf-8") as f:
        fixtures = json.load(f)
    return bootstrap, fixtures


def test_ep_next_projections_follow_fixture_counts():
    from fplrank.data.projections import from_ep_next

    bootstrap, fixtures = _gw6()
    proj = from_ep_next(bootstrap, fixtures, horizon=4)
    assert [c for c in proj.columns if c.endswith("_Pts")] == ["6_Pts", "7_Pts", "8_Pts", "9_Pts"]
    assert len(proj) == len(bootstrap["elements"]) and proj["ID"].is_unique
    raya = proj.set_index("ID").loc[1]
    assert raya["6_Pts"] == pytest.approx(float(next(e["ep_next"] for e in bootstrap["elements"] if e["id"] == 1)))


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


# --- S1c: λ on the next GW only ------------------------------------------------------------------


def test_lam_gw_scales_only_that_gw():
    proj, eo = _proj(), pd.Series({1: 1.0, 2: 1.6})
    adj = ow.adjust_projections(proj, eo, 0.2, lam_gw=6)
    assert list(adj["6_Pts"]) == pytest.approx([6.0, 4.0 * 1.12, 2.0 * 0.8])
    assert list(adj["7_Pts"]) == list(proj["7_Pts"])
    pd.testing.assert_frame_equal(ow.adjust_projections(proj, eo, 0.2, lam_gw=None), ow.adjust_projections(proj, eo, 0.2))


def _picks():
    """Three managers, two players each in the XI (1 captain) plus player 9 on the bench."""
    rows = []
    for entry, gw, chip, cap, xi in [
        (1, 5, None, 1, (1, 2)),
        (2, 5, "3xc", 2, (1, 2)),  # TC counts as a normal captain
        (3, 4, None, 1, (1, 3)),  # the squad manager 3 returns to after the free hit
        (3, 5, "freehit", 4, (4, 5)),
        (1, 6, "bboost", 1, (1, 2)),  # bench boost: bench still counts 0
    ]:
        for pos, pid in enumerate(xi, 1):
            rows.append((entry, gw, pid, pos, int(pid == cap), chip))
        rows.append((entry, gw, 9, 12, 0, chip))
    return pd.DataFrame(rows, columns=["entry_id", "gw", "fpl_id", "position", "is_captain", "active_chip"])


def test_chip_free_eo_drops_tc_bb_and_free_hit():
    members = pd.DataFrame({"set": "AE64", "entry_id": [1, 2, 3]})
    eo = ow.chip_free_eo(_picks(), members, "AE64").set_index(["gw", "fpl_id"])["eo"]
    # GW5: manager 3 counts with their GW4 squad (1 C, 3), not the free hit
    assert eo[5].to_dict() == pytest.approx({1: 5 / 3, 2: 1.0, 3: 1 / 3})
    assert eo[6].to_dict() == {1: 2.0, 2: 1.0}


def test_elite_is_the_mix_of_ae64_and_e64(tmp_path, monkeypatch):
    members = pd.DataFrame({"set": ["AE64", "AE64", "E64", "top10k"], "entry_id": [1, 2, 3, 3]})
    members.to_parquet(tmp_path / "members.parquet")
    picks = _picks()
    picks[picks["gw"] == 5].to_parquet(tmp_path / "picks.parquet")
    # E64 (manager 3) only has a free hit at GW5 and no earlier squad, so falls back to the graphics
    monkeypatch.setattr("fplrank.data.elite.load_eo", lambda *a: pd.DataFrame({"gw": [5], "group": ["E64"], "fpl_id": [7], "eo": [0.5]}))
    eo, gw = ow.load_eo("elite", 5, collected_dir=tmp_path)
    assert gw == 5 and eo.to_dict() == pytest.approx({1: 0.75, 2: 0.75, 7: 0.25})
    assert ow.group_weights("elite", 0.4) == pytest.approx({"AE64": 0.3, "E64": 0.3, "top10k": 0.4})
    assert ow.group_weights("elite") == {"AE64": 0.5, "E64": 0.5}  # the live blend is off by default
    assert ow.drift_group("elite") == "elite"


def test_rank_goal_table_moves_a_stale_line_on_by_its_pace(monkeypatch):
    """Our points are after GW5; a line last collected after GW3 is moved on two GWs at its pace."""
    from fplrank.model import variance
    from fplrank.opt import rank_goal
    from fplrank.rank import target

    monkeypatch.setattr(target, "target_line", lambda rank: target.TargetLine(rank, 3, 200, 60, 200 + 35 * 60, float("nan"), ("x",)))
    monkeypatch.setattr(target, "line_drift", lambda rank, group: (0.0, None))
    monkeypatch.setattr(variance, "build", lambda: None)
    monkeypatch.setattr(rank_goal, "plan_moments", lambda *a, **k: rank_goal.Moments(0.0, 100.0, 1))
    solutions = {0.0: {"ev": 50.0}, 0.1: {"ev": 49.0}}
    table, text = ow.rank_goal_table(solutions, None, None, 6, 10000, 300, "AE64")
    assert "line 320 after GW5 (GW3 line moved on 2 GW at 60 a GW)" in text
    assert "gap to close 20" in text
    assert table["p"].notna().all()  # one season of cut-offs (sd NaN) still gives a probability


def test_repick_eo_mixes_the_elite_groups_on_next_gw_xp(tmp_path):
    pos = [1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4]
    rows = [
        (entry, 5, pid, i, int(i == 3), pos[i - 1], None)
        for entry, ids in ((1, range(1, 16)), (2, range(101, 116)))
        for i, pid in enumerate(ids, 1)
    ]
    cols = ["entry_id", "gw", "fpl_id", "position", "is_captain", "element_type", "active_chip"]
    pd.DataFrame(rows, columns=cols).to_parquet(tmp_path / "picks.parquet")
    pd.DataFrame({"set": ["AE64", "E64"], "entry_id": [1, 2]}).to_parquet(tmp_path / "members.parquet")
    xp = pd.Series(1.0, index=[*range(1, 16), *range(101, 116)])
    xp[[13, 113]] = 8.0
    eo, gw = ow.repick_eo("elite", 6, xp, collected_dir=tmp_path)
    assert gw == 5 and eo.sum() == pytest.approx(12)  # each group's one manager, half weight each
    assert eo[13] == pytest.approx(1.0) and eo[113] == pytest.approx(1.0)  # captain x2, x 0.5
    with pytest.raises(ValueError):
        ow.repick_eo("elite", 5, xp, collected_dir=tmp_path)  # no picks before GW5
