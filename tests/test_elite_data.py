"""Checks on the committed elite ownership datasets (ported from the Cowork build.py) and the loaders."""

import numpy as np
import pandas as pd
import pytest

from fplrank.data import elite

# Managers per group, by source. Add an entry when a new source is added to datasets/elite_ownership/.
GROUP_SIZE = {"elite64": 64}
# Meta tables where every manager falls in exactly one row per GW
PARTITION_TABLES = ["captain", "chip_active", "fts_used", "fts_remaining_next", "hits"]
CHIPS = ["WC", "FH", "TC", "BB"]

DATASETS = elite.available()


def test_datasets_found():
    assert ("elite64", "2026-27") in DATASETS


@pytest.mark.parametrize(("source", "season"), DATASETS)
def test_partition_tables_sum_to_group_size(source, season):
    meta = elite.load_meta(source, season)
    sums = meta[meta["table"].isin(PARTITION_TABLES)].groupby(["table", "group", "gw"])["count"].sum()
    assert (sums == GROUP_SIZE[source]).all(), sums[sums != GROUP_SIZE[source]].to_string()


@pytest.mark.parametrize(("source", "season"), DATASETS)
def test_chips_remaining_consistent_with_usage(source, season):
    # Holds within one chip set; revisit when the second-half chips appear in the data
    meta = elite.load_meta(source, season)
    used = meta[meta["table"] == "chip_active"].pivot_table(index="gw", columns=["group", "item"], values="count")
    left = meta[meta["table"] == "chips_remaining"].pivot_table(index="gw", columns=["group", "item"], values="count")
    for group in meta["group"].unique():
        for chip in CHIPS:
            expected = GROUP_SIZE[source] - used[(group, chip)].sort_index().cumsum()
            pd.testing.assert_series_equal(left[(group, chip)].sort_index(), expected, check_names=False, check_dtype=False)


@pytest.mark.parametrize(("source", "season"), DATASETS)
def test_every_row_has_unique_fpl_id(source, season):
    eo = elite.load_eo(source, season)
    assert eo["fpl_id"].notna().all(), eo[eo["fpl_id"].isna()]
    assert not eo.duplicated(["group", "gw", "fpl_id"]).any()


@pytest.mark.parametrize(("source", "season"), DATASETS)
def test_listed_eo_covers_most_of_group_total(source, season):
    eo = elite.load_eo(source, season)
    coverage = eo.groupby(["group", "gw"])["eo"].sum() / elite.expected_totals(elite.load_meta(source, season))
    assert coverage.between(0.85, 1.0).all(), coverage.round(3).to_string()


def test_load_eo_long_shape():
    eo = elite.load_eo()
    assert list(eo.columns) == ["season", "gw", "group", "fpl_id", "player", "team", "pos", "eo"]
    assert set(eo["group"]) == {"AE64", "E64"}
    assert eo["eo"].between(0, 3).all()  # fractions, 3.0 = everyone triple-captained
    row = eo[(eo["gw"] == 1) & (eo["player"] == "Raya")].set_index("group")["eo"]
    assert row.to_dict() == {"AE64": 0.59, "E64": 0.19}


def test_load_meta_long_shape():
    meta = elite.load_meta()
    assert list(meta.columns) == ["season", "gw", "group", "table", "item", "count"]
    assert "none" in set(meta.loc[meta["table"] == "chip_active", "item"])
    assert meta["item"].map(type).eq(str).all()


def test_expected_totals():
    totals = elite.expected_totals(elite.load_meta())
    assert totals[("AE64", 1)] == 12 + 4 * 48 / 64  # GW1: 48 of 64 on Bench Boost
    assert totals[("E64", 3)] == 12 + 28 / 64  # GW3: 28 Triple Captains
    assert elite.expected_total_eo("AE64", 1) == totals[("AE64", 1)]


def test_water_fill_is_proportional_capped_and_redistributes():
    fill = elite._water_fill(1.0, np.array([3.0, 1.0, 0.0]), np.array([1.0, 1.0, 1.0]))
    np.testing.assert_allclose(fill, [0.75, 0.25, 0.0])
    fill = elite._water_fill(1.0, np.array([9.0, 1.0, 0.0]), np.array([0.5, 1.0, 1.0]))
    np.testing.assert_allclose(fill, [0.5, 0.5, 0.0])  # capped excess goes to the other owned player
    fill = elite._water_fill(1.0, np.array([0.0, 0.0]), np.array([1.0, 1.0]))
    np.testing.assert_allclose(fill, [0.5, 0.5])  # no ownership at all: even split
    fill = elite._water_fill(5.0, np.array([1.0, 1.0]), np.array([1.0, 2.0]))
    np.testing.assert_allclose(fill, [1.0, 2.0])  # not enough room: everyone at their cap


