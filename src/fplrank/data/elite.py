"""Effective ownership (EO) of elite manager groups, from the committed datasets/elite_ownership/.

Each source/season has two wide CSVs (see datasets/README.md):

- `<source>_eo_<season>.csv`: one row per listed player per GW, one `<group>_eo` column per manager
  group, EO in percent.
- `<source>_meta_<season>.csv`: `season, gw, table, item` plus one manager-count column per group
  (captains, chips, free transfers, hits, transfers in/out).

The loaders return long tables with a `group` column, so new sources and groups need no code changes.

Sources only list the top players per position. An unlisted player's EO is censored (somewhere below
the listing cutoff), not zero. `eo_panel` fills unlisted players by spreading each group's residual EO
(expected total minus listed total) in proportion to overall FPL ownership, capped at the cutoff.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from fplrank.paths import DATASETS_DIR

ELITE_DIR = DATASETS_DIR / "elite_ownership"
PLAYER_COLS = ["fpl_id", "player", "team", "pos"]
META_KEYS = ["season", "gw", "table", "item"]
POS_BY_ELEMENT_TYPE = {1: "G", 2: "D", 3: "M", 4: "F"}


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


def expected_totals(meta: pd.DataFrame) -> pd.Series:
    """Expected total EO per (group, gw): 11 starters + 1 captain + TC share + 4 x BB share.

    Shares are chip_active counts over the group size (the chip_active rows partition the group).
    """
    chips = meta[meta["table"] == "chip_active"].pivot_table(index=["group", "gw"], columns="item", values="count", aggfunc="sum")
    chips = chips.reindex(columns=sorted(set(chips.columns) | {"TC", "BB"}), fill_value=0).fillna(0)
    size = chips.sum(axis=1)
    return (12 + chips["TC"] / size + 4 * chips["BB"] / size).rename("expected_total")


def expected_total_eo(group: str, gw: int, *, source: str = "elite64", season: str = "2026-27", meta: pd.DataFrame | None = None) -> float:
    """Expected total EO for one group and GW, as a fraction (12.0 = 1200%). See `expected_totals`."""
    totals = expected_totals(load_meta(source, season) if meta is None else meta)
    return float(totals.loc[(group, gw)])


def universe_from_bootstrap(bootstrap: dict) -> pd.DataFrame:
    """Every FPL player from a bootstrap-static payload: `fpl_id, player, team, pos, ownership` (fraction)."""
    teams = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    return pd.DataFrame(
        {
            "fpl_id": e["id"],
            "player": e["web_name"],
            "team": teams.get(e["team"]),
            "pos": POS_BY_ELEMENT_TYPE[e["element_type"]],
            "ownership": float(e["selected_by_percent"]) / 100,
        }
        for e in bootstrap["elements"]
    ).astype({"fpl_id": "Int64"})


def _default_universe() -> pd.DataFrame:
    from fplrank.data.fpl_api import latest_snapshot

    try:
        return universe_from_bootstrap(latest_snapshot("bootstrap-static/"))
    except FileNotFoundError as e:
        raise FileNotFoundError(
            "eo_panel needs the FPL player list: save a snapshot with FplApi().bootstrap() or pass universe=universe_from_bootstrap(...)"
        ) from e


def _water_fill(amount: float, weights: np.ndarray, caps: np.ndarray) -> np.ndarray:
    """Split `amount` in proportion to `weights` with no share above its cap; capped excess goes to the rest."""
    alloc = np.zeros(len(weights))
    free = caps > 0
    remaining = amount
    while remaining > 1e-12 and free.any():
        w = np.where(free, weights, 0.0)
        if w.sum() == 0:  # nobody left with ownership: spread evenly
            w = free.astype(float)
        give = np.minimum(remaining * w / w.sum(), caps - alloc)
        alloc += give
        remaining -= give.sum()
        free &= caps - alloc > 1e-12
    return alloc


def eo_panel(
    groups=None,
    gws=None,
    players=None,
    *,
    universe: pd.DataFrame | None = None,
    source: str = "elite64",
    season: str = "2026-27",
    eo: pd.DataFrame | None = None,
    meta: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Complete group x GW x player EO table: `season, group, gw, fpl_id, player, team, pos, eo, censored, fill_method`.

    Listed players keep their EO (`fill_method="listed"`). For each group/GW, the residual
    `expected_total - listed total` (clipped at 0) is spread over every unlisted player in `universe`
    in proportion to `ownership`, each capped at the smallest positive listed EO for their position,
    with capped excess passed on (`fill_method="residual"`, `censored=True`).

    `universe` is every player that could be owned: `fpl_id, pos, ownership` (+ optional `player`,
    `team`), defaulting to the latest saved bootstrap-static snapshot. Missing ownership values get
    the mean; with no ownership at all the residual is spread evenly. Listed players are always
    included. `players` (FPL ids) filters the output after filling, so totals stay meaningful.
    Pass `eo` / `meta` (from `load_eo` / `load_meta`) to skip reading files.
    """
    eo = load_eo(source, season) if eo is None else eo
    meta = load_meta(source, season) if meta is None else meta
    universe = _default_universe() if universe is None else universe
    if eo["season"].nunique() != 1:
        raise ValueError("eo_panel needs a single season")
    groups = sorted(eo["group"].unique()) if groups is None else list(dict.fromkeys(groups))
    gws = sorted(eo["gw"].unique()) if gws is None else list(dict.fromkeys(gws))
    # An unknown group or GW would come back fully filled, which looks like real data
    if missing := set(groups) - set(eo["group"]):
        raise ValueError(f"Groups not in the data: {sorted(missing)}")
    if missing := set(gws) - set(eo["gw"]):
        raise ValueError(f"GWs not in the data: {sorted(missing)}")

    # Player universe: given players plus everyone ever listed; names from the latest listing first
    listed_players = eo.sort_values("gw").drop_duplicates("fpl_id", keep="last")[PLAYER_COLS]
    uni = universe.astype({"fpl_id": "Int64"}).drop_duplicates("fpl_id").set_index("fpl_id")
    uni = listed_players.set_index("fpl_id").combine_first(uni.reindex(columns=["player", "team", "pos", "ownership"]))
    own = uni["ownership"].astype(float)
    uni["ownership"] = own.fillna(own.mean()).fillna(0)
    uni = uni.reset_index()
    if players is not None and (unknown := set(players) - set(uni["fpl_id"])):
        raise ValueError(f"Players not in the universe or the listings: {sorted(unknown)}")

    totals = expected_totals(meta)
    blocks = []
    for group in groups:
        for gw in gws:
            listed = eo[(eo["group"] == group) & (eo["gw"] == gw)].set_index("fpl_id")["eo"]
            block = uni.copy()
            block["group"], block["gw"] = group, gw
            block["censored"] = ~block["fpl_id"].isin(listed.index)
            block["eo"] = block["fpl_id"].map(listed).astype(float)

            positive = eo[(eo["group"] == group) & (eo["gw"] == gw) & (eo["eo"] > 0)]
            cutoff = positive.groupby("pos")["eo"].min()
            unl = block["censored"].to_numpy()
            caps = block.loc[unl, "pos"].map(cutoff).fillna(positive["eo"].min()).to_numpy(float)
            residual = max(totals.loc[(group, gw)] - listed.sum(), 0.0)
            block.loc[unl, "eo"] = _water_fill(residual, block.loc[unl, "ownership"].to_numpy(float), caps)
            blocks.append(block)

    panel = pd.concat(blocks, ignore_index=True)
    panel["fill_method"] = np.where(panel["censored"], "residual", "listed")
    panel.insert(0, "season", eo["season"].iloc[0])
    if players is not None:
        panel = panel[panel["fpl_id"].isin(list(players))]
    cols = ["season", "group", "gw", *PLAYER_COLS, "eo", "censored", "fill_method"]
    return panel[cols].sort_values(["group", "gw", "fpl_id"], ignore_index=True)
