"""Per-GW player data from FPL-Core-Insights (D1).

github.com/olbauday/FPL-Core-Insights (free CSVs, refreshed twice a day; the author asks for a link
back) keeps a snapshot of every player's FPL `elements` record per GW: `ep_next`, `ep_this`,
`selected_by_percent`, transfers in/out and more. vaastav stopped weekly updates, and its 2025-26 `xP`
is blank for 27 GWs, so this is our source of FPL's own expected points for every past GW.

Note that `ep_next` is FPL's form-based estimate, not a projection (docs/data-log.md, 2026-10-06);
vaastav `xP` is the same measure. Use it as a like-for-like xP across seasons, not for decisions.

Files are downloaded once and cached under data/raw/core_insights/<season>/ (git-ignored).
"""

from pathlib import Path

import pandas as pd
import requests

from fplrank.paths import RAW_DIR

BASE_URL = "https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/main/data"
COLUMNS = [
    "gw",
    "fpl_id",
    "ep_next",
    "ep_this",
    "selected_by_percent",
    "transfers_in_event",
    "transfers_out_event",
    "now_cost",
    "status",
]


def _season_dir(season: str) -> str:
    """'2025-26' -> '2025-2026' (the repo's folder names)."""
    start = int(season[:4])
    return f"{start}-{start + 1}"


def season_file(season: str, relpath: str = "playerstats.csv", refresh: bool = False) -> Path:
    target = RAW_DIR / "core_insights" / _season_dir(season) / relpath
    if target.exists() and not refresh:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(f"{BASE_URL}/{_season_dir(season)}/{relpath}", timeout=120)
    response.raise_for_status()
    target.write_bytes(response.content)
    return target


def tidy_playerstats(raw: pd.DataFrame) -> pd.DataFrame:
    """Raw playerstats rows -> `gw, fpl_id, ep_next, ep_this, selected_by_percent, transfers_in_event,
    transfers_out_event, now_cost (£m), status`, one row per player per GW."""
    df = raw.rename(columns={"id": "fpl_id"})
    df = df.drop_duplicates(["gw", "fpl_id"], keep="last")
    for col in ("ep_next", "ep_this", "selected_by_percent", "now_cost"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("transfers_in_event", "transfers_out_event"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype("int64")
    df = df.astype({"gw": "int64", "fpl_id": "int64"})
    return df[COLUMNS].sort_values(["gw", "fpl_id"], ignore_index=True)


def playerstats(season: str, refresh: bool = False) -> pd.DataFrame:
    return tidy_playerstats(pd.read_csv(season_file(season, refresh=refresh), low_memory=False))


def xp_from_ep_next(season: str, stats: pd.DataFrame | None = None) -> pd.DataFrame:
    """FPL's expected points for each player and GW: `gw, fpl_id, xp` = `ep_next` from the gw = N row.

    Checked against vaastav `xP` for 2025-26 (docs/data-log.md): the gw = N row matches GW N best
    (correlation 0.92-0.97 from GW2 on; GW1 only 0.40, so treat GW1 as unreliable).
    """
    stats = playerstats(season) if stats is None else stats
    return stats[["gw", "fpl_id", "ep_next"]].rename(columns={"ep_next": "xp"}).dropna(subset=["xp"]).reset_index(drop=True)
