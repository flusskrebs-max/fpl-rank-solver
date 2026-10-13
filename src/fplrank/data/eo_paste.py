"""The EO file `--eo solio` reads, built from an EO table Alex pastes or downloads (e.g. LiveFPL's top-10k EO CSV:
`Player,Team,EOTop10k,CTop10k,TcTop10k,...`), in place of Solio's EO export.

The pasted table is last GW's EO for one group. The file carries it forward unchanged to every GW from next GW to
GW38 (persistence), with triple captains counted as normal captains (chips don't carry over). Players not in the
table get `FLOOR` %: Alex's lists run in descending order, so anyone below the last row is about 0.1%.
Persistence is the simple choice: on GW6 2026-27 (top 10k) it was off by 6.2 EO points a player against 7.8 for
Solio's own forecast; the collector's re-pick (`--eo top10k`) did better again at 4.7 (eo-blend.md).

    uv run python -m fplrank.data.eo_paste <file> [--gw N]   # writes data/projections/solio_eo/EO_GWnn_<date>.csv
"""

import argparse
import io
import re
import unicodedata
from datetime import date
from pathlib import Path

import pandas as pd

from fplrank.paths import PROJECTIONS_DIR

EO_DIR = PROJECTIONS_DIR / "solio_eo"  # where opt.ownership.load_solio_eo reads the newest file
FLOOR = 0.1  # EO % for players not in the table
LAST_GW = 38


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower().strip()


def _column(cols, pattern: str) -> str | None:
    return next((c for c in cols if re.search(pattern, _norm(c))), None)


def key_columns(cols) -> tuple[str | None, str | None]:
    """The name and EO columns of an EO table's header (None where there is none)."""
    return _column(cols, r"^(player|name|web_name)$"), _column(cols, r"^eo|\beo\b")


def read_table(text: str) -> pd.DataFrame:
    """The pasted table as `name, team, eo, tc` (EO and triple-captain shares in %; team may be None).

    Comma or tab separated, with a header. The first column called Player/Name is the name, Team the team, the
    first column starting `EO` (or `... EO %`) the EO and the first starting `TC` the triple captains; `%` signs
    are fine. Raises ValueError if there is no name or EO column."""
    text = text.lstrip("﻿").strip()
    if not text:
        raise ValueError("nothing pasted")
    sep = "\t" if "\t" in text.split("\n", 1)[0] else ","
    raw = pd.read_csv(io.StringIO(text), sep=sep, dtype=str, keep_default_na=False)
    cols = list(raw.columns)
    name, eo = key_columns(cols)
    if name is None or eo is None:
        raise ValueError(f"need a Player (or Name) column and an EO column; the header was: {', '.join(cols)}")
    team, tc = _column(cols, r"^team$"), _column(cols, r"^tc")

    def pct(col: str | None) -> pd.Series:
        if col is None:
            return pd.Series(0.0, index=raw.index)
        return pd.to_numeric(raw[col].str.replace("%", "").str.strip(), errors="coerce").fillna(0.0)

    out = pd.DataFrame({"name": raw[name].str.strip(), "team": raw[team].str.strip() if team else None, "eo": pct(eo), "tc": pct(tc)})
    return out[out["name"] != ""].reset_index(drop=True)


def match_ids(table: pd.DataFrame, bootstrap: dict) -> tuple[pd.Series, list[str]]:
    """fpl_id for each row (NaN if none) on web name (accents ignored) and team (full or short name), or on name
    alone when no team is given and the name is unique; and the rows not matched."""
    teams = {t["id"]: t for t in bootstrap["teams"]}
    by_team, by_name = {}, {}
    for e in bootstrap["elements"]:
        t = teams[e["team"]]
        for key in (t["name"], t["short_name"]):
            by_team[(_norm(e["web_name"]), _norm(key))] = e["id"]
        by_name.setdefault(_norm(e["web_name"]), []).append(e["id"])
    ids = []
    for name, team in zip(table["name"], table["team"], strict=True):
        if team:
            ids.append(by_team.get((_norm(name), _norm(team))))
        else:
            found = by_name.get(_norm(name), [])
            ids.append(found[0] if len(found) == 1 else None)
    ids = pd.Series(ids, index=table.index, dtype="Int64")
    missing = [f"{n} ({t})" if t else n for n, t, i in zip(table["name"], table["team"], ids, strict=True) if pd.isna(i)]
    return ids, missing


