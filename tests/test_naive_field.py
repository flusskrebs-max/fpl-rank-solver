"""Naive field: team states at a past deadline, group tables and scoring. Synthetic data only (no data/)."""

import pandas as pd
import pytest

from fplrank.model import naive_field as nf


def _bootstrap(n=15, price=60):
    elements = [
        {"id": i, "now_cost": price + 2, "cost_change_start": 2, "element_type": 1 + (i - 1) % 4, "team": 1} for i in range(1, n + 3)
    ]
    events = [{"id": g, "is_next": g == 6, "is_current": g == 5, "finished": g < 6} for g in range(1, 9)]
    return {"elements": elements, "events": events}


def test_market_prices_use_latest_purchase_at_or_before_the_deadline():
    b = _bootstrap()
    t = pd.DataFrame(
        {"gw": [2, 3, 3, 5], "element_in": [1] * 4, "element_in_cost": [61, 62, 64, 70], "element_out": [9] * 4, "element_out_cost": 60}
    )
    assert nf.market_prices(t, b, 3)[1] == 63  # median of the GW3 purchases
    assert nf.market_prices(t, b, 4)[1] == 63  # nothing bought for GW4: last earlier price
    assert nf.market_prices(t, b, 1)[1] == 60  # before any purchase: start price
    assert nf.market_prices(t, b, 3)[2] == 60  # never bought: start price


def test_bootstrap_at_keeps_start_prices_and_moves_the_next_event():
    b = nf.bootstrap_at(_bootstrap(), 3, {1: 65})
    e1 = next(e for e in b["elements"] if e["id"] == 1)
    assert e1["now_cost"] == 65 and e1["now_cost"] - e1["cost_change_start"] == 60
    assert [e["id"] for e in b["events"] if e["is_next"]] == [3]
    assert [e["id"] for e in b["events"] if e["finished"]] == [1, 2]


def test_team_state_rebuilds_squad_bank_and_free_transfers():
    b = nf.bootstrap_at(_bootstrap(), 4, {16: 50, 1: 70})
    picks = pd.DataFrame({"entry_id": 7, "gw": 1, "fpl_id": range(1, 16)})
    transfers = pd.DataFrame(
        {
            "entry_id": [7, 7],
            "gw": [3, 4],  # the GW4 transfer is after the deadline we rebuild for
            "element_in": [16, 17],
            "element_in_cost": [50, 60],
            "element_out": [2, 3],
            "element_out_cost": [60, 60],
            "time": ["2026-09-01T00:00:00Z", "2026-09-10T00:00:00Z"],
        }
    )
    chips = pd.DataFrame({"entry_id": [7], "gw": [2], "chip": ["bboost"]})
    d = nf.team_state(7, 4, picks, transfers, chips, b)
    squad = {p["element"]: p for p in d["picks"]}
    assert 16 in squad and 2 not in squad and 17 not in squad
    assert d["transfers"]["bank"] == 1000 - 15 * 60 + 60 - 50
    assert d["transfers"]["limit"] == 2  # GW2: 1 FT unused -> 2 for GW3; GW3: 1 used -> 1 + 1 = 2 for GW4
    assert squad[1]["selling_price"] == 65  # bought at 60, now 70: half the rise
    assert d["chips"] == []


def test_variant_inputs():
    d = {"picks": [], "transfers": {"bank": 0, "limit": 3, "made": 0}}
    assert nf.variant_inputs(d, "1ft", 5)[0]["transfers"]["limit"] == 1
    assert nf.variant_inputs(d, "2ft", 5)[0]["transfers"]["limit"] == 2
    assert nf.variant_inputs(d, "banked", 5)[0]["transfers"]["limit"] == 3
    assert nf.variant_inputs(d, "wc", 5)[1] == {"use_wc": [5]}
    assert d["transfers"]["limit"] == 3  # input untouched
    with pytest.raises(ValueError):
        nf.variant_inputs(d, "fh", 5)


