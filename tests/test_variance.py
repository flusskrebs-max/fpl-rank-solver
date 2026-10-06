"""S2b variance table on synthetic rows."""

import numpy as np
import pandas as pd
import pytest

from fplrank.model import variance as v


def test_bands_by_quantile_with_zero_band():
    xp = pd.Series([0.0, 0.05, 1, 2, 3, 4])
    assert v.bands(xp, n_bands=2).tolist() == [0, 0, 1, 1, 2, 2]


def test_table_and_lookup():
    rng = np.random.default_rng(0)
    n = 4000
    xp = rng.uniform(0.1, 8, n)
    pts = rng.poisson(xp)  # variance = mean
    rows = pd.DataFrame({"season": "S", "gw": 1, "fpl_id": range(n), "pos": "M", "xp": xp, "pts": pts})
    table = v.variance_table(rows, n_bands=4)
    assert table["band"].tolist() == [1, 2, 3, 4]
    np.testing.assert_allclose(table["pts_var"], table["xp_mean"], rtol=0.25)  # plus the spread of xP within a band
    other = pd.Series([0.0, 0.3, 9.0])  # another source on a different scale: banded within itself
    got = v.lookup(table, pd.Series(["M", "M", "M"]), other)
    assert np.isnan(got[0]) and got[2] == pytest.approx(table["pts_var"].iloc[-1])
