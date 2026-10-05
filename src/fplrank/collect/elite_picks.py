"""Collect elite managers' picks from the public FPL API (run on a machine that can reach it).

For every manager in the sets in config/manager_sets.toml: each GW's picks, captain, vice, chip,
transfers, hits and rank. Every response is saved as a snapshot under data/snapshots/, and the
tables in data/collected/ are rebuilt from the latest snapshots. That makes runs resumable: picks
for a GW are fetched once (they are fixed at the deadline); standings, history and transfers are
fetched again once their snapshot is older than `max_age` (default 12 hours).

Tables (parquet, git-ignored), keyed by `season, gw, entry_id` where relevant:
    members    set, entry_id, rank (overall rank when collected), collected_at
    picks      one row per pick: fpl_id, position, multiplier, is_captain, is_vice_captain, active_chip
    chips      chip played per GW (from history)
    transfers  element_in/out, costs, time
    ranks      points, total_points, gw rank, overall_rank, bank, value, transfers, hits
    eo         season, gw, group, fpl_id, eo, n_managers (same long shape as fplrank.data.elite)

EO is deadline EO, as in the Elite 64 graphics: starters count 1, the captain 2 (3 on Triple
Captain), bench players 0 (1 on Bench Boost). Auto-subs and vice-captain promotions are ignored.

Survivorship: `overall_top` sets come from the standings at collection time, so "top1000" in GW1 is
the GW1 picks of today's top 1000. `ranks` keeps each member's overall rank by GW so "top N as of
GW t" can be reconstructed later.

CLI:
    uv run python -m fplrank.collect.elite_picks collect [--top N] [--max-age-hours H]
    uv run python -m fplrank.collect.elite_picks build
    uv run python -m fplrank.collect.elite_picks report
"""

import argparse
import json
import math
import time
import tomllib
from datetime import UTC, datetime, timedelta
from functools import partial
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from fplrank.data.fpl_api import FplApi, latest_snapshot_path, snapshot_time
from fplrank.paths import COLLECTED_DIR, CONFIG_DIR, PROJECT_ROOT, SNAPSHOT_DIR

CONFIG_PATH = CONFIG_DIR / "manager_sets.toml"
REPORT_PATH = PROJECT_ROOT / "docs" / "research" / "top1000-vs-elite64.md"
STANDINGS_PAGE_SIZE = 50
_log = partial(print, flush=True)  # flush so progress shows up in redirected logs straight away


