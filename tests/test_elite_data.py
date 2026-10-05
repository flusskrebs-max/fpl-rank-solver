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
SECOND_CHIP_SET_GW = 20  # each manager gets a second set of chips from GW20 (2025-26 rules onwards)

# Known quirks in the source graphics: kept as transcribed, never "fixed". Each entry is the value the
# check sees, so a change to the data (or a new quirk) makes the tests fail and gets looked at.
#   (season, check, table or "transfers", group, gw) -> observed
KNOWN_QUIRKS = {
    ("2025-26", "partition", "captain", "E64", 1): 62,  # GW1 E64 sums to 62
    ("2025-26", "partition", "chip_active", "E64", 1): 62,
    ("2025-26", "partition", "captain", "E64", 2): 63,  # not in the B06 brief's list
    ("2025-26", "partition", "chip_active", "E64", 3): 69,  # "no chip" 62 in the source, should be 57
    ("2025-26", "partition", "fts_remaining_next", "E64", 3): 63,  # not in the B06 brief's list
    ("2025-26", "partition", "captain", "AE64", 38): 62,  # GW38 captains 62/63
    ("2025-26", "partition", "captain", "E64", 38): 63,
    # transfers in = out always; these GWs disagree with sum(k x managers making k transfers)
    ("2025-26", "transfers", "fts_used", "E64", 3): (97, 101),  # (transfers in, sum of k) - not in the brief
    ("2025-26", "transfers", "fts_used", "AE64", 4): (53, 54),  # not in the brief
    ("2025-26", "transfers", "fts_used", "E64", 7): (44, 42),  # not in the brief
    ("2025-26", "transfers", "fts_used", "E64", 25): (71, 67),  # not in the brief
    ("2025-26", "transfers", "fts_used", "AE64", 38): (97, 89),  # GW38 FT table vs transfer lists
    ("2025-26", "transfers", "fts_used", "E64", 38): (122, 99),
    # chips remaining minus (group size - chips played in this chip set); not in the brief, likely
    # a Bench Boost missing from the E64 GW1/GW3 chip tables (those GWs are off already, see above)
    **{("2025-26", "chips", "BB", "E64", gw): -1 for gw in range(13, 19)},
}

DATASETS = elite.available()


def group_size(source, season, group, gw):
    if (source, season, group) == ("elite64", "2025-26", "AE64") and gw >= 29:
        return 63  # one AE64 manager deactivated in GW29
    return GROUP_SIZE[source]


def _quirks(season, check):
    return {k[2:]: v for k, v in KNOWN_QUIRKS.items() if k[0] == season and k[1] == check}


def test_datasets_found():
    assert {("elite64", "2025-26"), ("elite64", "2026-27")} <= set(DATASETS)


@pytest.mark.parametrize(("source", "season"), DATASETS)
def test_partition_tables_sum_to_group_size(source, season):
    meta = elite.load_meta(source, season)
    sums = meta[meta["table"].isin(PARTITION_TABLES)].groupby(["table", "group", "gw"])["count"].sum()
    off = {k: int(v) for k, v in sums.items() if v != group_size(source, season, k[1], k[2])}
    assert off == _quirks(season, "partition")


@pytest.mark.parametrize(("source", "season"), DATASETS)
def test_transfers_in_equal_out_equal_transfers_made(source, season):
    meta = elite.load_meta(source, season)
    moves = meta[meta["table"].isin(["transfer_in", "transfer_out"])].pivot_table(
        index=["group", "gw"], columns="table", values="count", aggfunc="sum", fill_value=0
    )
    used = meta[(meta["table"] == "fts_used") & ~meta["item"].isin(["WC", "FH"])]
    made = (used["item"].astype(int) * used["count"]).groupby([used["group"], used["gw"]]).sum()
    assert (moves["transfer_in"] == moves["transfer_out"]).all()
    made = made.reindex(moves.index, fill_value=0)
    off = {("fts_used", g, gw): (int(n), int(made[(g, gw)])) for (g, gw), n in moves["transfer_in"].items() if n != made[(g, gw)]}
    assert off == _quirks(season, "transfers")


@pytest.mark.parametrize(("source", "season"), DATASETS)
def test_chips_remaining_consistent_with_usage(source, season):
    # remaining = group size - chips played so far in this chip set; a missing chip_active row means 0
    meta = elite.load_meta(source, season)
    used = meta[meta["table"] == "chip_active"].pivot_table(index="gw", columns=["group", "item"], values="count", aggfunc="sum")
    used = used.reindex(range(1, used.index.max() + 1)).fillna(0)
    left = meta[meta["table"] == "chips_remaining"].pivot_table(index="gw", columns=["group", "item"], values="count", aggfunc="sum")
    off = {}
    for group in meta["group"].unique():
        for chip in CHIPS:
            u = used.get((group, chip), pd.Series(0.0, index=used.index))
            chip_set = (u.index >= SECOND_CHIP_SET_GW).astype(int)
            size = pd.Series([group_size(source, season, group, gw) for gw in u.index], index=u.index)
            expected = size - u.groupby(chip_set).cumsum()  # a deactivated manager's chips leave with him
            got = left[(group, chip)].dropna() if (group, chip) in left else pd.Series(dtype=float)
            off |= {(chip, group, int(gw)): int(d) for gw, d in (got - expected.loc[got.index]).items() if d != 0}
    assert off == _quirks(season, "chips")


