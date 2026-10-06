"""S2a target line on synthetic thresholds and cut-offs."""

import math

import pandas as pd
import pytest

from fplrank.rank import target as tg


def _thresholds():
    rows = [("2026-10-05T10:00:00+00:00", 4, 1000, 300), ("2026-10-05T10:00:00+00:00", 5, 1000, 380)]
    rows += [("2026-10-06T10:00:00+00:00", 5, 1000, 400), ("2026-10-06T10:00:00+00:00", 5, 100_000, 360)]
    return pd.DataFrame(rows, columns=["collected_at", "gw", "target_rank", "total_points"])


def _cutoffs():
    rows = [("2023-24", 1000, 2660), ("2023-24", 100_000, 2470), ("2024-25", 1000, 2698), ("2024-25", 100_000, 2508)]
    rows += [("2025-26", 1000, 2470), ("2025-26", 100_000, 2280), ("2025-26", 100, 2510)]
    return pd.DataFrame(rows, columns=["season", "target_rank", "points"])


def test_line_now_uses_latest_snapshot_and_log_rank():
    assert tg.line_now(_thresholds(), 1000) == (400, 5)
    assert tg.line_now(_thresholds(), 1000, gw=4) == (300, 4)
    assert tg.line_now(_thresholds(), 10_000)[0] == pytest.approx(380)  # halfway in log rank
    with pytest.raises(ValueError):
        tg.line_now(_thresholds(), 100)  # no extrapolation


def test_season_paces_skip_seasons_that_do_not_bracket_the_rank():
    paces = tg.season_paces(_cutoffs(), 100)
    assert list(paces.index) == ["2025-26"] and paces.iloc[0] == pytest.approx(2510 / 38)
    assert list(tg.season_paces(_cutoffs(), 10_000, n_seasons=2).index) == ["2024-25", "2025-26"]


def test_target_line_projects_with_past_pace():
    line = tg.target_line(1000, thresholds=_thresholds(), cutoffs=_cutoffs())
    paces = [2660 / 38, 2698 / 38, 2470 / 38]
    assert line.gw == 5 and line.now == 400
    assert line.pace == pytest.approx(sum(paces) / 3)
    assert line.final == pytest.approx(400 + 33 * line.pace)
    assert line.sd == pytest.approx(pd.Series(paces).std() * 33)
    assert "Top 1,000: 400 after GW5" in str(line) and not math.isnan(line.sd)


def _ranks():
    rows = []  # entry, gw, points, transfer cost, total, overall rank
    for gw, (a, b) in enumerate([(100, 80), (60, 70), (70, 50), (50, 60)], start=1):
        rows += [(1, gw, a, 0, None, 1_000), (2, gw, b, 4 if gw == 2 else 0, None, 100_000)]
    df = pd.DataFrame(rows, columns=["entry_id", "gw", "points", "event_transfers_cost", "total_points", "overall_rank"])
    df["total_points"] = df.groupby("entry_id")["points"].cumsum() - df.groupby("entry_id")["event_transfers_cost"].cumsum()
    return df


def test_line_drift_against_group():
    ranks, members = _ranks(), pd.DataFrame({"set": ["G", "H"], "entry_id": [1, 2]})
    line = tg.line_history(ranks, 10_000)  # halfway in log rank between the two managers
    assert list(line) == pytest.approx([90, 153, 213, 268])
    drift, table = tg.line_drift(10_000, "H", ranks, members)
    assert list(table["group_points"]) == [66, 50, 60]  # net of the GW2 hit
    assert drift == pytest.approx(((63 - 66) + (60 - 50) + (55 - 60)) / 3)
    assert tg.line_drift(10_000, "H", ranks, members, min_gws=4)[0] == 0.0
