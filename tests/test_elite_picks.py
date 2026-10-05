import math
from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest
import requests

from fplrank.collect import elite_picks
from fplrank.data.fpl_api import FplApi, snapshot_folder

NOW = datetime.now(UTC)  # snapshot files are stamped with the real time, so the test clock must match


def _picks(captain, chip=None, players=range(1, 16)):
    return {
        "active_chip": chip,
        "automatic_subs": [],
        "entry_history": {},
        "picks": [
            {"element": p, "position": i, "multiplier": 0, "is_captain": p == captain, "is_vice_captain": False, "element_type": 1}
            for i, p in enumerate(players, 1)
        ],
    }


def _history(gws, chips=(), past=()):
    current = [
        {"event": gw, "points": 50, "total_points": 50 * gw, "rank": 1, "overall_rank": 10 * gw, "event_transfers_cost": 0} for gw in gws
    ]
    return {"current": current, "past": list(past), "chips": [{"name": c, "event": gw, "time": "t"} for gw, c in chips]}


# Three managers: 101 plays GW1-2 (Bench Boost GW1), 102 joined in GW2 (Triple Captain on 2), 103 is not found
PAYLOADS = {
    "bootstrap-static/": {
        "events": [
            {"id": 1, "deadline_time": "2026-08-15T10:00:00Z", "finished": True},
            {"id": 2, "deadline_time": "2026-08-22T10:00:00Z", "finished": True},
            {"id": 3, "deadline_time": (NOW + timedelta(days=5)).isoformat(), "finished": False},  # not started
        ]
    },
    "fixtures/": [],
    "leagues-classic/314/standings/?page_standings=1": {
        "standings": {
            "has_next": False,
            "results": [
                {"entry": e, "rank": 1 if r < 3 else 3, "rank_sort": r, "total": 300 - r} for r, e in enumerate([101, 102, 103], 1)
            ],
        }
    },
    "entry/101/history/": _history([1, 2], chips=[(1, "bboost")], past=[{"season_name": "2025/26", "total_points": 2600, "rank": 5000}]),
    "entry/101/transfers/": [
        {"element_in": 16, "element_in_cost": 50, "element_out": 15, "element_out_cost": 45, "entry": 101, "event": 2, "time": "t"}
    ],
    "entry/101/event/1/picks/": _picks(captain=1, chip="bboost"),
    "entry/101/event/2/picks/": _picks(captain=1, players=[*range(1, 15), 16]),
    "entry/102/history/": _history([2], chips=[(2, "3xc")]),
    "entry/102/transfers/": [],
    "entry/102/event/2/picks/": _picks(captain=2, chip="3xc"),
    "event/1/live/": {},
    "event/2/live/": {},
}


class FakeApi(FplApi):
    def __init__(self, snapshot_dir):
        super().__init__(snapshot_dir=snapshot_dir, session=requests.Session())
        self.calls = []

    def get(self, endpoint, save=True):
        self.calls.append(endpoint)
        if endpoint not in PAYLOADS:
            raise requests.HTTPError(f"404 for {endpoint}")
        self._save(endpoint, PAYLOADS[endpoint])
        return PAYLOADS[endpoint]


@pytest.fixture
def collected(tmp_path):
    api = FakeApi(tmp_path / "snapshots")
    collector = elite_picks.Collector(api=api, snapshot_dir=tmp_path / "snapshots", out_dir=tmp_path / "out", now=NOW, log=lambda *_: None)
    config = {"season": "2026-27", "overall_top": [3], "named_lists": {"pair": [101, 102]}, "threshold_ranks": [2]}
    return collector, config, collector.collect(config)


def test_collect_fetches_played_gws_only_and_reports_failures(collected):
    collector, _, summary = collected
    assert summary["gws"] == [1, 2] and summary["failed"] == [103]
    assert "entry/102/event/1/picks/" not in collector.api.calls  # joined in GW2
    assert not any("event/3" in c for c in collector.api.calls)  # GW3 deadline not passed


