"""Realised-spread check for S2 (V1): does S2's predicted sd match what real managers' scores did?

For each collected group (AE64, E64, top1000, top10k) and GW, every member's realised score relative to
the group is

    Δ = Σ (m - EO) x pts - (hits - group mean hits)

with m the manager's multipliers and EO the group's, both as FPL counted them (after automatic subs),
so Δ averages 0 over the group. S2 predicts, for the same squads at the deadline,

    mean_i = Σ (m - EO) x xP,   var_i = Σ (m - EO)² x v(xP)

(xP from the newest Solio file made for that GW, v from the S2b table). If S2 is right, the spread of
Δ across managers should satisfy  var(Δ) ≈ var(mean_i) + average var_i. The ratio of the two sds is
the scale s for S2c (`--s`): within ~20% of 1, keep s = 1.

Also: per-GW σ² of Δ (the empirical base for S2c) and the line's drift against each group.
"""

import numpy as np
import pandas as pd

from fplrank.data.projections import latest, load_solio
from fplrank.model import variance
from fplrank.model.ownership import points_in
from fplrank.paths import COLLECTED_DIR

GROUPS = ("AE64", "E64", "top1000", "top10k")


def _load(collected_dir=COLLECTED_DIR):
    picks = pd.read_parquet(collected_dir / "picks.parquet")
    members = pd.read_parquet(collected_dir / "members.parquet")
    ranks = pd.read_parquet(collected_dir / "ranks.parquet")
    return picks, members, ranks


def gw_spread(picks: pd.DataFrame, hits: pd.Series, pts: pd.Series, xp: pd.Series, v: pd.Series) -> dict:
    """One group and GW. picks: `entry_id, fpl_id, multiplier, position, is_captain, active_chip` for its
    members; hits: entry_id -> transfer cost; pts/xp/v: fpl_id -> points, projection, variance."""
    real = picks.pivot_table(index="entry_id", columns="fpl_id", values="multiplier", aggfunc="sum", fill_value=0)
    # deadline multipliers: the XI (positions 1-11, or all 15 on Bench Boost) plus the captain's extra
    bb = picks["active_chip"].eq("bboost")
    tc = picks["active_chip"].eq("3xc")
    dl = picks.assign(m=((picks["position"] <= 11) | bb) * (1 + picks["is_captain"] * (1 + tc)))
    dead = dl.pivot_table(index="entry_id", columns="fpl_id", values="m", aggfunc="sum", fill_value=0).reindex(
        columns=real.columns, fill_value=0
    )
    ids = real.columns
    p, x, var = pts.reindex(ids).fillna(0), xp.reindex(ids).fillna(0), v.reindex(ids).fillna(0)
    h = hits.reindex(real.index).fillna(0)
    delta = (real - real.mean()) @ p - (h - h.mean())
    d = dead - dead.mean()
    mean_i, var_i = d @ x, (d**2) @ var
    pred_var = float(mean_i.var() + var_i.mean())
    return {"n": len(real), "sd_real": float(delta.std()), "sd_pred": float(np.sqrt(pred_var)), "sd_mean": float(mean_i.std())}


def spread_table(groups=GROUPS, gws=None, collected_dir=COLLECTED_DIR) -> pd.DataFrame:
    picks, members, ranks = _load(collected_dir)
    vtable = variance.build()
    gws = gws or sorted(picks["gw"].unique())
    rows = []
    for gw in gws:
        proj = load_solio(latest(int(gw)))
        proj = proj[proj["gw"] == gw].set_index("fpl_id")
        xp = proj["xpts"]
        v = variance.lookup(vtable, proj["pos"], xp)
        pts = points_in(int(gw))
        g_ranks = ranks[ranks["gw"] == gw].set_index("entry_id")["event_transfers_cost"]
        for group in groups:
            ids = set(members.loc[members["set"] == group, "entry_id"])
            gp = picks[(picks["gw"] == gw) & picks["entry_id"].isin(ids)]
            if gp.empty:
                continue
            rows.append({"group": group, "gw": int(gw), **gw_spread(gp, g_ranks, pts, xp, v)})
    table = pd.DataFrame(rows)
    table["ratio"] = table["sd_real"] / table["sd_pred"]
    return table


def summary(table: pd.DataFrame) -> pd.DataFrame:
    """Per group: RMS of realised and predicted sd over GWs, and their ratio (the suggested s)."""
    g = table.groupby("group")
    out = pd.DataFrame(
        {
            "gws": g.size(),
            "sd_real": g["sd_real"].apply(lambda s: np.sqrt((s**2).mean())),
            "sd_pred": g["sd_pred"].apply(lambda s: np.sqrt((s**2).mean())),
        }
    )
    out["s"] = out["sd_real"] / out["sd_pred"]
    return out