@pytest.mark.parametrize(("source", "season"), DATASETS)
def test_listed_eo_never_exceeds_expected_total(source, season):
    eo = elite.load_eo(source, season)
    totals = elite.expected_totals(elite.load_meta(source, season))
    listed = eo.groupby(["group", "gw"])["eo"].sum()
    assert (listed <= totals.loc[listed.index] + 1e-9).all()


@pytest.mark.parametrize(("source", "season"), DATASETS)
def test_every_row_has_unique_fpl_id(source, season):
    eo = elite.load_eo(source, season)
    assert eo["fpl_id"].notna().all(), eo[eo["fpl_id"].isna()]
    assert not eo.duplicated(["group", "gw", "fpl_id"]).any()


@pytest.mark.parametrize(("source", "season"), DATASETS)
def test_listed_eo_covers_most_of_group_total(source, season):
    eo = elite.load_eo(source, season)
    listed = eo.groupby(["group", "gw"])["eo"].sum()
    coverage = listed / elite.expected_totals(elite.load_meta(source, season)).loc[listed.index]
    assert coverage.between(0.85, 1.0).all(), coverage.round(3).to_string()


def test_load_eo_long_shape():
    eo = elite.load_eo()
    assert list(eo.columns) == ["season", "gw", "group", "fpl_id", "player", "team", "pos", "eo"]
    assert set(eo["group"]) == {"AE64", "E64"}
    assert eo["eo"].between(0, 3).all()  # fractions, 3.0 = everyone triple-captained
    row = eo[(eo["gw"] == 1) & (eo["player"] == "Raya")].set_index("group")["eo"]
    assert row.to_dict() == {"AE64": 0.59, "E64": 0.19}


@pytest.mark.parametrize("season", ["2025-26", "2026-27"])
def test_load_meta_long_shape(season):
    meta = elite.load_meta(season=season)
    assert list(meta.columns) == ["season", "gw", "group", "table", "item", "count", "fpl_id"]
    assert set(meta.loc[meta["table"] == "chip_active", "item"]) == {"none", "WC", "FH", "TC", "BB"}  # blank / "None" -> "none"
    assert meta["item"].map(type).eq(str).all()
    assert meta.loc[~meta["table"].isin(elite.PLAYER_TABLES), "fpl_id"].isna().all()


def test_elite_meta_maps_every_2025_26_player():
    transfers = elite.elite_meta("2025-26", "transfer_in")
    assert set(transfers["table"]) == {"transfer_in"} and len(transfers) > 0
    for table in ("captain", "transfer_in", "transfer_out", "wc_pick_pct"):
        assert elite.elite_meta("2025-26", table)["fpl_id"].notna().all(), table  # players map covers every name
    tc = elite.elite_meta("2025-26", "captain")
    tc = tc[tc["item"].str.endswith(" (TC)")]
    assert len(tc) and tc["fpl_id"].notna().all()
    with pytest.raises(ValueError):
        elite.elite_meta("2025-26", "no_such_table")


def test_elite_ownership_2025_26():
    own = elite.elite_ownership("2025-26")
    assert list(own.columns) == ["season", "gw", "group", "fpl_id", "player", "pos", "count", "own", "quality"]
    assert own["gw"].min() == 1 and own["gw"].max() == 38 and set(own["group"]) == {"AE64", "E64"}
    assert own["own"].between(-0.01, 1.01).all()  # shares (rebuild rounding allowed)
    per_manager = own.groupby(["group", "gw"])["own"].sum()
    assert per_manager.between(14.9, 15.2).all(), per_manager[~per_manager.between(14.9, 15.2)]  # 15 players each
    # GW1 is exact: the transcribed GW1 squads
    picks = pd.read_csv(elite.ELITE_DIR / "elite64_picks_2025-26.csv", keep_default_na=False).set_index("fpl_id")
    gw1 = own[(own["gw"] == 1) & (own["group"] == "AE64")].set_index("fpl_id")["own"]
    np.testing.assert_allclose(gw1.reindex(picks.index).fillna(0), picks["ae64_own"] / 100, atol=0.006)


@pytest.mark.network
def test_eo_panel_past_season_uses_that_seasons_players():
    # 2025-26 FPL ids differ from 2026-27's, so the universe comes from vaastav's 2025-26 players_raw
    panel = elite.eo_panel("2025-26")
    eo = elite.load_eo(season="2025-26")
    totals = elite.expected_totals(elite.load_meta(season="2025-26"))
    sums = panel.groupby(["group", "gw"])["eo"].sum()
    assert ((sums / totals.loc[sums.index] - 1).abs() < 0.01).all()
    merged = eo.merge(panel, on=["group", "gw", "fpl_id"], suffixes=("", "_panel"))
    assert len(merged) == len(eo) and (merged["eo"] == merged["eo_panel"]).all()
    # The universe's names for the listed ids match the transcribed names (with 2026-27 ids only ~2% would)
    names = elite._default_universe("2025-26").set_index("fpl_id")["player"]
    assert eo["player"].eq(eo["fpl_id"].map(names)).all()


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