def _toy():
    """Two groups, two GWs; listed EO sums to 11.5 against an expected 12 (no chips)."""
    listed = {1: 5.5, 2: 4.0, 3: 1.9, 4: 0.1, 5: 0.0}  # id 5 is a listed zero
    eo = pd.DataFrame(
        [(gw, g, pid, f"P{pid}", eo) for gw in (1, 2) for g in ("A", "B") for pid, eo in listed.items()],
        columns=["gw", "group", "fpl_id", "player", "eo"],
    ).assign(season="2099-00", team="XXX", pos="M")
    eo["fpl_id"] = eo["fpl_id"].astype("Int64")
    meta = pd.DataFrame(
        [("2099-00", gw, g, "chip_active", "none", 4) for gw in (1, 2) for g in ("A", "B")],
        columns=["season", "gw", "group", "table", "item", "count"],
    )
    # Unlisted: id 10 owned by most of the game, ids 11-19 by few, id 20 by nobody, id 21 unknown
    own = {10: 0.9, **dict.fromkeys(range(11, 20), 0.01), 20: 0.0, 21: float("nan")}
    universe = pd.DataFrame({"fpl_id": list(own), "pos": "M", "ownership": list(own.values())})
    return eo, meta, universe


def test_eo_panel_residual_fill():
    eo, meta, universe = _toy()
    panel = elite.eo_panel(eo=eo, meta=meta, universe=universe)
    assert len(panel) == 2 * 2 * (5 + 12)  # groups x gws x (listed + universe), complete
    sums = panel.groupby(["group", "gw"])["eo"].sum()
    np.testing.assert_allclose(sums, 12.0)
    cell = panel.set_index(["group", "gw", "fpl_id"])
    assert cell.loc[("A", 1, 1), "eo"] == 5.5 and cell.loc[("A", 1, 1), "fill_method"] == "listed"
    assert cell.loc[("A", 1, 5), "eo"] == 0.0 and not cell.loc[("A", 1, 5), "censored"]  # listed zero kept
    assert cell.loc[("A", 1, 10), "eo"] == pytest.approx(0.1)  # capped at the smallest positive listed EO
    assert cell.loc[("A", 1, 20), "eo"] == 0.0  # zero ownership gets nothing while others have room
    assert cell.loc[("A", 1, 21), "eo"] > 0  # unknown ownership gets the mean
    assert (panel.loc[panel["censored"], "fill_method"] == "residual").all()
    assert panel.loc[panel["censored"], "eo"].max() <= 0.1 + 1e-12


def test_eo_panel_player_filter_keeps_full_fill():
    eo, meta, universe = _toy()
    full = elite.eo_panel(eo=eo, meta=meta, universe=universe).set_index(["group", "gw", "fpl_id"])["eo"]
    some = elite.eo_panel(groups=["A"], gws=[2], players=[1, 12], eo=eo, meta=meta, universe=universe)
    assert some["fpl_id"].tolist() == [1, 12]
    assert some["eo"].tolist() == [full[("A", 2, 1)], full[("A", 2, 12)]]


@pytest.mark.parametrize("bad", [{"groups": ["C"]}, {"gws": [3]}, {"players": [99]}])
def test_eo_panel_rejects_unknown_groups_gws_and_players(bad):
    eo, meta, universe = _toy()
    with pytest.raises(ValueError):
        elite.eo_panel(eo=eo, meta=meta, universe=universe, **bad)


def _check_real_panel(panel):
    eo = elite.load_eo()
    totals = elite.expected_totals(elite.load_meta())
    sums = panel.groupby(["group", "gw"])["eo"].sum()
    assert ((sums / totals.loc[sums.index] - 1).abs() < 0.01).all(), (sums / totals).round(4).to_string()
    # Listed values unchanged
    merged = eo.merge(panel, on=["group", "gw", "fpl_id"], suffixes=("", "_panel"))
    assert len(merged) == len(eo) and (merged["eo"] == merged["eo_panel"]).all()
    # No unlisted value above the listing cutoff for its position/group/GW
    cutoff = eo[eo["eo"] > 0].groupby(["group", "gw", "pos"])["eo"].min().rename("cutoff")
    filled = panel[panel["censored"]].join(cutoff, on=["group", "gw", "pos"])
    assert (filled["eo"] <= filled["cutoff"] + 1e-12).all()


def test_eo_panel_on_real_data_with_synthetic_universe():
    # Runs anywhere (no FPL snapshot needed): listed players plus 600 made-up ones
    rng = np.random.default_rng(0)
    fake = pd.DataFrame({"fpl_id": range(10_001, 10_601), "pos": rng.choice(list("GDMF"), 600), "ownership": rng.exponential(0.02, 600)})
    _check_real_panel(elite.eo_panel(universe=fake))


def test_eo_panel_on_real_data_with_fpl_snapshot():
    try:
        universe = elite._default_universe()
    except FileNotFoundError:
        pytest.skip("no bootstrap-static snapshot saved on this machine")
    panel = elite.eo_panel(universe=universe)
    _check_real_panel(panel)
    assert panel["fpl_id"].nunique() == len(universe)
