"""The page's weekly setup: latest code, the team from his bookmarklet and the Solio files (steps 1-3 of
docs/weekly-run.md), so none of them needs PowerShell. No modelling here."""

import json
import re
import subprocess
import time
from datetime import date
from pathlib import Path

from fplrank.paths import PROJECT_ROOT, PROJECTIONS_DIR, UPSTREAM_DIR

TEAM_JSON = UPSTREAM_DIR / "data" / "team.json"  # where his bookmarklet's team goes (--team_data json)
SOLIO_CSV = UPSTREAM_DIR / "data" / "solio.csv"  # the projections his solver reads (datasource solio)
SOLIO_EO_DIR = PROJECTIONS_DIR / "solio_eo"  # Solio's EO forecast; opt.ownership.load_solio_eo reads the newest
DOWNLOADS = Path.home() / "Downloads"
RECENT_DAYS = 7  # a Downloads CSV older than this is not this week's


def csv_kind(header: str) -> tuple[str, list[int]] | None:
    """Which Solio export a CSV header line is, and its GWs: ("projections", [8, 9, ...]) for the projections
    (`Pos,ID,Name,...,8_xMins,...,8_Pts,...`), ("eo", [8, ...]) for the EO forecast (`Name,Team,...,GW8 EO %`),
    None for anything else."""
    cols = [c.strip().strip('"') for c in header.lstrip("\ufeff").strip().split(",")]
    if "ID" in cols and (gws := [int(m[1]) for c in cols if (m := re.fullmatch(r"(\d+)_Pts", c))]):
        return "projections", gws
    if {"Name", "Team"} <= set(cols) and (gws := [int(m[1]) for c in cols if (m := re.fullmatch(r"GW(\d+) EO %", c))]):
        return "eo", gws
    return None


def file_kind(path: Path) -> tuple[str, list[int]] | None:
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            return csv_kind(f.readline())
    except OSError:
        return None


def newest_downloads(folder: Path = DOWNLOADS, days: float = RECENT_DAYS) -> dict[str, Path]:
    """The newest recent projections and EO exports in `folder`, found by their columns, not their names
    (Solio's names vary: `projection (9).csv`)."""
    found: dict[str, Path] = {}
    cutoff = time.time() - days * 86400
    try:
        csvs = [p for p in folder.glob("*.csv") if p.stat().st_mtime >= cutoff]
    except OSError:
        return found
    for path in sorted(csvs, key=lambda p: p.stat().st_mtime, reverse=True):
        if (kind := file_kind(path)) and kind[0] not in found:
            found[kind[0]] = path
    return found


def install(data: bytes, today: date | None = None) -> tuple[str, list[int], Path]:
    """Put a Solio export where it is read: projections over solio.csv, the EO forecast as
    solio_eo/EO_GWxx_yyyymmdd.csv (xx its first GW). Raises ValueError for any other file."""
    kind = csv_kind(data.decode("utf-8", errors="replace").split("\n", 1)[0])
    if kind is None:
        raise ValueError("not a Solio projections or EO export (no ID and n_Pts, or GWn EO % columns)")
    name, gws = kind
    if name == "projections":
        dest = SOLIO_CSV
    else:
        dest = SOLIO_EO_DIR / f"EO_GW{min(gws):02d}_{(today or date.today()):%Y%m%d}.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return name, gws, dest


def save_team(text: str) -> dict:
    """Save what his bookmarklet copied as team.json (no byte-order mark, which his solver can't read).
    Raises ValueError if it isn't his team data."""
    if not text.strip():
        raise ValueError("nothing pasted: click the bookmarklet on the FPL site, then paste here (Ctrl+V)")
    try:
        team = json.loads(text.strip().lstrip("\ufeff"))
    except json.JSONDecodeError as e:
        raise ValueError(f"not JSON ({e.msg}): copy it again with the bookmarklet") from None
    if not isinstance(team, dict) or not team.get("picks"):
        raise ValueError('not the team data: it should start with {"picks": [')
    TEAM_JSON.parent.mkdir(parents=True, exist_ok=True)
    TEAM_JSON.write_text(json.dumps(team), encoding="utf-8")
    return team


def team_summary(team: dict) -> str:
    bank = (team.get("transfers") or {}).get("bank")
    return f"{len(team['picks'])} players" + (f", £{bank / 10:.1f}m in the bank" if bank is not None else "")


def git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")


def code_version() -> str:
    """The commit the page is running, e.g. `Merge pull request #51 ... (2026-10-13)`."""
    out = git("log", "-1", "--format=%s (%cs)")
    return out.stdout.strip() if out.returncode == 0 else "unknown (git not found)"


def update_code() -> tuple[bool, str]:
    """`git pull --ff-only` on main (never a merge; a branch checked out to try a PR is left alone).
    Returns whether the code changed, and what git said."""
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch != "main":
        return False, f'On branch "{branch}", not main: not updating.'
    before = git("rev-parse", "HEAD").stdout.strip()
    pull = git("pull", "--ff-only")
    after = git("rev-parse", "HEAD").stdout.strip()
    return before != after, (pull.stdout + pull.stderr).strip()


def age(path: Path) -> str | None:
    """`3 h ago` / `2 days ago` for a file, None if there is none."""
    try:
        hours = (time.time() - path.stat().st_mtime) / 3600
    except OSError:
        return None
    if hours < 1:
        return "just now"
    return f"{hours:.0f} h ago" if hours < 48 else f"{hours / 24:.0f} days ago"
