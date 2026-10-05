"""Historical FPL data from github.com/vaastav/Fantasy-Premier-League.

This is the main source for backtesting: per-season player snapshots, fixtures and
gameweek-by-gameweek results (points, minutes, prices, ownership). Files are downloaded
once and cached under data/raw/vaastav/<season>/.
"""

from pathlib import Path

import pandas as pd
import requests

from fplrank.paths import RAW_DIR

VAASTAV_BASE = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/master/data"


def season_file(season: str, relpath: str, refresh: bool = False) -> Path:
    """Return a local path to `relpath` for `season` (e.g. "2025-26"), downloading it if needed."""
    target = RAW_DIR / "vaastav" / season / relpath
    if target.exists() and not refresh:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    response = requests.get(f"{VAASTAV_BASE}/{season}/{relpath}", timeout=60)
    response.raise_for_status()
    target.write_bytes(response.content)
    return target


def players_raw(season: str, refresh: bool = False) -> pd.DataFrame:
    """One row per player with FPL `elements` fields as of the last repo update."""
    return pd.read_csv(season_file(season, "players_raw.csv", refresh))


def teams(season: str, refresh: bool = False) -> pd.DataFrame:
    return pd.read_csv(season_file(season, "teams.csv", refresh))


def fixtures(season: str, refresh: bool = False) -> pd.DataFrame:
    return pd.read_csv(season_file(season, "fixtures.csv", refresh))


def merged_gw(season: str, refresh: bool = False) -> pd.DataFrame:
    """One row per player per fixture: points, minutes, price (`value`), ownership (`selected`)."""
    return pd.read_csv(season_file(season, "gws/merged_gw.csv", refresh))
