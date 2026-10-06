"""Points variance by position and projection band (S2b): v(xP) for S2's σ² = s² x Σ (m - EO)² x v(xP).

Projection sources aren't on one scale (FPL `ep_next`/vaastav `xP` vs Solio), so players are banded by
their **within-source quantile** of xP, not raw xP (critical review, 2026-10-06). The table is built
from past seasons where FPL's own xP is the projection:

- 2023-24, 2024-25: vaastav `xP` (FPL's `ep_this`, filled for every GW);
- 2025-26: FPL-Core-Insights `ep_next` (gw = N row; D1), since vaastav `xP` is blank for 27 GWs. First
  season with defensive contribution points.

Rows are player-GWs (double GWs summed). Band 0 = xP below 0.1 (not expected to play; FPL gives
these exactly 0, Solio tiny positive values); bands 1..N_BANDS are quantiles of xP among the rest,
per season. To use the table with another source (e.g. Solio for
the coming GW), band that source's xP the same way (`bands`) and look up (pos, band).
"""

import numpy as np
import pandas as pd

N_BANDS = 10
MIN_XP = 0.1
SEASONS = ("2023-24", "2024-25", "2025-26")
POS = {"GK": "G", "GKP": "G", "DEF": "D", "MID": "M", "FWD": "F"}


def bands(xp: pd.Series, n_bands: int = N_BANDS) -> pd.Series:
    """Band of each xP: 0 if xP < MIN_XP, else 1..n_bands by quantile among the rest."""
    out = pd.Series(0, index=xp.index, dtype="int64")
    pos = xp >= MIN_XP
    if pos.any():
        out[pos] = np.ceil(xp[pos].rank(method="first", pct=True) * n_bands).astype("int64")
    return out


def season_rows(season: str) -> pd.DataFrame:
    """`season, gw, fpl_id, pos, xp, pts` for one season (player-GW, doubles summed, assistant managers dropped)."""
    from fplrank.data import core_insights, historical

    m = historical.merged_gw(season)
    m = m[m["position"].isin(POS)]
    rows = m.groupby(["GW", "element"]).agg(pos=("position", "first"), pts=("total_points", "sum"), xp=("xP", "sum")).reset_index()
    rows = rows.rename(columns={"GW": "gw", "element": "fpl_id"})
    rows["pos"] = rows["pos"].map(POS)
    if season == "2025-26":
        ep = core_insights.xp_from_ep_next(season).set_index(["gw", "fpl_id"])["xp"]
        rows["xp"] = [ep.get((g, p), np.nan) for g, p in zip(rows["gw"], rows["fpl_id"], strict=True)]
        rows = rows[rows["gw"] > 1].dropna(subset=["xp"])  # GW1 ep_next is unreliable (data-log)
    return rows.assign(season=season)[["season", "gw", "fpl_id", "pos", "xp", "pts"]]


def variance_table(rows: pd.DataFrame, n_bands: int = N_BANDS) -> pd.DataFrame:
    """`pos, band, n, xp_mean, pts_mean, pts_var` with bands made within each season."""
    rows = rows.copy()
    rows["band"] = rows.groupby("season", group_keys=False)["xp"].apply(lambda s: bands(s, n_bands))
    table = rows.groupby(["pos", "band"]).agg(n=("pts", "size"), xp_mean=("xp", "mean"), pts_mean=("pts", "mean"), pts_var=("pts", "var"))
    return table.reset_index()


def build(seasons=SEASONS) -> pd.DataFrame:
    return variance_table(pd.concat([season_rows(s) for s in seasons], ignore_index=True))


def lookup(table: pd.DataFrame, pos: pd.Series, xp: pd.Series) -> pd.Series:
    """v(xP) for players of one source and GW: band `xp` within itself, then read (pos, band)."""
    key = pd.MultiIndex.from_arrays([pos, bands(xp, int(table["band"].max()))])
    return pd.Series(table.set_index(["pos", "band"])["pts_var"].reindex(key).to_numpy(), index=xp.index)