class PoliteApi(FplApi):
    """FplApi with a minimum gap between requests and retries with exponential backoff."""

    def __init__(self, min_interval: float = 0.5, retries: int = 5, **kwargs):
        super().__init__(**kwargs)
        retry = Retry(
            total=retries,
            backoff_factor=2,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=True,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.min_interval = min_interval
        self.requests = 0
        self._last = 0.0

    def get(self, endpoint: str, save: bool = True) -> dict | list:
        wait = self._last + self.min_interval - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        self.requests += 1
        return super().get(endpoint, save)


def load_config(path: Path = CONFIG_PATH) -> dict:
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    return {
        "season": cfg["season"],
        "overall_top": [int(n) for n in cfg.get("overall_top", [])],
        "named_lists": {name: [int(e) for e in ids] for name, ids in cfg.get("named_lists", {}).items()},
    }


class Collector:
    def __init__(
        self,
        api: FplApi | None = None,
        snapshot_dir: Path = SNAPSHOT_DIR,
        out_dir: Path = COLLECTED_DIR,
        max_age: timedelta = timedelta(hours=12),
        now: datetime | None = None,
        log=_log,
    ):
        self.snapshot_dir = snapshot_dir
        self.api = api or PoliteApi(snapshot_dir=snapshot_dir)
        self.out_dir = out_dir
        self.max_age = max_age
        self.now = now or datetime.now(UTC)
        self.log = log

    def fetch(self, endpoint: str, max_age: timedelta | None) -> dict | list:
        """Latest snapshot if it is recent enough (`max_age=None`: any snapshot will do), else download."""
        path = latest_snapshot_path(endpoint, self.snapshot_dir)
        if path is not None and (max_age is None or self.now - snapshot_time(path) < max_age):
            return json.loads(path.read_text())
        return self.api.get(endpoint)

    def members(self, config: dict) -> pd.DataFrame:
        rows = []
        for n in config["overall_top"]:
            results = []
            for page in range(1, math.ceil(n / STANDINGS_PAGE_SIZE) + 1):
                standings = self.fetch(f"leagues-classic/314/standings/?page_standings={page}", self.max_age)["standings"]
                results += standings["results"]
                if not standings["has_next"]:
                    break
            rows += [{"set": f"top{n}", "entry_id": r["entry"], "rank": r["rank"]} for r in results[:n]]
        for name, ids in config["named_lists"].items():
            rows += [{"set": name, "entry_id": e, "rank": None} for e in ids]
        members = pd.DataFrame(rows, columns=["set", "entry_id", "rank"]).astype({"entry_id": "int64", "rank": "Int64"})
        members["collected_at"] = self.now.isoformat(timespec="seconds")
        return members

    def collect(self, config: dict) -> dict:
        """Download everything needed for `config`'s sets, then rebuild the tables. Returns a summary."""
        bootstrap = self.fetch("bootstrap-static/", self.max_age)
        self.fetch("fixtures/", self.max_age)
        started = {e["id"]: e for e in bootstrap["events"] if datetime.fromisoformat(e["deadline_time"]) <= self.now}
        members = self.members(config)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        members.to_parquet(self.out_dir / "members.parquet", index=False)

        entries = members["entry_id"].unique().tolist()
        self.log(f"{len(entries)} managers, GW{min(started)}-{max(started)}")
        failed = []
        for i, entry in enumerate(entries, 1):
            try:
                history = self.fetch(f"entry/{entry}/history/", self.max_age)
                self.fetch(f"entry/{entry}/transfers/", self.max_age)
                for gw in (h["event"] for h in history["current"] if h["event"] in started):
                    self.fetch(f"entry/{entry}/event/{gw}/picks/", None)
            except requests.HTTPError as err:
                failed.append(entry)
                self.log(f"  entry {entry}: {err}")
            if i % 50 == 0 or i == len(entries):
                self.log(f"  {i}/{len(entries)} managers done ({getattr(self.api, 'requests', '?')} requests so far)")
        for gw, event in started.items():
            self.fetch(f"event/{gw}/live/", None if event["finished"] else self.max_age)

        tables = build(config["season"], self.out_dir, self.snapshot_dir)
        return {"managers": len(entries), "failed": failed, "gws": sorted(started), "rows": {k: len(v) for k, v in tables.items()}}


def _latest(endpoint: str, snapshot_dir: Path) -> dict | list | None:
    path = latest_snapshot_path(endpoint, snapshot_dir)
    return json.loads(path.read_text()) if path else None


def build(season: str, out_dir: Path = COLLECTED_DIR, snapshot_dir: Path = SNAPSHOT_DIR) -> dict[str, pd.DataFrame]:
    """Rebuild picks/chips/transfers/ranks/eo from the latest snapshots of every member's endpoints."""
    members = pd.read_parquet(out_dir / "members.parquet")
    picks, chips, transfers, ranks = [], [], [], []
    for entry in members["entry_id"].unique().tolist():
        history = _latest(f"entry/{entry}/history/", snapshot_dir)
        if history is None:
            continue
        for h in history["current"]:
            ranks.append({"entry_id": entry, "gw": h["event"], **{k: v for k, v in h.items() if k != "event"}})
            gw_picks = _latest(f"entry/{entry}/event/{h['event']}/picks/", snapshot_dir)
            if gw_picks is not None:
                chip = gw_picks["active_chip"]
                picks += [
                    {"entry_id": entry, "gw": h["event"], "fpl_id": p["element"], **p, "active_chip": chip} for p in gw_picks["picks"]
                ]
        chips += [{"entry_id": entry, "gw": c["event"], "chip": c["name"], "time": c["time"]} for c in history["chips"]]
        transfers += [{"entry_id": entry, "gw": t["event"], **t} for t in _latest(f"entry/{entry}/transfers/", snapshot_dir) or []]

    def frame(rows, drop=()):
        df = pd.DataFrame(rows).drop(columns=list(drop), errors="ignore")
        df.insert(0, "season", season)
        return df

    tables = {
        "picks": frame(picks, drop=["element"]),
        "chips": frame(chips),
        "transfers": frame(transfers, drop=["entry", "event"]),
        "ranks": frame(ranks),
    }
    tables["eo"] = compute_eo(tables["picks"], members, season)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_parquet(out_dir / f"{name}.parquet", index=False)
    return tables


def compute_eo(picks: pd.DataFrame, members: pd.DataFrame, season: str) -> pd.DataFrame:
    """Deadline EO per set and GW: `season, gw, group, fpl_id, eo, n_managers` (eo 1.0 = 100%)."""
    columns = ["season", "gw", "group", "fpl_id", "eo", "n_managers"]
    if picks.empty:
        return pd.DataFrame(columns=columns)
    bench_counts = picks["position"].gt(11) & picks["active_chip"].ne("bboost")
    captain_extra = picks["is_captain"] * picks["active_chip"].eq("3xc").map({True: 2, False: 1})
    weighted = picks.assign(weight=(~bench_counts) * (1 + captain_extra))
    out = []
    for group, ids in members.groupby("set")["entry_id"]:
        sub = weighted[weighted["entry_id"].isin(ids)]
        n = sub.groupby("gw")["entry_id"].nunique().rename("n_managers")
        eo = sub.groupby(["gw", "fpl_id"])["weight"].sum().reset_index().join(n, on="gw")
        eo["eo"] = eo["weight"] / eo["n_managers"]
        out.append(eo[eo["eo"] > 0].assign(group=group, season=season))
    return pd.concat(out, ignore_index=True)[columns].sort_values(["group", "gw", "eo"], ascending=[True, True, False], ignore_index=True)


def compare_with_elite64(eo: pd.DataFrame, group: str = "top1000") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Our EO for `group` next to AE64/E64 for every player listed in the Elite 64 data.

    Returns (per-player table, per-GW summary). Players we collected but nobody owned count as 0.
    """
    from fplrank.data.elite import load_eo

    elite = load_eo().pivot_table(index=["gw", "fpl_id", "player", "pos"], columns="group", values="eo").reset_index()
    ours = eo[eo["group"] == group][["gw", "fpl_id", "eo"]].rename(columns={"eo": group})
    both = elite[elite["gw"].isin(ours["gw"].unique())].merge(ours, on=["gw", "fpl_id"], how="left").fillna({group: 0.0})
    rows = []
    for gw, g in both.groupby("gw"):
        row = {"gw": gw, "players": len(g)}
        for other in ("AE64", "E64"):
            row[f"corr_{other}"] = g[group].corr(g[other])
            row[f"mean_abs_diff_{other}"] = (g[group] - g[other]).abs().mean()
        rows.append(row)
    return both, pd.DataFrame(rows)


def write_report(out_dir: Path = COLLECTED_DIR, path: Path = REPORT_PATH, group: str = "top1000") -> Path:
    eo = pd.read_parquet(out_dir / "eo.parquet")
    members = pd.read_parquet(out_dir / "members.parquet")
    both, summary = compare_with_elite64(eo, group)
    n_managers = eo[eo["group"] == group].groupby("gw")["n_managers"].first()
    both["diff_vs_AE64"] = both[group] - both["AE64"]
    biggest = both.reindex(both["diff_vs_AE64"].abs().sort_values(ascending=False).index).head(15)

    def table(df, cols):
        shown = df[cols].copy()
        for c in cols:
            if c in ("AE64", "E64", group, "diff_vs_AE64") or c.startswith("mean_abs"):
                shown[c] = shown[c].map("{:.0%}".format)
        return shown.to_markdown(index=False, floatfmt=".2f")

    collected_at = members["collected_at"].iloc[0]
    text = f"""# {group} EO vs Elite 64 (AE64 / E64), 2026-27

Generated by `uv run python -m fplrank.collect.elite_picks report` from data collected {collected_at[:10]}.
Not an assertion: a sanity check that our collector's EO is in the same ballpark as the
hand-transcribed Elite 64 graphics (`datasets/elite_ownership/`).

- **{group}** = the overall top {group.removeprefix("top")} *at collection time* (survivorship: they were not
  necessarily top {group.removeprefix("top")} in earlier GWs). Managers per GW: {", ".join(f"GW{g} {n}" for g, n in n_managers.items())}.
- Deadline EO for all three: captain x2 (x3 on Triple Captain), bench counted only on Bench Boost.
- Compared only on players listed in the Elite 64 data for that GW (the graphics list ~8 per position).

## Per GW

{table(summary, list(summary.columns))}

`corr_*` = Pearson correlation across the listed players; `mean_abs_diff_*` = mean absolute EO gap.

## Largest gaps vs AE64

{table(biggest, ["gw", "player", "pos", group, "AE64", "E64", "diff_vs_AE64"])}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m fplrank.collect.elite_picks", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    col = sub.add_parser("collect", help="download picks for the configured manager sets, then build the tables")
    col.add_argument("--top", type=int, help="override overall_top with a single N (e.g. 20 for a quick test)")
    col.add_argument("--max-age-hours", type=float, default=12, help="re-download standings/history/transfers older than this")
    col.add_argument("--config", type=Path, default=CONFIG_PATH)
    bld = sub.add_parser("build", help="rebuild the tables from saved snapshots (no downloads)")
    bld.add_argument("--config", type=Path, default=CONFIG_PATH)
    rep = sub.add_parser("report", help="write the top-N vs Elite 64 comparison to docs/research/")
    rep.add_argument("--group", default="top1000")
    args = parser.parse_args(argv)

    if args.command == "report":
        print(f"Wrote {write_report(group=args.group)}")
        return
    config = load_config(args.config)
    if args.command == "build":
        tables = build(config["season"])
        print({k: len(v) for k, v in tables.items()})
        return
    if args.top:
        config["overall_top"] = [args.top]
    start = time.monotonic()
    summary = Collector(max_age=timedelta(hours=args.max_age_hours)).collect(config)
    print(f"Done in {(time.monotonic() - start) / 60:.1f} min: {summary}")


if __name__ == "__main__":
    _main()
