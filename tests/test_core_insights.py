"""D1: FPL-Core-Insights playerstats loader."""

import pandas as pd
import pytest

from fplrank.data import core_insights as ci


def _raw():
    return pd.DataFrame(
        {
            "id": [7, 8, 7, 7],
            "gw": [1, 1, 2, 2],
            "status": ["a", "d", "a", "a"],
            "now_cost": ["5.8", "4.5", "5.8", "5.9"],
            "selected_by_percent": ["14.9", "1.0", "15.2", "15.3"],
            "transfers_in_event": [100, None, 50, 60],
            "transfers_out_event": [10, 0, 5, 6],
            "ep_next": ["4.3", None, "5.0", "5.1"],
            "ep_this": ["4.0", "1.0", "4.3", "4.3"],
            "web_name": ["A", "B", "A", "A"],
        }
    )


def test_tidy_keeps_latest_row_and_types():
    df = ci.tidy_playerstats(_raw())
    assert list(df.columns) == ci.COLUMNS and len(df) == 3
    row = df[(df["gw"] == 2) & (df["fpl_id"] == 7)].iloc[0]
    assert row["ep_next"] == pytest.approx(5.1) and row["now_cost"] == pytest.approx(5.9)
    assert df["transfers_in_event"].dtype == "int64"


def test_xp_from_ep_next_uses_same_gw_row():
    xp = ci.xp_from_ep_next("2025-26", ci.tidy_playerstats(_raw()))
    assert xp.set_index(["gw", "fpl_id"])["xp"].to_dict() == {(1, 7): 4.3, (2, 7): 5.1}


def test_season_folder_name():
    assert ci._season_dir("2025-26") == "2025-2026"


@pytest.mark.network
def test_download_2026_27():
    df = ci.playerstats("2026-27")
    assert df["gw"].min() == 1 and df["fpl_id"].is_unique is False and df["ep_next"].notna().any()
