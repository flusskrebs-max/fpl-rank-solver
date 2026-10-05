"""Effective ownership (EO) of elite manager groups, from the committed datasets/elite_ownership/.

Each source/season has two wide CSVs (see datasets/README.md):

- `<source>_eo_<season>.csv`: one row per listed player per GW, one `<group>_eo` column per manager
  group, EO in percent.
- `<source>_meta_<season>.csv`: `season, gw, table, item` plus one manager-count column per group
  (captains, chips, free transfers, hits, transfers in/out).

The loaders return long tables with a `group` column, so new sources and groups need no code changes.

Sources only list the top players per position. An unlisted player's EO is censored (somewhere below
the listing cutoff), not zero: `eo_panel` fills them with a floor and flags them `censored`.
"""

from pathlib import Path

import pandas as pd

from fplrank.paths import DATASETS_DIR

ELITE_DIR = DATASETS_DIR / "elite_ownership"
PLAYER_COLS = ["fpl_id", "player", "team", "pos"]
META_KEYS = ["season", "gw", "table", "item"]


def _path(kind: str, source: str, season: str) -> Path:
    path = ELITE_DIR / f"{source}_{kind}_{season}.csv"
    if not path.exists():
        raise FileNotFoundError(f"No elite {kind} file for source={source!r}, season={season!r} (looked for {path})")
    return path


def available() -> list[tuple[str, str]]:
    """(source, season) pairs that have an EO file, e.g. [("elite64", "2026-27")]."""
    return sorted(tuple(p.stem.split("_eo_")) for p in ELITE_DIR.glob("*_eo_*.csv"))


def load_eo(source: str = "elite64", season: str = "2026-27") -> pd.DataFrame:
    """Listed players' EO, long: `season, gw, group, fpl_id, player, team, pos, eo` (eo 1.0 = 100%)."""
    wide = pd.read_csv(_path("eo", source, season))
    eo_cols = [c for c in wide.columns if c.endswith("_eo")]
    long = wide.melt(id_vars=["season", "gw", *PLAYER_COLS], value_vars=eo_cols, var_name="group", value_name="eo")
    long["group"] = long["group"].str.removesuffix("_eo").str.upper()
    long["fpl_id"] = long["fpl_id"].astype("Int64")
    long["eo"] = long["eo"] / 100
    return long[["season", "gw", "group", *PLAYER_COLS, "eo"]].sort_values(["group", "gw"], kind="stable", ignore_index=True)


def load_meta(source: str = "elite64", season: str = "2026-27") -> pd.DataFrame:
    """Manager counts, long: `season, gw, group, table, item, count`.

    `item` is always a string ("WC", "0", "-4", a player name...). The blank `chip_active` item
    (managers playing no chip) becomes "none".
    """
    wide = pd.read_csv(_path("meta", source, season), dtype={"item": str}, keep_default_na=False)
    wide.loc[(wide["table"] == "chip_active") & (wide["item"] == ""), "item"] = "none"
    group_cols = [c for c in wide.columns if c not in META_KEYS]
    long = wide.melt(id_vars=META_KEYS, value_vars=group_cols, var_name="group", value_name="count")
    long["group"] = long["group"].str.upper()
    return long[["season", "gw", "group", "table", "item", "count"]].sort_values(["group", "gw"], kind="stable", ignore_index=True)


def eo_panel(
    groups=None,
    gws=None,
    players=None,
    floor: float = 0.025,
    *,
    source: str = "elite64",
    season: str = "2026-27",
    eo: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Complete group x GW x player EO table: `season, group, gw, fpl_id, player, team, pos, eo, censored`.

    Players not listed for a group/GW get `eo = floor` and `censored = True` (their EO is below the
    source's listing cutoff, not zero). Defaults: all groups and GWs in the data, and every player
    listed at least once in them. `players` are FPL ids; ids never listed get NaN name columns.
    Pass `eo` (a `load_eo` table) to skip reading the file.
    """
    if eo is None:
        eo = load_eo(source, season)
    if eo["season"].nunique() != 1:
        raise ValueError("eo_panel needs a single season")
    groups = sorted(eo["group"].unique()) if groups is None else list(dict.fromkeys(groups))
    gws = sorted(eo["gw"].unique()) if gws is None else list(dict.fromkeys(gws))
    # An unknown group or GW would come back fully censored, which looks like real data
    if missing := set(groups) - set(eo["group"]):
        raise ValueError(f"Groups not in the data: {sorted(missing)}")
    if missing := set(gws) - set(eo["gw"]):
        raise ValueError(f"GWs not in the data: {sorted(missing)}")

    listed = eo[eo["group"].isin(groups) & eo["gw"].isin(gws)]
    players = sorted(listed["fpl_id"].unique()) if players is None else list(dict.fromkeys(players))
    grid = pd.MultiIndex.from_product([groups, gws, players], names=["group", "gw", "fpl_id"]).to_frame(index=False)
    grid["fpl_id"] = grid["fpl_id"].astype("Int64")

    panel = grid.merge(listed[["group", "gw", "fpl_id", "eo"]], on=["group", "gw", "fpl_id"], how="left", validate="one_to_one")
    panel["censored"] = panel["eo"].isna()
    panel["eo"] = panel["eo"].fillna(floor)
    # Latest listing wins for name/team/pos (players can change club mid-season)
    names = eo.sort_values("gw").drop_duplicates("fpl_id", keep="last").set_index("fpl_id")[["player", "team", "pos"]]
    panel = panel.join(names, on="fpl_id")
    panel.insert(0, "season", eo["season"].iloc[0])
    return panel[["season", "group", "gw", *PLAYER_COLS, "eo", "censored"]]
