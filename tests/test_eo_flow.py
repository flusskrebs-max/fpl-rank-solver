"""Tests for the EO flow model (idea 1). Small synthetic fixtures only; no files in data/."""

import numpy as np
import pandas as pd
import pytest

from fplrank.model import eo_flow as ef


def _players():
    return pd.DataFrame(
        {
            "pos": ["M", "M", "M", "D"],
            "price": [10.0, 10.5, 8.0, 5.0],
            "xp": [6.0, 7.0, 5.0, 4.0],
        }
    )


def test_price_gap_uses_same_position_within_band():
    gap = ef.price_gap(_players())
    # 10.0 can reach 10.5 (7.0) -> +1; 10.5 can reach 10.0 and 8.0 -> best 6.0 - 7.0 = -1
    # 8.0 can't reach 10.0 -> nobody -> NaN; the only defender has nobody either
    assert gap[0] == pytest.approx(1.0)
    assert gap[1] == pytest.approx(-1.0)
    assert np.isnan(gap[2]) and np.isnan(gap[3])


def _synthetic(n_gw=8, seed=0):
    """A tiny league: 2 G, 5 D, 5 M, 3 F owned by everyone, plus spare players; ownership drifts with xp."""
    rng = np.random.default_rng(seed)
    pos = ["G"] * 4 + ["D"] * 8 + ["M"] * 8 + ["F"] * 6
    ids = np.arange(1, len(pos) + 1)
    price = np.round(rng.uniform(4, 12, len(ids)), 1)
    stats, own_rows, pts = [], [], []
    share = pd.Series(0.0, index=ids)
    for p, k in ef.SQUAD.items():  # start with the first k of each position fully owned
        share[ids[[i for i, q in enumerate(pos) if q == p][:k]]] = 1.0
    for gw in range(1, n_gw + 1):
        xp = rng.gamma(2.0, 1.5, len(ids))
        stats.append(pd.DataFrame({"gw": gw, "fpl_id": ids, "pos": pos, "xp": xp, "price": price}))
        pts.append(pd.DataFrame({"gw": gw, "fpl_id": ids, "pts": rng.poisson(xp)}))
        if gw > 1:
            z = np.log((share * 64 + 0.5) / (64.5 - share * 64)).to_numpy() + 0.4 * (xp - xp.mean())
            for p, k in ef.SQUAD.items():
                idx = [i for i, q in enumerate(pos) if q == p]
                e = np.exp(z[idx])
                share.iloc[idx] = np.clip(k * e / e.sum(), 0, 1)
        own_rows.append(pd.DataFrame({"gw": gw, "fpl_id": ids, "own": share.to_numpy().copy(), "n": 64.0}))
    chips = pd.DataFrame({"gw": range(1, n_gw + 1), "wc": [0.0] * (n_gw - 1) + [0.3]})
    return pd.concat(own_rows), pd.concat(stats), pd.concat(pts), chips


def test_transitions_features():
    own, stats, pts, chips = _synthetic()
    t = ef.transitions(own, stats, pts, chips)
    assert sorted(t["gw_next"].unique()) == list(range(2, 9))
    assert set(ef.SPLIT_FEATURES) | set(ef.FULL_FEATURES) <= set(t.columns)
    row = t[(t["gw_next"] == 3) & (t["fpl_id"] == 1)].iloc[0]
    xp = stats.set_index(["gw", "fpl_id"])["xp"]
    assert row["dev"] == pytest.approx(xp[(3, 1)] - xp[(2, 1)])
    assert row["pts"] == pts.set_index(["gw", "fpl_id"])["pts"][(2, 1)]
    assert t.loc[t["gw_next"] == 8, "wc"].eq(0.3).all()


def test_fit_and_balanced_forecast():
    own, stats, pts, chips = _synthetic(n_gw=12)
    t = ef.transitions(own, stats, pts, chips)
    beta = ef.fit_flow(t, ef.V0_FEATURES)
    assert beta[ef.V0_FEATURES.index("xp")] > 0  # ownership follows xp in the fixture
    pred = ef.predict_own(t, beta, ef.V0_FEATURES)
    sums = pd.Series(pred).groupby([t["gw_next"].to_numpy(), t["pos"].to_numpy()]).sum()
    for (_, p), total in sums.items():
        assert total == pytest.approx(ef.SQUAD[p], abs=1e-6)


def test_surge_recall():
    rows = pd.DataFrame(
        {
            "gw_next": [5] * 4,
            "fpl_id": [1, 2, 3, 4],
            "own_t": [0.9, 0.1, 0.5, 0.0],
            "own_next": [0.1, 0.7, 0.5, 0.25],
            "pred": [0.5, 0.3, 0.5, 0.0],
        }
    )
    s = ef.surge_recall(rows, "pred", top=1)
    # surges: 1 (fall, top faller -> hit), 2 (rise, top riser -> hit), 4 (rise, not top -> miss)
    assert dict(zip(s["fpl_id"], s["hit"], strict=True)) == {1: True, 2: True, 4: False}


def test_quiet_weeks_and_week_kind():
    trans = pd.DataFrame({"gw_next": [2, 2, 3, 3, 4], "own_t": [0.5, 0.1, 0.5, 0.5, 0.2], "own_next": [0.55, 0.1, 0.2, 0.5, 0.2]})
    share = pd.DataFrame({"WC": [0.0, 0.0, 0.3], "FH": [0.0, 0.0, 0.0], "TC": [0.0, 0.0, 0.0], "BB": [0.0, 0.2, 0.0]}, index=[2, 3, 4])
    assert ef.quiet_weeks(trans, share) == [2]  # 3 has a 30-point move, 4 is a wildcard week
    assert ef.week_kind(share, 2) == "normal" and ef.week_kind(share, 3) == "chip"


def test_backtest_and_score_run_on_fixture():
    own, stats, pts, chips = _synthetic(n_gw=10)
    t = ef.transitions(own, stats, pts, chips)
    eo = own.rename(columns={"own": "eo"})[["gw", "fpl_id", "eo"]].assign(listed=lambda d: d["eo"] > 0.05)
    cap = eo[eo["listed"]].groupby("gw").head(1)[["gw", "fpl_id"]].assign(cap_eo=1.0)
    cap.attrs["tc"] = pd.Series(0.0, index=range(1, 11))
    own_rows, eo_rows = ef.backtest_group(t, eo, cap)
    assert set(ef.MODELS) <= set(own_rows.columns)
    assert {"persist", "captain_only", "full", "eo"} <= set(eo_rows.columns)
    res = ef.score(own_rows, eo_rows, quiet_gws=[3, 4])
    assert set(res["checks"]) == {"eo_15pct", "quiet_no_worse", "recall_50", "recall_50_surge_weeks"}
    assert res["own_mae"]["full"] >= 0
