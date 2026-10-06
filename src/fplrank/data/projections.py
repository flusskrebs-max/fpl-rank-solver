"""Projection files: load them into one long shape and keep a registry of when each was made.

Solio exports look like `Pos, ID, Name, BV, SV, Team, {gw}_xMins..., {gw}_Pts...` (means only).
A file's vintage is the GW it was made for, i.e. its first `_Pts` column: pre-season files start
at GW1, a file made before GW6 starts at GW6.

Projection files are paid data. They live under data/projections/ (git-ignored) and must never be
committed. `register` copies a download to `data/projections/solio/GW{vintage:02d}_{yyyymmdd}.csv`
and appends a row to `data/projections/registry.csv`.

CLI:
    uv run python -m fplrank.data.projections register <file> [<file> ...]
    uv run python -m fplrank.data.projections check-ids [<file> ...]   # default: all registered
"""

import argparse
import hashlib
import re
import shutil
import unicodedata
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from fplrank.paths import PROJECTIONS_DIR

SOLIO_BASE_COLS = ["Pos", "ID", "Name", "BV", "Team"]
REGISTRY_COLS = ["file", "original", "vintage_gw", "first_gw", "last_gw", "n_players", "downloaded", "sha256", "registered"]
LONG_COLS = ["vintage_gw", "gw", "fpl_id", "name", "team", "pos", "price", "xmins", "xpts"]
POS_BY_ELEMENT_TYPE = {1: "G", 2: "D", 3: "M", 4: "F"}
_GW_COL = re.compile(r"^(\d+)_(xMins|Pts)$")


def load_solio(path) -> pd.DataFrame:
    """Solio export as one row per player per GW: `vintage_gw, gw, fpl_id, name, team, pos, price, xmins, xpts`.

    `price` is the buy value (BV) in £m; `vintage_gw` is the first projected GW.
    """
    wide = pd.read_csv(path, encoding="utf-8-sig")  # exports start with a byte-order mark
    if missing := [c for c in SOLIO_BASE_COLS if c not in wide.columns]:
        raise ValueError(f"{path}: not a Solio export, missing columns {missing}")
    gw_cols = {c: _GW_COL.match(c) for c in wide.columns}
    gw_cols = {c: (int(m[1]), m[2]) for c, m in gw_cols.items() if m}
    pts_gws = sorted(gw for gw, kind in gw_cols.values() if kind == "Pts")
    mins_gws = sorted(gw for gw, kind in gw_cols.values() if kind == "xMins")
    if not pts_gws or pts_gws != mins_gws:
        raise ValueError(f"{path}: expected matching {{gw}}_xMins and {{gw}}_Pts columns, got Pts {pts_gws} and xMins {mins_gws}")
    if wide["ID"].duplicated().any():
        raise ValueError(f"{path}: duplicate player IDs {wide.loc[wide['ID'].duplicated(), 'ID'].tolist()}")

    long = wide.melt(id_vars=SOLIO_BASE_COLS, value_vars=list(gw_cols), var_name="col")
    long["gw"] = long["col"].map(lambda c: gw_cols[c][0])
    long["kind"] = long["col"].map(lambda c: gw_cols[c][1])
    long = long.pivot(index=[*SOLIO_BASE_COLS, "gw"], columns="kind", values="value").reset_index()
    long = long.rename(
        columns={"ID": "fpl_id", "Name": "name", "Team": "team", "Pos": "pos", "BV": "price", "xMins": "xmins", "Pts": "xpts"}
    )
    long["vintage_gw"] = pts_gws[0]
    return long[LONG_COLS].sort_values(["gw", "fpl_id"], ignore_index=True)


def from_ep_next(bootstrap: dict, fixtures: list[dict], horizon: int) -> pd.DataFrame:
    """Free fallback projections in the upstream/Solio wide format, from FPL's own `ep_next`.

    Crude on purpose (S1b): `ep_next` is FPL's one-GW expectation for the next GW (it tracks vaastav `xP`
    closely; docs/research/data-sources.md). Later GWs repeat it per fixture (0 for a blank, x2 for a
    double), so it knows nothing about fixture difficulty, rotation or injuries beyond the next GW. xMins
    = 90 x the player's share of possible minutes so far x chance of playing (if given), per fixture.
    """
    next_gw = next(e["id"] for e in bootstrap["events"] if e["is_next"])
    gws = [gw for gw in range(next_gw, next_gw + horizon) if gw <= 38]
    played = sum(1 for e in bootstrap["events"] if e["id"] < next_gw)
    n_fix = pd.DataFrame(
        [(f["event"], t) for f in fixtures if f["event"] in gws for t in (f["team_h"], f["team_a"])], columns=["gw", "team"]
    )
    n_fix = n_fix.value_counts().to_dict()
    teams = {t["id"]: t["name"] for t in bootstrap["teams"]}
    rows = []
    for e in bootstrap["elements"]:
        ep = float(e["ep_next"] or 0)
        n_next = n_fix.get((next_gw, e["team"]), 0)
        per_fixture = ep / n_next if n_next else ep
        share = min(1.0, e["minutes"] / (90 * played)) if played else 1.0
        chance = e["chance_of_playing_next_round"]
        xmins = 90 * share * (1.0 if chance is None else chance / 100)
        price = e["now_cost"] / 10
        row = {
            "Pos": POS_BY_ELEMENT_TYPE[e["element_type"]],
            "ID": e["id"],
            "Name": e["web_name"],
            "BV": price,
            "SV": price,
            "Team": teams[e["team"]],
        }
        for gw in gws:
            row[f"{gw}_xMins"] = round(xmins * n_fix.get((gw, e["team"]), 0), 2)
        for gw in gws:
            row[f"{gw}_Pts"] = round(per_fixture * n_fix.get((gw, e["team"]), 0), 2)
        rows.append(row)
    return pd.DataFrame(rows)


