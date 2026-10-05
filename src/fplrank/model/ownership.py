"""Ownership dynamics v0: forecast next-GW elite EO with an error bar (brief B04).

EO is split into parts that move for different reasons:

    eo = xi + bench + cap * (1 + tc)

- `xi`: share of the group starting the player (0-1). Moves with transfers. Modelled by a 4-parameter
  logistic transition, fitted on the top-1000 data (complete picks):
      logit(xi[t+1]) = a + b * logit(xi[t]) + c * xpts[t+1] + d * pts[t]
  `xpts[t+1]` is the projected points for the next GW (latest projection made for it), `pts[t]` the
  points scored in the GW just played.
- `cap`: share of the group captaining the player. Softmax over the projected points of what the
  group starts, with a temperature fitted per group: cap_j ~ xi_j * exp(xpts_j / tau).
- `tc`: share of those captains on Triple Captain; `bench`: bench players counted on Bench Boost.
  Chip use is an input (`chip_rates`), not forecast: chip timing is a separate question.

Groups: "top1000" (from data/collected, exact), "AE64" / "E64" (Elite 64 graphics: only listed
players are observed, `xi` = eo - captain part; Bench Boost benches can't be separated there).

Everything is deliberately small: a handful of parameters, fitted on a few GWs. See
docs/research/ownership-dynamics-v0.md for results and limits.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, logit

from fplrank.data import elite as elite_data
from fplrank.data.fpl_api import latest_snapshot
from fplrank.data.projections import latest as latest_projection
from fplrank.data.projections import load_solio
from fplrank.paths import COLLECTED_DIR

ELITE_GROUPS = ("AE64", "E64")
TOP_GROUP = "top1000"
GROUP_SIZE = {"AE64": 64, "E64": 64}
BUCKETS = pd.IntervalIndex.from_breaks([-np.inf, 0.02, 0.1, 0.3, 0.7, np.inf])  # forecast EO bands


# ---------------------------------------------------------------------------------------------
# Data: one row per group, GW and player
# ---------------------------------------------------------------------------------------------


def top_table(collected_dir=COLLECTED_DIR, group: str = TOP_GROUP) -> pd.DataFrame:
    """`gw, fpl_id, xi, bench, cap, tc_cap, eo` for a collected set (shares of the set's managers)."""
    picks = pd.read_parquet(collected_dir / "picks.parquet")
    members = pd.read_parquet(collected_dir / "members.parquet")
    picks = picks[picks["entry_id"].isin(members.loc[members["set"] == group, "entry_id"])]
    n = picks.groupby("gw")["entry_id"].nunique()
    picks = picks.assign(
        xi=picks["position"] <= 11,
        bench=(picks["position"] > 11) & (picks["active_chip"] == "bboost"),
        cap=picks["is_captain"],
        tc_cap=picks["is_captain"] & (picks["active_chip"] == "3xc"),
    )
    table = picks.groupby(["gw", "fpl_id"])[["xi", "bench", "cap", "tc_cap"]].sum()
    table = table.div(n, axis=0, level="gw").reset_index()
    table["eo"] = table["xi"] + table["bench"] + table["cap"] + table["tc_cap"]
    table["n"] = table["gw"].map(n)
    return table


def elite_table(group: str) -> pd.DataFrame:
    """`gw, fpl_id, xi, bench, cap, tc_cap, eo` for an Elite 64 group, listed players only.

    `xi` is eo minus the captain part, so on Bench Boost-heavy GWs (1-2) it includes bench players.
    """
    eo = elite_data.load_eo()
    eo = eo[eo["group"] == group]
    meta = elite_data.load_meta()
    caps = meta[(meta["group"] == group) & (meta["table"] == "captain")].copy()
    caps["tc"] = caps["item"].str.endswith(" (TC)")
    caps["player"] = caps["item"].str.removesuffix(" (TC)")
    caps = caps.pivot_table(index=["gw", "player"], columns="tc", values="count", aggfunc="sum", fill_value=0)
    caps = caps.reindex(columns=[False, True], fill_value=0).rename(columns={False: "plain", True: "tc"}).reset_index()
    table = eo.merge(caps, on=["gw", "player"], how="left").fillna({"plain": 0, "tc": 0})
    size = GROUP_SIZE[group]
    table["cap"] = (table["plain"] + table["tc"]) / size
    table["tc_cap"] = table["tc"] / size
    table["bench"] = 0.0
    table["xi"] = (table["eo"] - table["cap"] - table["tc_cap"]).clip(0, 1)
    table["n"] = size
    return table[["gw", "fpl_id", "xi", "bench", "cap", "tc_cap", "eo", "n"]]


def group_table(group: str) -> pd.DataFrame:
    return top_table(group=group) if group not in ELITE_GROUPS else elite_table(group)


def projections_for(gw: int, horizon: int = 1) -> pd.Series:
    """Projected points for `gw`..`gw + horizon - 1` (summed) from the latest projection made for `gw`."""
    proj = load_solio(latest_projection(gw))
    proj = proj[proj["gw"].between(gw, gw + horizon - 1)]
    return proj.groupby("fpl_id")["xpts"].sum()


def points_in(gw: int) -> pd.Series:
    """Actual FPL points scored in `gw`, from the saved event/{gw}/live/ snapshot."""
    live = latest_snapshot(f"event/{gw}/live/")
    return pd.Series({e["id"]: e["stats"]["total_points"] for e in live["elements"]}, name="pts")


def chip_rates(table: pd.DataFrame, gw: int) -> dict:
    """Chip use in `gw` as the model needs it: TC share of captains, Bench Boost bench EO per player."""
    g = table[table["gw"] == gw]
    cap = g["cap"].sum()
    return {"tc": float(g["tc_cap"].sum() / cap) if cap else 0.0, "bench": g.set_index("fpl_id")["bench"]}


# ---------------------------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------------------------


def _shrunk_logit(share, n):
    """logit of a share, shrunk away from 0/1 by half a manager so empty and full players are finite."""
    return logit((np.asarray(share, float) * n + 0.5) / (n + 1))


@dataclass
class OwnershipModel:
    xi_params: np.ndarray = field(default_factory=lambda: np.array([0.0, 1.0, 0.0, 0.0]))  # a, b, c, d
    tau: dict = field(default_factory=dict)  # captain softmax temperature per group (xpts units)
    residual_q: dict = field(default_factory=dict)  # group -> 10%/90% EO error by forecast bucket (backtest)

    def xi_next(self, xi_t, n, xpts_next, pts_t):
        a, b, c, d = self.xi_params
        return expit(a + b * _shrunk_logit(xi_t, n) + c * np.asarray(xpts_next) + d * np.asarray(pts_t))

    def cap_shares(self, xi, xpts, group):
        w = np.asarray(xi) * np.exp((np.asarray(xpts) - np.max(xpts)) / self.tau.get(group, 1.0))
        return w / w.sum() if w.sum() > 0 else w


def transitions(table: pd.DataFrame, universe: pd.Index | None = None) -> pd.DataFrame:
    """Rows (gw_next, fpl_id) with xi_t, xi_next, xpts_next, pts_t for every consecutive pair of GWs.

    Players missing from a GW get xi = 0 (exact for collected sets; for Elite 64 they are censored and
    the backtest only scores listed players). `universe` defaults to everyone in the table or the projections.
    """
    rows = []
    for gw in sorted(table["gw"].unique())[:-1]:
        nxt = gw + 1
        if nxt not in set(table["gw"]):
            continue
        xpts = projections_for(nxt)
        ids = universe if universe is not None else pd.Index(table["fpl_id"].unique()).union(xpts.index)
        now = table[table["gw"] == gw].set_index("fpl_id")
        later = table[table["gw"] == nxt].set_index("fpl_id")
        frame = pd.DataFrame(index=ids.rename("fpl_id"))
        frame["gw_next"] = nxt
        frame["xi_t"] = now["xi"].reindex(ids).fillna(0).to_numpy()
        frame["xi_next"] = later["xi"].reindex(ids).fillna(0).to_numpy()
        frame["xpts_next"] = xpts.reindex(ids).fillna(0).to_numpy()
        frame["pts_t"] = points_in(gw).reindex(ids).fillna(0).to_numpy()
        frame["n"] = int(table["n"].iloc[0])
        rows.append(frame.reset_index())
    return pd.concat(rows, ignore_index=True)


def fit_xi(trans: pd.DataFrame) -> np.ndarray:
    """Fit (a, b, c, d) by binomial likelihood of xi_next (shares of n managers)."""
    x = np.column_stack([np.ones(len(trans)), _shrunk_logit(trans["xi_t"], trans["n"]), trans["xpts_next"], trans["pts_t"]])
    y, n = trans["xi_next"].to_numpy(), trans["n"].to_numpy()

    def nll(beta):
        z = x @ beta
        return -np.sum(n * (y * -np.logaddexp(0, -z) + (1 - y) * -np.logaddexp(0, z))) / n.sum()

    return minimize(nll, np.array([0.0, 1.0, 0.0, 0.0]), method="BFGS").x


def fit_tau(table: pd.DataFrame, gws=None) -> float:
    """Captain softmax temperature by multinomial likelihood of the captain shares, pooled over `gws`."""
    gws = sorted(table["gw"].unique()) if gws is None else gws
    data = []
    for gw in gws:
        g = table[table["gw"] == gw]
        xpts = projections_for(gw).reindex(g["fpl_id"]).fillna(0).to_numpy()
        data.append((g["xi"].to_numpy(), xpts, g["cap"].to_numpy()))
    return fit_tau_arrays(data)


def fit_tau_arrays(data) -> float:
    """`fit_tau` on [(xi, xpts, cap), ...] arrays, one tuple per GW."""

    def nll(log_tau):
        tau, total = np.exp(log_tau[0]), 0.0
        for xi, xpts, cap in data:
            w = np.log(np.clip(xi, 1e-6, None)) + (xpts - xpts.max()) / tau
            total -= np.sum(cap * (w - np.logaddexp.reduce(w)))
        return total

    return float(np.exp(minimize(nll, [0.0], method="Nelder-Mead").x[0]))


# ---------------------------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------------------------


def state_for(group: str, gw_next: int, table: pd.DataFrame | None = None, chips_known: bool = True) -> dict:
    """Inputs for `forecast_eo` from repo data: the group at gw_next - 1, projections, points, chip use.

    With `chips_known`, `chip_rates` are the group's actual chip use in `gw_next` (for backtests);
    otherwise no chips are assumed.
    """
    table = group_table(group) if table is None else table
    gw = gw_next - 1
    now = table[table["gw"] == gw].set_index("fpl_id")
    known = chips_known and gw_next in set(table["gw"])
    return {
        "xi": now["xi"],
        "n": int(table["n"].iloc[0]),
        "xpts_next": projections_for(gw_next),
        "pts_last": points_in(gw),
        "chip_rates": chip_rates(table, gw_next) if known else {"tc": 0.0, "bench": pd.Series(dtype=float)},
    }


def forecast_eo(group: str, gw_next: int, state: dict, model: OwnershipModel) -> pd.DataFrame:
    """Forecast EO for `gw_next`: `fpl_id, xi, cap, eo_mean, eo_low, eo_high` (80% band from backtest residuals)."""
    ids = state["xi"].index.union(state["xpts_next"].index)
    xi_t = state["xi"].reindex(ids).fillna(0)
    xpts = state["xpts_next"].reindex(ids).fillna(0)
    pts = state["pts_last"].reindex(ids).fillna(0)
    xi = model.xi_next(xi_t, state["n"], xpts, pts)
    xi = pd.Series(xi * (11 / xi.sum()), index=ids)  # every manager starts 11
    cap = pd.Series(model.cap_shares(xi, xpts, group), index=ids)
    bench = state["chip_rates"]["bench"].reindex(ids).fillna(0)
    eo = xi + bench + cap * (1 + state["chip_rates"]["tc"])
    out = pd.DataFrame({"fpl_id": ids, "xi": xi.to_numpy(), "cap": cap.to_numpy(), "eo_mean": eo.to_numpy()})
    out["eo_low"], out["eo_high"] = out["eo_mean"], out["eo_mean"]
    if group in model.residual_q:
        q = model.residual_q[group].to_numpy()[pd.cut(out["eo_mean"], BUCKETS).cat.codes]  # rows follow BUCKETS
        out["eo_low"] = (out["eo_mean"] + q[:, 0]).clip(lower=0)
        out["eo_high"] = out["eo_mean"] + q[:, 1]
    return out.sort_values("eo_mean", ascending=False, ignore_index=True)


def residual_quantiles(errors: pd.DataFrame, q=(0.1, 0.9)) -> pd.DataFrame:
    """10%/90% quantiles of (actual - forecast) EO by forecast bucket."""
    bucket = pd.cut(errors["eo_mean"], BUCKETS)
    return (errors["eo"] - errors["eo_mean"]).groupby(bucket, observed=False).quantile(list(q)).unstack().fillna(0)


# ---------------------------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------------------------


def backtest(groups=(TOP_GROUP, *ELITE_GROUPS), chips_known: bool = True) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Leave-one-GW-out backtest of forecast_eo against "next week = this week".

    For each transition gw -> gw+1, the xi model is fitted on the other top-1000 transitions and each
    group's tau on its other GWs. Scored on every player with EO in either week (top1000) or on
    players listed in gw+1 (Elite 64, where unlisted EO is unknown).
    Returns (per-player errors, summary per group and GW, fitted parameters per held-out GW).
    """
    top = group_table(TOP_GROUP)
    top_trans = transitions(top)
    tables = {g: (top if g == TOP_GROUP else group_table(g)) for g in groups}
    errors, params = [], {}
    for gw_next in sorted(top_trans["gw_next"].unique()):
        xi_params = fit_xi(top_trans[top_trans["gw_next"] != gw_next])
        params[gw_next] = {"xi": xi_params}
        for group, table in tables.items():
            if gw_next not in set(table["gw"]) or gw_next - 1 not in set(table["gw"]):
                continue
            tau = fit_tau(table, [g for g in sorted(table["gw"].unique()) if g != gw_next])
            params[gw_next][group] = tau
            model = OwnershipModel(xi_params=xi_params, tau={group: tau})
            fc = forecast_eo(group, gw_next, state_for(group, gw_next, table, chips_known), model)
            actual = table[table["gw"] == gw_next].set_index("fpl_id")["eo"]
            before = table[table["gw"] == gw_next - 1].set_index("fpl_id")["eo"]
            scored = actual.index if group in ELITE_GROUPS else actual.index.union(before.index)
            fc = fc.set_index("fpl_id").reindex(scored)
            errors.append(
                pd.DataFrame(
                    {
                        "group": group,
                        "gw_next": gw_next,
                        "fpl_id": scored,
                        "eo": actual.reindex(scored).fillna(0).to_numpy(),
                        "eo_mean": fc["eo_mean"].fillna(0).to_numpy(),
                        "persist": before.reindex(scored).fillna(0).to_numpy(),
                    }
                )
            )
    errors = pd.concat(errors, ignore_index=True)
    summary = errors.assign(model_ae=(errors["eo"] - errors["eo_mean"]).abs(), persist_ae=(errors["eo"] - errors["persist"]).abs())
    summary = summary.groupby(["group", "gw_next"]).agg(
        players=("fpl_id", "size"), mae_model=("model_ae", "mean"), mae_persist=("persist_ae", "mean")
    )
    return errors, summary.reset_index(), params


def fit_default(groups=(TOP_GROUP, *ELITE_GROUPS)) -> OwnershipModel:
    """Model fitted on all the data we have, with error bands from the leave-one-GW-out backtest."""
    top = group_table(TOP_GROUP)
    errors, _, _ = backtest(groups, chips_known=False)
    tau = {g: fit_tau(top if g == TOP_GROUP else group_table(g)) for g in groups}
    bands = {g: residual_quantiles(errors[errors["group"] == g]) for g in groups}
    return OwnershipModel(xi_params=fit_xi(transitions(top)), tau=tau, residual_q=bands)