def build(text: str, bootstrap: dict, next_gw: int | None = None, floor: float = FLOOR) -> tuple[pd.DataFrame, list[str]]:
    """Solio's EO layout (`ID, Name, Team, Price, Avg EO %, GW{next_gw} EO %, ... GW38 EO %`, one row per FPL
    player) from a pasted EO table, and the pasted rows that matched no player. `next_gw`: FPL's next GW by default."""
    if next_gw is None:
        next_gw = next(e["id"] for e in bootstrap["events"] if e["is_next"])
    table = read_table(text)
    table["fpl_id"], missing = match_ids(table, bootstrap)
    eo = (table["eo"] - table["tc"]).groupby(table["fpl_id"]).sum()  # chip-free: a triple captain counts as a captain
    teams = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    els = sorted(bootstrap["elements"], key=lambda e: e["id"])
    now = [round(float(eo.get(e["id"], floor)), 2) for e in els]
    out = pd.DataFrame(
        {
            "ID": [e["id"] for e in els],
            "Name": [e["web_name"] for e in els],
            "Team": [teams[e["team"]] for e in els],
            "Price": [e["now_cost"] / 10 for e in els],
            "Avg EO %": now,
        }
    )
    gws = pd.DataFrame({f"GW{gw} EO %": now for gw in range(next_gw, LAST_GW + 1)})
    out = pd.concat([out, gws], axis=1).sort_values("Avg EO %", ascending=False, kind="stable")
    return out.reset_index(drop=True), missing


def save(table: pd.DataFrame, folder: Path = EO_DIR, today: date | None = None) -> Path:
    """Write the file as solio_eo/EO_GWnn_yyyymmdd.csv (nn its first GW), where `--eo solio` reads the newest."""
    first = min(int(m[1]) for c in table.columns if (m := re.fullmatch(r"GW(\d+) EO %", c)))
    dest = folder / f"EO_GW{first:02d}_{(today or date.today()):%Y%m%d}.csv"
    dest.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(dest, index=False, encoding="utf-8")
    return dest


def bootstrap() -> dict:
    """FPL's bootstrap (live, saved as a snapshot), or the latest saved snapshot when the API can't be reached."""
    import requests

    from fplrank.data import fpl_api

    try:
        return fpl_api.FplApi().bootstrap()
    except requests.RequestException as e:
        print(f"FPL API not reached ({e}); using the latest saved bootstrap")
        return fpl_api.latest_snapshot("bootstrap-static/")


def summary(table: pd.DataFrame, missing: list[str]) -> str:
    gws = [c for c in table.columns if c.endswith(" EO %") and c.startswith("GW")]
    floor = table["Avg EO %"].min()
    listed = int((table["Avg EO %"] > floor).sum())
    text = f"{gws[0][:-5]}-{gws[-1][:-5]}, {listed} players above {floor:g}%, EO total {table[gws[0]].sum() / 100:.1f}"
    return text + (f"; not matched, left out: {', '.join(missing)}" if missing else "")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="python -m fplrank.data.eo_paste", description=__doc__.split("\n\n")[0])
    p.add_argument("file", type=Path, help="the EO table (CSV or tab separated, with a header)")
    p.add_argument("--gw", type=int, help="first GW of the file (default: FPL's next GW)")
    p.add_argument("--floor", type=float, default=FLOOR, help=f"EO %% for players not listed (default {FLOOR})")
    args = p.parse_args(argv)
    table, missing = build(args.file.read_text(encoding="utf-8-sig"), bootstrap(), args.gw, args.floor)
    print(f"Saved {save(table)}: {summary(table, missing)}")


if __name__ == "__main__":
    main()