def read_registry(projections_dir: Path | None = None) -> pd.DataFrame:
    projections_dir = projections_dir or PROJECTIONS_DIR
    path = projections_dir / "registry.csv"
    if not path.exists():
        return pd.DataFrame(columns=REGISTRY_COLS)
    return pd.read_csv(path, dtype={"file": str, "original": str, "sha256": str})


def register(path, downloaded: datetime | None = None, projections_dir: Path | None = None) -> pd.Series:
    """Copy a Solio export into the projection store and add it to the registry.

    `downloaded` defaults to the file's modified time (the download time for a browser download).
    A file whose sha256 is already registered is skipped and its existing registry row returned.
    """
    projections_dir = projections_dir or PROJECTIONS_DIR
    path = Path(path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    registry = read_registry(projections_dir)
    if sha in set(registry["sha256"]):
        return registry[registry["sha256"] == sha].iloc[0]

    proj = load_solio(path)  # validates before anything is copied
    gws = sorted(proj["gw"].unique())
    downloaded = downloaded or datetime.fromtimestamp(path.stat().st_mtime)
    stem = f"GW{gws[0]:02d}_{downloaded:%Y%m%d}"
    target = projections_dir / "solio" / f"{stem}.csv"
    n = 2
    while target.exists():  # a different file for the same vintage and day
        target = target.with_name(f"{stem}_{n}.csv")
        n += 1
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)

    row = pd.Series(
        {
            "file": target.relative_to(projections_dir).as_posix(),
            "original": path.name,
            "vintage_gw": gws[0],
            "first_gw": gws[0],
            "last_gw": gws[-1],
            "n_players": proj["fpl_id"].nunique(),
            "downloaded": downloaded.isoformat(timespec="minutes"),
            "sha256": sha,
            "registered": date.today().isoformat(),
        }
    )
    registry = pd.concat([registry, row.to_frame().T], ignore_index=True) if len(registry) else row.to_frame().T
    registry.to_csv(projections_dir / "registry.csv", index=False)
    return row


def latest(gw: int, projections_dir: Path | None = None) -> Path:
    """Path of the newest registered projection made at or before `gw` (highest vintage, then latest download)."""
    projections_dir = projections_dir or PROJECTIONS_DIR
    registry = read_registry(projections_dir)
    usable = registry[registry["vintage_gw"].astype(int) <= gw]
    if usable.empty:
        raise LookupError(f"No registered projection with vintage GW{gw} or earlier in {projections_dir}")
    best = usable.sort_values(["vintage_gw", "downloaded"]).iloc[-1]
    return projections_dir / best["file"]


def _normalise(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode().lower().strip()
    return re.sub(r"^[a-z]\.\s*", "", ascii_name)  # FPL adds initials to tell namesakes apart ("I.Sangaré")


def id_report(proj: pd.DataFrame, bootstrap: dict) -> pd.DataFrame:
    """Players whose `fpl_id` does not line up with FPL's bootstrap-static data.

    `issue` is "missing" (id not in FPL), "name" (web_name differs, ignoring accents, case and a
    leading initial) or "pos". A different team alone is not reported: players move clubs after a
    file is made. "name" rows are usually renames of the same player; check them by eye.
    """
    teams = {t["id"]: t["name"] for t in bootstrap["teams"]}
    fpl = pd.DataFrame(
        {
            "fpl_id": e["id"],
            "fpl_name": e["web_name"],
            "fpl_team": teams.get(e["team"]),
            "fpl_pos": POS_BY_ELEMENT_TYPE.get(e["element_type"]),
        }
        for e in bootstrap["elements"]
    )
    players = proj.drop_duplicates("fpl_id")[["fpl_id", "name", "team", "pos"]]
    joined = players.merge(fpl, on="fpl_id", how="left", indicator=True)
    joined["issue"] = None
    joined.loc[joined["pos"] != joined["fpl_pos"], "issue"] = "pos"
    joined.loc[joined["name"].map(_normalise) != joined["fpl_name"].map(_normalise), "issue"] = "name"
    joined.loc[joined["_merge"] == "left_only", "issue"] = "missing"
    return joined[joined["issue"].notna()].drop(columns="_merge").reset_index(drop=True)


def _main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m fplrank.data.projections", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    reg = sub.add_parser("register", help="copy Solio exports into data/projections/ and add them to the registry")
    reg.add_argument("files", nargs="+", type=Path)
    chk = sub.add_parser("check-ids", help="compare projection ids with the latest FPL bootstrap-static snapshot")
    chk.add_argument("files", nargs="*", type=Path, help="default: every registered file")
    chk.add_argument("--fetch", action="store_true", help="download a fresh bootstrap-static snapshot first")
    args = parser.parse_args(argv)

    if args.command == "register":
        for f in args.files:
            row = register(f)
            span = f"GW{row['first_gw']}-{row['last_gw']}"
            print(f"{f.name} -> {row['file']} (vintage GW{row['vintage_gw']}, {span}, {row['n_players']} players)")
        return

    from fplrank.data.fpl_api import FplApi, latest_snapshot

    bootstrap = FplApi().bootstrap() if args.fetch else latest_snapshot("bootstrap-static/")
    files = args.files or [PROJECTIONS_DIR / f for f in read_registry()["file"]]
    for f in files:
        report = id_report(load_solio(f), bootstrap)
        print(f"{f.name}: {'all ids match' if report.empty else f'{len(report)} issue(s)'}")
        if not report.empty:
            print(report.to_string(index=False))


if __name__ == "__main__":
    _main()
