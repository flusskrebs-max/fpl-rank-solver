"""Checks on the committed elite ownership datasets (ported from the Cowork build.py) and the loaders."""

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
    meta = elite.load_meta(source, season)
    chips = meta[meta["table"] == "chip_active"].pivot_table(index=["group", "gw"], columns="item", values="count") / GROUP_SIZE[source]
    # Starting XI + captain + extra for Triple Captain + bench on Bench Boost, as fractions of a manager
    full = 11 + 1 + chips["TC"] + 4 * chips["BB"]
    coverage = eo.groupby(["group", "gw"])["eo"].sum() / full
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


def _toy_eo():
    rows = [
        (1, "A", 10, "Ten", 0.5),
        (1, "B", 10, "Ten", 0.0),  # listed zero is observed, not censored
        (2, "A", 20, "Twenty", 1.2),
        (2, "B", 20, "Twenty", 0.3),
    ]
    df = pd.DataFrame(rows, columns=["gw", "group", "fpl_id", "player", "eo"])
    return df.assign(season="2099-00", team="XXX", pos="M", fpl_id=df["fpl_id"].astype("Int64"))


def test_eo_panel_fills_censored_with_floor():
    panel = elite.eo_panel(eo=_toy_eo(), floor=0.01)
    assert len(panel) == 2 * 2 * 2  # groups x gws x players, complete
    cell = panel.set_index(["group", "gw", "fpl_id"])
    assert cell.loc[("A", 1, 10), "eo"] == 0.5 and not cell.loc[("A", 1, 10), "censored"]
    assert cell.loc[("B", 1, 10), "eo"] == 0.0 and not cell.loc[("B", 1, 10), "censored"]
    assert cell.loc[("A", 1, 20), "eo"] == 0.01 and cell.loc[("A", 1, 20), "censored"]
    assert cell.loc[("A", 1, 20), "player"] == "Twenty"  # names filled for censored cells


def test_eo_panel_selection_and_unknown_players():
    panel = elite.eo_panel(groups=["A"], gws=[2], players=[20, 99], eo=_toy_eo())
    assert panel["fpl_id"].tolist() == [20, 99]
    assert panel["censored"].tolist() == [False, True]
    assert panel["eo"].tolist() == [1.2, 0.025]  # default floor
    assert pd.isna(panel["player"].iloc[1])


@pytest.mark.parametrize("bad", [{"groups": ["C"]}, {"gws": [3]}])
def test_eo_panel_rejects_groups_and_gws_not_in_data(bad):
    with pytest.raises(ValueError):
        elite.eo_panel(eo=_toy_eo(), **bad)


def test_eo_panel_on_real_data():
    panel = elite.eo_panel()
    eo = elite.load_eo()
    assert len(panel) == 2 * eo["gw"].nunique() * eo["fpl_id"].nunique()
    assert (~panel["censored"]).sum() == len(eo)
    assert (panel.loc[panel["censored"], "eo"] == 0.025).all()
