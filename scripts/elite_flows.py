"""Derived Elite 64 tables for a season: weekly summary and transfer flows vs points (B06).

Port of Cowork's analyse_2025-26.py. Its outputs need vaastav's merged_gw.csv (points by GW), which
is downloaded, not committed, so the tables are written to data/derived/elite64/ (git-ignored):

    weekly_summary_<season>.csv      per GW and group: captaincy, chips, transfers, FTs, hits, EO listing
    flows_player_gw_<season>.csv     net transfers in per player and GW vs points the GW before
    flow_by_prev_points_<season>.csv mean net flow by last-GW points bucket
    top_pileins_<season>.csv         the 25 biggest combined pile-ins

Usage: uv run python scripts/elite_flows.py [season]   (default 2025-26)
"""

import sys

import numpy as np
import pandas as pd

from fplrank.data import historical
from fplrank.data.elite import load_eo, load_meta
from fplrank.paths import DATA_DIR

OUT_DIR = DATA_DIR / "derived" / "elite64"
GROUPS = ["AE64", "E64"]


def weekly_summary(meta: pd.DataFrame, eo: pd.DataFrame, pts: pd.Series) -> pd.DataFrame:
    def table(name, gw, group):
        t = meta[(meta["table"] == name) & (meta["gw"] == gw) & (meta["group"] == group)]
        return t.set_index("item")["count"]

    rows = []
    for gw in sorted(meta["gw"].unique()):
        row = {"gw": gw}
        e = eo[eo["gw"] == gw]
        for g in GROUPS:
            p = g.lower()
            chips = table("chip_active", gw, g)
            row[f"{p}_n"] = chips.sum()
            caps = table("captain", gw, g)
            if caps.sum():
                share = caps.groupby(caps.index.str.removesuffix(" (TC)")).sum() / caps.sum()
                row |= {
                    f"{p}_cap_top": share.idxmax(),
                    f"{p}_cap_share": round(share.max(), 3),
                    f"{p}_cap_eff": round(1 / (share**2).sum(), 2),
                }
            row |= {f"{p}_chip_{c}": int(chips.get(c, 0)) for c in ["WC", "FH", "TC", "BB"]}
            used = table("fts_used", gw, g)
            used = used[~used.index.isin(["WC", "FH"])]
            if used.sum():
                k = used.index.astype(int)
                row[f"{p}_transfers_pm"] = round((k * used).sum() / used.sum(), 2)
                row[f"{p}_roll_share"] = round(used[k == 0].sum() / used.sum(), 3)
            bank = table("fts_remaining_next", gw, g)
            if bank.sum():
                row[f"{p}_ft_bank_next"] = round((bank.index.astype(int) * bank).sum() / bank.sum(), 2)
            hits = table("hits", gw, g)
            if hits.sum():
                row[f"{p}_hit_share"] = round(hits[hits.index != "0"].sum() / hits.sum(), 3)
            ins = table("transfer_in", gw, g)
            if ins.sum():
                row |= {
                    f"{p}_in_top": ins.idxmax(),
                    f"{p}_in_top_n": int(ins.max()),
                    f"{p}_in_top_share_of_all": round(ins.max() / ins.sum(), 3),
                }
            ge = e[e["group"] == g]
            if len(ge):
                row[f"{p}_n50"] = int((ge["eo"] >= 0.5).sum())
                row[f"{p}_eo_listed"] = round(100 * ge["eo"].sum())
                row[f"{p}_listed_score"] = round((ge["eo"] * ge["fpl_id"].map(lambda i, gw=gw: pts.get((i, gw), 0))).sum(), 1)
        if len(e):
            w = e.pivot_table(index="fpl_id", columns="group", values="eo")
            row["divergence"] = round(100 * (w["AE64"] - w["E64"]).abs().sum() / 2)
            gw_pts = w.index.map(lambda i, gw=gw: pts.get((i, gw), 0))
            row["delta_ae_minus_e"] = round(((w["AE64"] - w["E64"]) * gw_pts).sum(), 1)
        rows.append(row)
    return pd.DataFrame(rows)


