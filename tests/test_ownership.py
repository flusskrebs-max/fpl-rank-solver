"""Ownership dynamics v0 on synthetic data (the real-data backtest lives in notebooks/, it needs local data)."""

import numpy as np
import pandas as pd
import pytest
from scipy.special import expit

from fplrank.model import ownership as o


def test_fit_xi_recovers_parameters():
    rng = np.random.default_rng(1)
    k, n = 4000, 1000
    xi_t = rng.beta(0.3, 3, k)
    xpts, pts = rng.uniform(0, 8, k), rng.integers(0, 15, k)
    true = np.array([-2.5, 0.7, 0.5, 0.02])
    p = expit(true[0] + true[1] * o._shrunk_logit(xi_t, n) + true[2] * xpts + true[3] * pts)
    trans = pd.DataFrame({"xi_t": xi_t, "xi_next": rng.binomial(n, p) / n, "xpts_next": xpts, "pts_t": pts, "n": n})
    np.testing.assert_allclose(o.fit_xi(trans), true, atol=0.05)


def test_fit_tau_recovers_temperature():
    rng = np.random.default_rng(2)
    data = []
    for _ in range(5):
        xi = rng.uniform(0.05, 1, 30)
        xpts = rng.uniform(2, 8, 30)
        w = xi * np.exp(xpts / 0.5)
        data.append((xi, xpts, w / w.sum()))
    assert o.fit_tau_arrays(data) == pytest.approx(0.5, rel=0.02)


def test_cap_shares_softmax():
    model = o.OwnershipModel(tau={"g": 1.0})
    shares = model.cap_shares([1.0, 1.0, 0.5, 0.0], [6.0, 5.0, 6.0, 9.0], "g")
    assert shares.sum() == pytest.approx(1)
    assert shares[3] == 0  # nobody starts him, so nobody captains him
    assert shares[0] == pytest.approx(np.e * shares[1]) and shares[0] == pytest.approx(2 * shares[2])


def _state():
    ids = pd.Index(range(1, 31), name="fpl_id")
    return {
        "xi": pd.Series(np.r_[np.full(11, 0.9), np.full(19, 0.0)] + 0.0, index=ids).iloc[:25],  # 5 ids only in projections
        "n": 100,
        "xpts_next": pd.Series(np.linspace(8, 1, 30), index=ids),
        "pts_last": pd.Series(5.0, index=ids),
        "chip_rates": {"tc": 0.5, "bench": pd.Series({30: 0.2})},
    }


def test_forecast_eo_adds_up():
    model = o.OwnershipModel(xi_params=np.array([-2.5, 0.7, 0.5, 0.0]), tau={"g": 0.5})
    fc = o.forecast_eo("g", 6, _state(), model).set_index("fpl_id")
    assert len(fc) == 30 and fc["xi"].sum() == pytest.approx(11)  # everyone starts 11
    assert fc["cap"].sum() == pytest.approx(1)
    # eo = xi + bench + cap x (1 + TC share)
    expected = fc["xi"] + pd.Series({30: 0.2}).reindex(fc.index).fillna(0) + fc["cap"] * 1.5
    pd.testing.assert_series_equal(fc["eo_mean"], expected, check_names=False)
    assert (fc["eo_low"] == fc["eo_mean"]).all()  # no error bands without backtest residuals


def test_forecast_eo_bands_from_residuals():
    errors = pd.DataFrame({"eo_mean": [0.05] * 10 + [0.5] * 10, "eo": [0.05 + d for d in np.linspace(-0.04, 0.04, 10)] * 2})
    bands = o.residual_quantiles(errors)
    assert list(bands.index.astype(str)) == [str(b) for b in o.BUCKETS]
    model = o.OwnershipModel(xi_params=np.array([-2.5, 0.7, 0.5, 0.0]), tau={"g": 0.5}, residual_q={"g": bands})
    fc = o.forecast_eo("g", 6, _state(), model)
    assert (fc["eo_low"] <= fc["eo_mean"]).all() and (fc["eo_high"] >= fc["eo_mean"]).all()
    assert (fc["eo_high"] > fc["eo_low"]).any()
