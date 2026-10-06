"""EO blend: chip stripping, re-picking, the weight fit and the bootstrap. Synthetic data only (no data/)."""

import numpy as np
import pandas as pd
import pytest

from fplrank.model import eo_blend as eb

POS = [1, 1, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 4, 4, 4]


def _picks(entry_id, gw, ids, chip=None, captain=None):
    return pd.DataFrame(
        {
            "entry_id": entry_id,
            "gw": gw,
            "fpl_id": ids,
            "position": range(1, 16),
            "is_captain": [i == (captain or ids[2]) for i in ids],
            "element_type": POS,
            "active_chip": chip,
        }
    )


def test_fair_rows_strip_chips_and_revert_free_hits():
    base = list(range(1, 16))
    picks = pd.concat(
        [
            _picks(1, 2, base),
            _picks(1, 3, list(range(101, 116)), chip="freehit"),  # free hit: back to the GW2 squad
            _picks(2, 3, base, chip="3xc"),
            _picks(3, 3, base, chip="bboost"),
        ]
    )
    rows = eb.fair_rows(picks, 3)
    m = rows.set_index(["entry_id", "fpl_id"])["multiplier"]
    assert set(rows.loc[rows["entry_id"] == 1, "fpl_id"]) == set(base)
    assert m[(2, 3)] == 2  # triple captain counted as a normal captain
    assert m[(3, 15)] == 0  # bench-boost bench at 0
    assert rows.groupby("entry_id")["multiplier"].sum().eq(12).all()


def test_lineup_picks_best_valid_formation_and_captain():
    xp = np.array([4, 4.5, 1, 1, 1, 1, 1, 8, 7, 6, 5, 4, 3, 2, 0.5])
    mult = eb.lineup(np.array(POS), xp)
    assert mult[1] == 1 and mult[0] == 0  # better keeper
    assert (mult[np.array(POS) == 2] > 0).sum() == 3  # at least 3 defenders even with low xP
    assert (mult[np.array(POS) == 4] > 0).sum() >= 1
    assert (mult > 0).sum() == 11 and mult.max() == 2 and mult[7] == 2  # captain: best starter
    assert mult.sum() == 12


def test_simplex_weights_sum_to_one():
    w = eb.simplex(3, 0.25)
    assert len(w) == 15 and np.allclose(w.sum(1), 1) and (w >= 0).all()


def test_fit_recovers_a_known_mix():
    rng = np.random.default_rng(0)
    cases = []
    for _ in range(3):
        x = pd.DataFrame(rng.uniform(0, 100, (60, 4)), columns=list(eb.INPUTS))
        y = 0.3 * x["fair"] + 0.7 * x["banked"]
        cases.append({"X": {0.0: x, 0.1: x.assign(drift=x["drift"] + 50)}, "y": y, "n": 10})
    _, w, err = eb.fit(cases, ks=(0.0, 0.1))
    assert dict(zip(eb.INPUTS, w, strict=True)) == pytest.approx({"fair": 0.3, "repick": 0, "drift": 0, "banked": 0.7})
    assert err == pytest.approx(0, abs=1e-9)


def test_bootstrap_full_sample_gain():
    actual = np.array([[100.0, 0], [0, 100]])
    mats = {2: {"actual": actual, "persistence": np.array([[0.0, 100], [0, 100]]), "banked": actual.copy(), "fair": actual * 0}}
    b = eb.bootstrap(mats, n_boot=50).set_index("gain")
    assert b.loc["banked vs persistence", "full_sample"] == pytest.approx(1.0)
    assert b.loc["banked vs fair", "p05"] == pytest.approx(1.0)


def test_surges_count_moves_and_those_left_after_a_base():
    prev, now, base = pd.Series([0.0, 50, 10]), pd.Series([30.0, 20, 10]), pd.Series([25.0, 25, 10])
    assert eb.surges(prev, now, base) == {"rises": 1, "falls": 1, "still_vs_base": 0}
