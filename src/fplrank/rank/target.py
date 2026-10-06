"""The target line (S2a): the gap S2 works with, and the absolute line for the report.

S2 compares our score with the EO group's, so the gap must be relative to the group too (otherwise the
field's growth is counted twice: once in the line, once in μ = Σ (m - EO) x xP):

    G = T_X(now) - ours(now) + drift x GWs left

`season_drift(rank, group)` (what S2c uses): drift = the mean over full past seasons of (the line's final
points - the group's mean final points) / 38, and its season-to-season sd, which x GWs left is the gap's
spread. A lower bound, as today's members' past seasons run high (docs/research/rank-goal-inputs.md).

`line_drift(rank, group)` (this season, for the report): the mean over this season's GWs of (the line's GW gain - the group's mean GW
points), with the line at each past GW interpolated from the collected managers' overall ranks and totals.
0 until 3 GWs are available. Caveat: groups are today's members, so for top1000 (selected for scoring
well so far) the group's past points run high and drift reads low; the fixed Elite 64 lists are less
affected.

`target_line(rank)`: indicative absolute line for the report only,

    final = T_X(now) + (38 - gw) x pace_X

with T_X(now) from the collector's `thresholds` table (log-rank interpolation, no extrapolation) and
pace_X the line's average points per GW over recent seasons (end-of-season cut-off / 38, from the `past`
field; docs/research/rank-cutoffs.md). The line's current pace is not used: early in a season the
managers at rank X are partly there by luck (top 10k ran at 80 a GW to GW5 of 2026-27 vs 63-68
historically). `sd` is the spread of the seasons' paces scaled to the GWs left (the absolute line's, so S2c does not use it:
the group's own swings would count twice).
"""

import math
import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd

from fplrank.paths import COLLECTED_DIR

N_GWS = 38


@dataclass(frozen=True)
class TargetLine:
    rank: int
    gw: int  # last GW included in `now`
    now: float  # points needed for `rank` after `gw`
    pace: float  # expected points per GW of the line from here to GW38
    final: float  # projected points needed after GW38
    sd: float  # uncertainty of `final` from season-to-season variation in pace
    seasons: tuple[str, ...]  # seasons the pace is taken from

    def __str__(self):
        return (
            f"Top {self.rank:,}: {self.now:.0f} after GW{self.gw}, projected {self.final:.0f} ± {self.sd:.0f} "
            f"after GW38 ({self.pace:.1f} a GW, from {', '.join(self.seasons)})"
        )


def _interp_log_rank(rank: int, ranks, values) -> float:
    """Linear in log(rank) between the nearest known ranks. No extrapolation beyond them."""
    if not min(ranks) <= rank <= max(ranks):
        raise ValueError(f"Rank {rank:,} is outside the tracked ranks {sorted(int(r) for r in ranks)}")
    order = np.argsort(ranks)
    x, y = np.log(np.asarray(ranks, float)[order]), np.asarray(values, float)[order]
    return float(np.interp(math.log(rank), x, y))


def line_now(thresholds: pd.DataFrame, rank: int, gw: int | None = None) -> tuple[float, int]:
    """Points needed for `rank` after the latest collected GW (or `gw`), from the collector's thresholds."""
    t = thresholds.dropna(subset=["gw"])
    if gw is not None:
        t = t[t["gw"] == gw]
    if t.empty:
        raise ValueError("No threshold rows" + (f" for GW{gw}" if gw is not None else ""))
    gw = int(t["gw"].max())
    latest = t[t["gw"] == gw].sort_values("collected_at").groupby("target_rank").last()
    return _interp_log_rank(rank, latest.index, latest["total_points"]), gw


def season_paces(cutoffs: pd.DataFrame, rank: int, n_seasons: int = 3) -> pd.Series:
    """Points per GW of the rank-`rank` line over each of the last `n_seasons` seasons (season -> pace).

    Uses `elite_picks.season_cutoffs` output. A season counts only if its cut-offs bracket `rank` (no
    extrapolation), so e.g. top-100 paces skip 2024-25, whose sample has no top-100 finisher.
    """
    wide = cutoffs.pivot(index="season", columns="target_rank", values="points").sort_index()
    paces = {}
    for season, row in wide.iterrows():
        row = row.dropna()
        if len(row) >= 2 and row.index.min() <= rank <= row.index.max():
            paces[season] = _interp_log_rank(rank, row.index, row.values) / N_GWS
    return pd.Series(paces).sort_index().tail(n_seasons)


def target_line(
    rank: int,
    gw: int | None = None,
    thresholds: pd.DataFrame | None = None,
    cutoffs: pd.DataFrame | None = None,
    n_seasons: int = 3,
) -> TargetLine:
    """The rank-`rank` line now and projected to GW38. Defaults read `data/collected/`."""
    if thresholds is None:
        thresholds = pd.read_parquet(COLLECTED_DIR / "thresholds.parquet")
    if cutoffs is None:
        from fplrank.collect.elite_picks import season_cutoffs

        cutoffs = season_cutoffs(pd.read_parquet(COLLECTED_DIR / "past_seasons.parquet"))
    now, gw = line_now(thresholds, rank, gw)
    paces = season_paces(cutoffs, rank, n_seasons)
    if paces.empty:
        raise ValueError("No past-season cut-offs to take a pace from")
    left = N_GWS - gw
    pace = float(paces.mean())
    sd = float(paces.std(ddof=1)) * left if len(paces) > 1 else float("nan")
    return TargetLine(rank, gw, now, pace, now + left * pace, sd, tuple(paces.index))


