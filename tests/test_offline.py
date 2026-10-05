import pandas as pd

from fplrank.data import offline


def _players():
    return pd.DataFrame(
        [
            {
                "id": 1,
                "code": 101,
                "web_name": "Keeper",
                "element_type": 1,
                "team": 1,
                "now_cost": 45,
                "minutes": 90,
                "status": "a",
                "chance_of_playing_next_round": float("nan"),
            },
            {
                "id": 2,
                "code": 102,
                "web_name": "Striker",
                "element_type": 4,
                "team": 2,
                "now_cost": 90,
                "minutes": 45,
                "status": "d",
                "chance_of_playing_next_round": 50.0,
            },
            {
                "id": 3,
                "code": 103,
                "web_name": "Injured",
                "element_type": 3,
                "team": 2,
                "now_cost": 60,
                "minutes": 0,
                "status": "i",
                "chance_of_playing_next_round": float("nan"),
            },
        ]
    )


def _teams():
    return pd.DataFrame([{"id": 1, "name": "Alpha", "code": 1}, {"id": 2, "name": "Beta", "code": 2}])


def _fixtures():
    return pd.DataFrame(
        [
            {"id": 1, "event": 2, "team_h": 1, "team_a": 2, "team_h_difficulty": 2, "team_a_difficulty": 4, "finished": False},
            {"id": 2, "event": 3, "team_h": 2, "team_a": 1, "team_h_difficulty": 3, "team_a_difficulty": 3, "finished": False},
            {"id": 3, "event": 3, "team_h": 1, "team_a": 2, "team_h_difficulty": 3, "team_a_difficulty": 3, "finished": False},
        ]
    )


def test_bootstrap_marks_next_gw_and_has_element_types():
    boot = offline.build_bootstrap(_players(), _teams(), next_gw=2)
    assert [e["id"] for e in boot["events"] if e["is_next"]] == [2]
    assert {t["singular_name_short"][0] for t in boot["element_types"]} == {"G", "D", "M", "F"}
    assert boot["elements"][0]["chance_of_playing_next_round"] is None  # NaN cleaned


def test_placeholder_projections_shape_and_logic():
    fixtures = offline.build_fixtures(_fixtures())
    proj = offline.placeholder_projections(_players(), _teams(), fixtures, gws=[2, 3], games_played=1)
    assert list(proj.columns[:5]) == ["ID", "Name", "Pos", "Value", "Team"]
    assert {"2_Pts", "2_xMins", "3_Pts", "3_xMins"} <= set(proj.columns)
    by_id = proj.set_index("ID")
    assert by_id.loc[3, "2_Pts"] == 0  # injured
    assert by_id.loc[1, "3_xMins"] == 2 * by_id.loc[1, "2_xMins"]  # double gameweek
    assert by_id.loc[2, "2_xMins"] < by_id.loc[1, "2_xMins"]  # doubtful and half the minutes
