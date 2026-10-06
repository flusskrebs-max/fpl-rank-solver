"""V1 realised spread on a tiny synthetic group."""

import pandas as pd
import pytest

from fplrank.eval import spread


def test_gw_spread_relative_scores():
    # two managers, three players; A captains 1, B starts 2 instead of 3
    rows = [(1, 1, 2, 1, True), (1, 2, 1, 2, False), (1, 3, 0, 12, False), (2, 1, 1, 1, False), (2, 3, 2, 2, True), (2, 2, 0, 12, False)]
    picks = pd.DataFrame(rows, columns=["entry_id", "fpl_id", "multiplier", "position", "is_captain"]).assign(active_chip=None)
    pts = pd.Series({1: 10, 2: 2, 3: 6})
    out = spread.gw_spread(
        picks, pd.Series({1: 0, 2: 4}), pts, xp=pd.Series({1: 6.0, 2: 3.0, 3: 3.0}), v=pd.Series({1: 9.0, 2: 4.0, 3: 4.0})
    )
    # realised: A = 2*10 + 2 = 22, B = 10 + 12 - 4 = 18 -> deltas +2, -2 -> sd sqrt(8)
    assert out["n"] == 2 and out["sd_real"] == pytest.approx(8**0.5)
    # deadline m: A (2,1,0), B (1,0,2); m - mean = ±(0.5, 0.5, -1); mean_i = ±(3 + 1.5 - 3) = ±1.5
    assert out["sd_mean"] == pytest.approx(3 / 2**0.5)
    assert out["sd_pred"] == pytest.approx((4.5 + (0.25 * 9 + 0.25 * 4 + 1 * 4)) ** 0.5)