def line_history(ranks: pd.DataFrame, rank: int) -> pd.Series:
    """Points needed for `rank` after each GW (gw -> points), from collected managers' overall rank and total.

    GWs where the collected managers don't bracket `rank` are left out.
    """
    out = {}
    for gw, g in ranks.groupby("gw"):
        g = g.dropna(subset=["overall_rank"])
        if len(g) >= 2 and g["overall_rank"].min() <= rank <= g["overall_rank"].max():
            g = g.groupby("overall_rank")["total_points"].mean()
            out[int(gw)] = _interp_log_rank(rank, g.index, g.values)
    return pd.Series(out, dtype=float).sort_index()


def line_drift(
    rank: int, group: str, ranks: pd.DataFrame | None = None, members: pd.DataFrame | None = None, min_gws: int = 3
) -> tuple[float, pd.DataFrame]:
    """Mean per-GW (line gain - group's mean net GW points) this season, and the per-GW table behind it.

    Net points = points - transfer cost. Returns 0 if fewer than `min_gws` GWs have both numbers.
    `elite` is measured against the weighted mean of its groups (`opt.ownership.group_weights`), as its EO is.
    """
    from fplrank.opt.ownership import group_weights

    if ranks is None:
        ranks = pd.read_parquet(COLLECTED_DIR / "ranks.parquet")
    if members is None:
        members = pd.read_parquet(COLLECTED_DIR / "members.parquet")
    line = line_history(ranks, rank)
    net = ranks["points"] - ranks["event_transfers_cost"]
    group_pts = sum(
        w * net[ranks["entry_id"].isin(set(members.loc[members["set"] == g, "entry_id"]))].groupby(ranks["gw"]).mean()
        for g, w in group_weights(group).items()
    )
    table = pd.DataFrame({"line": line, "line_gain": line.diff(), "group_points": group_pts}).dropna()
    table["drift"] = table["line_gain"] - table["group_points"]
    drift = float(table["drift"].mean()) if len(table) >= min_gws else 0.0
    return drift, table


@dataclass(frozen=True)
class SeasonDrift:
    rank: int
    group: str
    drift: float  # mean per GW of (line's final points - group's mean final points) / 38
    sd: float  # spread of that per-GW figure across seasons; x GWs left = the relative line's sd
    seasons: tuple[str, ...]

    def __str__(self):
        return (
            f"drift vs {self.group} {self.drift:+.1f} ± {self.sd:.2f} a GW "
            f"({self.seasons[0]}..{self.seasons[-1]}, {len(self.seasons)} seasons)"
        )


def season_drift(
    rank: int, group: str, past: pd.DataFrame | None = None, members: pd.DataFrame | None = None, since: str = "2018-19"
) -> SeasonDrift:
    """The line's drift against the EO group over full past seasons, and its season-to-season spread.

    Per season: (end-of-season line - the group's mean final total) / 38, with the group = today's members
    and their `past` totals. Both are taken against the group, so the spread is of the gap, not of the line
    (a high-scoring season lifts both). Biased low: today's members were chosen on past results, so their
    past seasons run high and the drift is a lower bound (docs/research/rank-goal-inputs.md).
    `elite` is the weighted mean of its groups (`opt.ownership.group_weights`), as its EO is.
    """
    from fplrank.collect.elite_picks import season_cutoffs
    from fplrank.opt.ownership import group_weights

    if past is None:
        past = pd.read_parquet(COLLECTED_DIR / "past_seasons.parquet")
    if members is None:
        members = pd.read_parquet(COLLECTED_DIR / "members.parquet")
    past = past[past["season"] >= since]
    line = season_cutoffs(past, ranks=(rank,)).set_index("season")["points"]
    group_mean = sum(
        w * past[past["entry_id"].isin(set(members.loc[members["set"] == g, "entry_id"]))].groupby("season")["total_points"].mean()
        for g, w in group_weights(group).items()
    )
    per_gw = ((line - group_mean) / N_GWS).dropna().sort_index()
    if len(per_gw) < 2:
        raise ValueError(f"Need 2+ seasons with a top-{rank:,} line and {group} totals since {since}")
    return SeasonDrift(rank, group, float(per_gw.mean()), float(per_gw.std(ddof=1)), tuple(per_gw.index))


def _main(argv=None):
    import argparse

    p = argparse.ArgumentParser(description="Points needed for a target overall rank, now and at GW38")
    p.add_argument("ranks", type=int, nargs="+")
    p.add_argument("--gw", type=int, help="GW of the line (default: latest collected)")
    p.add_argument("--group", default="AE64", help="EO group for the drift (AE64, E64, elite, top1000)")
    args = p.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    for rank in args.ranks:
        print(target_line(rank, args.gw))
        drift, table = line_drift(rank, args.group)
        print(f"  this season's drift vs {args.group}: {drift:+.1f} a GW over GWs {', '.join(map(str, table.index))}")
        print(f"  full seasons (used by --target): {season_drift(rank, args.group)}")


if __name__ == "__main__":
    _main()