def test_group_table_shares_and_eo():
    rows = pd.DataFrame({"entry_id": [1, 1, 2, 2, 3], "gw": 5, "fpl_id": [10, 11, 10, 12, 10], "multiplier": [2, 1, 1, 0, 2]})
    t = nf.group_table(rows, pd.Series([1, 2])).set_index("fpl_id")  # member 3 is in another group
    assert t.loc[10, "own"] == 1.0 and t.loc[10, "eo"] == 1.5
    assert t.loc[12, "own"] == 0.5 and t.loc[12, "eo"] == 0.0


def test_score_and_pass_checks():
    prev = pd.DataFrame({"fpl_id": [1, 2, 3], "own": [0.5, 0.4, 0.1], "eo": [1.0, 0.4, 0.1]})
    actual = pd.DataFrame({"fpl_id": [1, 2, 3], "own": [0.2, 0.4, 0.4], "eo": [0.2, 0.8, 0.4]})
    perfect = nf.score(prev, actual, actual)
    assert perfect["own_mae"] == 0 and perfect["eo_mae"] == 0
    assert perfect["eo_mae_persist"] == pytest.approx((80 + 40 + 30) / 3)
    assert perfect["surges"] == 2 and perfect["caught"] == 2
    same = nf.score(prev, actual, prev)  # forecasting no change catches nothing
    assert same["caught"] == 0 and same["eo_mae"] == same["eo_mae_persist"]
    table = pd.DataFrame(
        [
            {"group": "AE64", "variant": "banked", "quiet": False, **perfect},
            {"group": "AE64", "variant": "1ft", "quiet": True, **same},
        ]
    )
    check = nf.passes(table).set_index("variant")
    assert bool(check.loc["banked", "pass_eo"]) and bool(check.loc["banked", "pass_recall"])
    assert not check.loc["1ft", "pass_eo"] and bool(check.loc["1ft", "pass_quiet"])


def test_future_ev_sums_the_horizon():
    proj = pd.DataFrame({"ID": [1, 2], "5_Pts": [1.0, 2.0], "6_Pts": [3.0, None], "7_Pts": [9.0, 9.0]})
    assert nf.future_ev(proj, 5, 2).to_dict() == {1: 4.0, 2: 2.0}


def test_cheap_forecast_moves_ownership_towards_higher_ev_within_a_position():
    prev = pd.DataFrame({"fpl_id": [1, 2, 3], "own": [0.5, 0.5, 1.0], "eo": [1.0, 0.5, 1.0]})
    ev, pos = pd.Series({1: 30.0, 2: 20.0, 3: 25.0}), pd.Series({1: 3, 2: 3, 3: 4})
    same = nf.cheap_forecast(prev, ev, pos, k=0.0).set_index("fpl_id")
    assert same["own"].to_dict() == {1: 0.5, 2: 0.5, 3: 1.0}
    moved = nf.cheap_forecast(prev, ev, pos, k=0.2).set_index("fpl_id")
    assert moved.loc[1, "own"] > 0.5 > moved.loc[2, "own"]
    assert moved.loc[[1, 2], "own"].sum() == pytest.approx(1.0)  # midfield slots held
    assert moved.loc[1, "eo"] == pytest.approx(2 * moved.loc[1, "own"])  # EO scales with ownership
    wc = pd.DataFrame({"fpl_id": [9], "own": [1.0], "eo": [2.0]})
    mixed = nf.cheap_forecast(prev, ev, pos, k=0.0, wc=wc, w=0.25).set_index("fpl_id")
    assert mixed.loc[9, "own"] == 0.25 and mixed.loc[9, "eo"] == 0.5 and mixed.loc[3, "own"] == 0.75


def test_eo_gap():
    prev = pd.DataFrame({"fpl_id": [1, 2], "own": [1.0, 0.5], "eo": [2.0, 0.5]})
    a = pd.DataFrame({"fpl_id": [1, 3], "own": [1.0, 0.5], "eo": [1.0, 0.5]})
    assert nf.eo_gap(prev, a, a) == 0
    assert nf.eo_gap(prev, a, prev) == pytest.approx((100 + 50 + 50) / 3)