def test_tables(collected):
    collector, _, _ = collected
    out = collector.out_dir
    picks = pd.read_parquet(out / "picks.parquet")
    assert len(picks) == 3 * 15 and {"season", "gw", "entry_id", "fpl_id", "position", "is_captain", "active_chip"} <= set(picks.columns)
    chips = pd.read_parquet(out / "chips.parquet")
    assert set(zip(chips["entry_id"], chips["gw"], chips["chip"], strict=True)) == {(101, 1, "bboost"), (102, 2, "3xc")}
    transfers = pd.read_parquet(out / "transfers.parquet")
    assert transfers[["entry_id", "gw", "element_in", "element_out"]].values.tolist() == [[101, 2, 16, 15]]
    ranks = pd.read_parquet(out / "ranks.parquet")
    assert ranks.set_index(["entry_id", "gw"])["overall_rank"].to_dict() == {(101, 1): 10, (101, 2): 20, (102, 2): 20}
    members = pd.read_parquet(out / "members.parquet")
    assert members.groupby("set")["entry_id"].apply(list).to_dict() == {"pair": [101, 102], "top3": [101, 102, 103]}


def test_eo_is_deadline_eo(collected):
    collector, _, _ = collected
    eo = pd.read_parquet(collector.out_dir / "eo.parquet")
    assert list(eo.columns) == ["season", "gw", "group", "fpl_id", "eo", "n_managers"]
    eo = eo.set_index(["group", "gw", "fpl_id"])
    # GW1: only 101, on Bench Boost: captain 2, every other pick (bench included) 1
    assert eo.loc[("top3", 1, 1), "eo"] == 2 and eo.loc[("top3", 1, 15), "eo"] == 1 and eo.loc[("top3", 1, 1), "n_managers"] == 1
    # GW2: 101 (captain 1, bench not counted) and 102 (Triple Captain on 2)
    assert eo.loc[("top3", 2, 1), "eo"] == (2 + 1) / 2
    assert eo.loc[("top3", 2, 2), "eo"] == (1 + 3) / 2
    assert eo.loc[("top3", 2, 11), "eo"] == 1.0
    # Players 12-16 sit on both GW2 benches and nobody played Bench Boost: zero EO, so no row
    assert not any(("top3", 2, p) in eo.index for p in (12, 13, 14, 15, 16))


def test_rerun_resumes_without_redownloading(collected, tmp_path):
    collector, config, _ = collected
    collector.api.calls.clear()
    collector.collect(config)
    assert collector.api.calls == ["entry/103/history/"]  # only the earlier failure is retried
    collector.now = NOW + timedelta(hours=13)  # standings/history/transfers are stale, picks never are
    collector.collect(config)
    assert not any("picks" in c for c in collector.api.calls)
    assert "entry/101/history/" in collector.api.calls


def test_snapshot_folder_is_windows_safe(tmp_path):
    folder = snapshot_folder("leagues-classic/314/standings/?page_standings=2", tmp_path)
    assert folder.name == "leagues-classic__314__standings____page_standings-2"
    assert not set('?<>:"|*') & set(folder.name)


def test_load_config(tmp_path):
    path = tmp_path / "sets.toml"
    path.write_text('season = "2026-27"\noverall_top = [1000, 10000]\n[named_lists]\nelite = [1, 2]\n')
    assert elite_picks.load_config(path) == {
        "season": "2026-27",
        "overall_top": [1000, 10000],
        "named_lists": {"elite": [1, 2]},
        "threshold_ranks": [],
    }
    assert elite_picks.load_config()["season"] == "2026-27"  # the committed config parses


def test_past_seasons_and_thresholds(collected):
    collector, _, _ = collected
    past = pd.read_parquet(collector.out_dir / "past_seasons.parquet")
    assert past.to_dict("records") == [{"season": "2025-26", "entry_id": 101, "total_points": 2600, "rank": 5000}]
    thresholds = pd.read_parquet(collector.out_dir / "thresholds.parquet")
    row = thresholds.iloc[0]
    assert len(thresholds) == 1 and (row["gw"], row["target_rank"], row["rank"], row["total_points"]) == (2, 2, 1, 298)  # tied rank 1


def test_season_cutoffs_interpolates_in_log_rank_and_never_extrapolates():
    past = pd.DataFrame({"season": "2025-26", "entry_id": range(3), "rank": [500, 5_000, 50_000], "total_points": [2700, 2500, 2300]})
    cut = elite_picks.season_cutoffs(past, ranks=(100, 1_000, 5_000, 10_000, 100_000)).set_index("target_rank")
    assert pd.isna(cut.loc[100, "points"]) and cut.loc[100, "above_rank"] == 500  # better than anyone sampled
    assert pd.isna(cut.loc[100_000, "points"])
    assert cut.loc[5_000, "points"] == 2500  # exact hit
    assert cut.loc[1_000, "points"] == pytest.approx(2700 - 200 * math.log(2) / math.log(10))
    assert (cut.loc[10_000, "below_rank"], cut.loc[10_000, "above_rank"]) == (5_000, 50_000)