def flows(meta: pd.DataFrame, gw_points: pd.DataFrame) -> pd.DataFrame:
    """Net transfers in (managers and % of group) per player and GW, vs points in the two GWs before."""
    moves = meta[meta["table"].isin(["transfer_in", "transfer_out"])]
    net = moves.assign(signed=np.where(moves["table"] == "transfer_in", 1, -1) * moves["count"])
    net = net.pivot_table(index=["gw", "fpl_id"], columns="group", values="signed", aggfunc="sum", fill_value=0).reset_index()
    size = meta[meta["table"] == "chip_active"].groupby(["gw", "group"])["count"].sum().unstack().reindex(range(1, 39)).ffill()
    rows = []
    for gw in range(2, int(meta["gw"].max()) + 1):
        played = gw_points[(gw_points["gw"] == gw - 1) & (gw_points["mins"] > 0)][["fpl_id", "pts"]]
        before = gw_points[gw_points["gw"] == gw - 2][["fpl_id", "pts"]].rename(columns={"pts": "pts2"})
        f = played.merge(net[net["gw"] == gw].drop(columns="gw"), on="fpl_id", how="left").merge(before, on="fpl_id", how="left")
        rows.append(f.fillna({g: 0 for g in GROUPS} | {"pts2": 0}).assign(gw=gw))
    fl = pd.concat(rows, ignore_index=True)
    for g in GROUPS:
        fl[f"{g.lower()}_net_pct"] = 100 * fl[g] / fl["gw"].map(size[g])
    fl["bucket"] = pd.cut(fl["pts"], [-10, 2, 5, 9, 14, 99], labels=["<=2", "3-5", "6-9", "10-14", "15+"])
    return fl


def main(season: str = "2025-26") -> None:
    meta, eo = load_meta(season=season), load_eo(season=season)
    merged = historical.merged_gw(season)
    gw_points = merged.groupby(["element", "round"]).agg(pts=("total_points", "sum"), mins=("minutes", "sum")).reset_index()
    gw_points = gw_points.rename(columns={"element": "fpl_id", "round": "gw"})
    pts = gw_points.set_index(["fpl_id", "gw"])["pts"]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    weekly_summary(meta, eo, pts).to_csv(OUT_DIR / f"weekly_summary_{season}.csv", index=False)
    fl = flows(meta, gw_points)
    fl.to_csv(OUT_DIR / f"flows_player_gw_{season}.csv", index=False)
    by_points = fl.groupby("bucket", observed=True).agg(
        n=("pts", "size"),
        ae_net=("ae64_net_pct", "mean"),
        e_net=("e64_net_pct", "mean"),
        ae_big=("ae64_net_pct", lambda x: (x >= 10).mean()),
        e_big=("e64_net_pct", lambda x: (x >= 10).mean()),
    )
    by_points.round(3).to_csv(OUT_DIR / f"flow_by_prev_points_{season}.csv")
    print(by_points.round(3))

    moves = meta[meta["table"].isin(["transfer_in", "transfer_out"])]
    piles = moves.assign(signed=np.where(moves["table"] == "transfer_in", 1, -1) * moves["count"])
    piles = piles.pivot_table(index=["gw", "item", "fpl_id"], columns="group", values="signed", aggfunc="sum", fill_value=0).reset_index()
    for lag, name in ((2, "pts_prev2"), (1, "pts_prev"), (0, "pts_this")):
        piles[name] = [pts.get((i, gw - lag), np.nan) for i, gw in zip(piles["fpl_id"], piles["gw"], strict=True)]
    piles["both"] = piles["AE64"] + piles["E64"]
    top = piles.sort_values("both", ascending=False).head(25)
    top.to_csv(OUT_DIR / f"top_pileins_{season}.csv", index=False)
    print(top[["gw", "item", "AE64", "E64", "pts_prev2", "pts_prev", "pts_this"]].to_string(index=False))
    print(f"Wrote {OUT_DIR}")


if __name__ == "__main__":
    main(*sys.argv[1:])
