"""Ownership weighting (S1): one "risk position" knob, λ, applied to Sertalp's projections by `fplrank solve`.

Each projection is scaled by how much the target field owns the player:

    xP' = xP x (1 + λ x (EO - 1))

EO is effective ownership as a fraction (1.5 = 150%, captaincy included). λ > 0 favours players the
field owns (covering), λ < 0 favours differentials. The term is a linear proxy for the variance of our
score relative to the field, which HiGHS can't take directly (solver-design §1, §4 [C]). Centring at
EO = 1 is a scale choice, not a neutral point: it keeps adjusted values near raw xP, so λ mostly changes
*which* players are picked rather than how keen the solver is on hits. (For variance, owning a player
once is neutral at EO 0.5 and captaining him at EO 1.5.)

`fplrank solve` (cli.py) applies λ to the first GW of the horizon only (`lam_gw`): that is the GW being
decided now, and EO further out is much less certain. Later GWs use raw xP. Each plan is then scored on
the raw projections (`score_plan`) and the λ chosen by P(reaching the target line) (`rank_goal_table`).
"""

import math
import re

import pandas as pd

from fplrank.paths import COLLECTED_DIR

SWEEP = (-0.3, -0.2, -0.1, -0.05, 0.0, 0.05, 0.1, 0.2, 0.3)
_PTS = re.compile(r"^(\d+)_Pts$")


def load_solio_eo(bootstrap: dict, path=None) -> pd.DataFrame:
    """Solio's EO forecast (`Name, Team, Price, Avg EO %, GW6 EO %, ...`) as fpl_id x GW (fraction).

    The export has no FPL ids, so players are matched on web name (accents ignored) and team. Default
    path: the newest file in data/projections/solio_eo/ (paid data, never committed).
    """
    import unicodedata

    from fplrank.paths import PROJECTIONS_DIR

    def norm(s):
        return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()

    if path is None:
        files = sorted((PROJECTIONS_DIR / "solio_eo").glob("*.csv"))
        if not files:
            raise FileNotFoundError(f"No Solio EO export in {PROJECTIONS_DIR / 'solio_eo'}")
        path = files[-1]
    raw = pd.read_csv(path, encoding="utf-8-sig")
    teams = {t["id"]: t["short_name"] for t in bootstrap["teams"]}
    ids = {(norm(e["web_name"]), teams[e["team"]]): e["id"] for e in bootstrap["elements"]}
    raw["fpl_id"] = [ids.get((norm(n), t)) for n, t in zip(raw["Name"], raw["Team"], strict=True)]
    if missing := raw.loc[raw["fpl_id"].isna(), "Name"].tolist():
        print(f"Solio EO: {len(missing)} players not matched to FPL ids, left out: {missing[:10]}")
    gw_cols = {c: int(c[2:].split()[0]) for c in raw.columns if c.startswith("GW") and c.endswith("EO %")}
    out = raw.dropna(subset=["fpl_id"]).set_index(raw["fpl_id"].dropna().astype(int))[list(gw_cols)]
    return out.rename(columns=gw_cols).div(100)


# `--eo elite`: an equal mix of the two fixed Elite 64 lists, EO and drift alike. LIVE_WEIGHT moves weight
# onto today's top managers (LIVE_GROUP): as ranks settle through the season they become a fair picture of
# the field we chase (Alex). 0 until we decide how to ramp it; top10k/top1000 drift is biased low early on.
LIVE_WEIGHT = 0.0
LIVE_GROUP = "top10k"


def group_weights(group: str, live_weight: float | None = None) -> dict[str, float]:
    """Collector groups and weights behind an EO group: `elite` is the mix above, anything else is itself."""
    if group != "elite":
        return {group: 1.0}
    w = LIVE_WEIGHT if live_weight is None else live_weight
    return {"AE64": (1 - w) / 2, "E64": (1 - w) / 2} | ({LIVE_GROUP: w} if w else {})


def chip_free_eo(picks: pd.DataFrame, members: pd.DataFrame, group: str) -> pd.DataFrame:
    """Deadline EO per GW for `group` with that GW's chips taken out: `gw, fpl_id, eo`.

    Chips don't carry over, so last GW's EO used for next GW shouldn't count them: a triple captain
    counts as a normal captain, a bench boost's bench counts 0, and a free hitter counts with the squad
    they return to (their latest earlier non-free-hit picks; left out if there are none).
    """
    p = picks[picks["entry_id"].isin(set(members.loc[members["set"] == group, "entry_id"]))]
    p = p.assign(weight=p["position"].le(11) * (1 + p["is_captain"].astype(int)))
    own = p[p["active_chip"].ne("freehit")]
    out = []
    for gw in sorted(p["gw"].unique()):
        week = own[own["gw"] == gw]
        fh = set(p.loc[(p["gw"] == gw) & p["active_chip"].eq("freehit"), "entry_id"])
        if fh:  # each free hitter's latest earlier own squad
            back = own[own["entry_id"].isin(fh) & (own["gw"] < gw)]
            back = back[back["gw"] == back.groupby("entry_id")["gw"].transform("max")]
            week = pd.concat([week, back])
        eo = week.groupby("fpl_id")["weight"].sum() / week["entry_id"].nunique()
        out.append(eo[eo > 0].rename("eo").reset_index().assign(gw=gw))
    return pd.concat(out, ignore_index=True)[["gw", "fpl_id", "eo"]] if out else pd.DataFrame(columns=["gw", "fpl_id", "eo"])


def load_eo(group: str, gw: int | None = None, collected_dir=COLLECTED_DIR) -> tuple[pd.Series, int]:
    """Latest EO for `group` at or before `gw`, as fpl_id -> EO (fraction), and the GW it is from.

    `elite` (and any mix from `group_weights`) is the weighted sum of its groups' EO, each at the
    latest GW they all have. Otherwise uses the collector's picks with chips taken out
    (`chip_free_eo`), or its `eo.parquet` if there are no picks, and falls back to the transcribed
    Elite 64 graphics for AE64/E64 (those include chips: TC and BB can't be taken out of them).
    Players not listed have EO 0 (for the graphics that understates the tail by ~5%; see data-log).
    """
    weights = group_weights(group)
    if len(weights) > 1:
        gw = min(load_eo(g, gw, collected_dir)[1] for g in weights)
        parts = [load_eo(g, gw, collected_dir)[0] * w for g, w in weights.items()]
        return pd.concat(parts, axis=1).fillna(0.0).sum(axis=1).rename("eo"), gw
    frames = []
    picks, members = collected_dir / "picks.parquet", collected_dir / "members.parquet"
    if picks.exists() and members.exists():
        frames.append(chip_free_eo(pd.read_parquet(picks), pd.read_parquet(members), group).assign(group=group))
    elif (path := collected_dir / "eo.parquet").exists():
        frames.append(pd.read_parquet(path, columns=["gw", "group", "fpl_id", "eo"]))
    if group in ("AE64", "E64"):
        from fplrank.data import elite

        frames.append(elite.load_eo("elite64", "2026-27")[["gw", "group", "fpl_id", "eo"]])
    eo = (
        pd.concat([f.assign(source=i) for i, f in enumerate(frames)])
        if frames
        else pd.DataFrame(columns=["gw", "group", "fpl_id", "eo", "source"])
    )
    eo = eo[eo["group"] == group]
    if gw is not None:
        eo = eo[eo["gw"] <= gw]
    if eo.empty:
        raise ValueError(f"No EO for group {group!r}" + (f" at or before GW{gw}" if gw else ""))
    latest = int(eo["gw"].max())
    # the collector is exact, so it wins over the graphics when both cover a GW (whole GW, not player by player)
    eo = eo[eo["gw"] == latest]
    eo = eo[eo["source"] == eo["source"].min()]
    return eo.set_index("fpl_id")["eo"].astype(float), latest


def eo_for(eo: pd.Series | pd.DataFrame, gw: int) -> pd.Series:
    """EO (fpl_id -> fraction) for `gw`. `eo` is one Series used for every GW, or a frame with one column
    per GW (e.g. Solio's EO forecast); GWs beyond its last column reuse the last one."""
    if isinstance(eo, pd.Series):
        return eo
    cols = [c for c in eo.columns if c <= gw] or [min(eo.columns)]
    return eo[max(cols)]


def adjust_projections(projections: pd.DataFrame, eo: pd.Series | pd.DataFrame, lam: float, lam_gw: int | None = None) -> pd.DataFrame:
    """Scale every `{gw}_Pts` column by (1 + lam x (EO - 1)), with that GW's EO (see `eo_for`).

    With `lam_gw`, only that GW's column is scaled; the others keep raw xP.
    """
    out = projections.copy()
    for col in out.columns:
        if (m := _PTS.match(col)) and lam_gw in (None, int(m[1])):
            out[col] = out[col] * (1 + lam * (out["ID"].map(eo_for(eo, int(m[1]))).fillna(0.0) - 1))
    return out


def _raw_xp(projections: pd.DataFrame) -> dict[tuple[int, int], float]:
    long = projections.set_index("ID")[[c for c in projections.columns if _PTS.match(c)]].stack()
    return {(int(pid), int(col.split("_")[0])): float(v) for (pid, col), v in long.items()}


def score_plan(solution: dict, projections: pd.DataFrame, eo: pd.Series, hit_cost: float = 4) -> dict:
    """Score a solution on raw xP and the field's EO.

    ev:        sum over the horizon of multiplier x raw xP for the XI (captain/TC included), minus hits
    ev_next:   the same for the next GW only
    eo_held:   next GW, sum of our multiplier x EO (how much of the field's EO we hold; the field holds ~11-12)
    exposure:  next GW, sum over players of |our multiplier - EO| x xP; 0 means we are the field
    """
    picks = solution["picks"]
    xp = _raw_xp(projections)
    weeks = sorted(int(w) for w in picks["week"].unique())
    nxt = weeks[0]
    eo = eo_for(eo, nxt)
    hits = {int(w): s.get("pt", 0) * hit_cost for w, s in solution["statistics"].items()}

    def week_ev(w):
        rows = picks[picks["week"] == w]
        return sum(xp.get((int(r.id), w), 0.0) * r.multiplier for r in rows.itertuples()) - hits.get(w, 0)

    rows = picks[picks["week"] == nxt]
    ours = {int(r.id): r.multiplier for r in rows.itertuples() if r.multiplier > 0}
    players = set(ours) | {int(i) for i in eo.index}
    exposure = sum(abs(ours.get(p, 0) - eo.get(p, 0.0)) * xp.get((p, nxt), 0.0) for p in players)
    lineup = rows[rows["lineup"] == 1]
    captain = lineup.loc[lineup["captain"] == 1, "name"]
    return {
        "ev": round(sum(week_ev(w) for w in weeks), 2),
        "ev_next": round(week_ev(nxt), 2),
        "eo_held": round(sum(m * eo.get(p, 0.0) for p, m in ours.items()), 2),
        "exposure": round(exposure, 2),
        "captain": captain.iloc[0] if len(captain) else None,
        "buy": solution["buy"],
        "sell": solution["sell"],
        "chip": solution["chip"],
    }


# ---------------------------------------------------------------------------------------------
# used by `fplrank solve` (cli.py)


def pick_eo(group: str, bootstrap: dict, next_gw: int) -> tuple[pd.Series | pd.DataFrame, str]:
    """EO for `group` (a collector group, or 'solio') and a one-line description of it."""
    if group == "solio":
        eo = load_solio_eo(bootstrap)
        first = eo_for(eo, next_gw)
        players = int((first > 0).sum())
        return eo, f"Solio forecast GW{min(eo.columns)}-{max(eo.columns)} (GW{next_gw}: {players} players, total {first.sum():.1f})"
    eo, eo_gw = load_eo(group, next_gw - 1)
    return eo, f"{group} collected GW{eo_gw}, repeated ({len(eo)} players, total {eo.sum():.1f})"


def drift_group(eo_group: str) -> str:
    """Collector group for the line's drift: the EO group if it is a fixed list (or the elite mix, measured
    against the same mix), else AE64."""
    # top1000/top10k are today's top managers, so their drift is biased low (V1); default to a fixed list
    return eo_group if eo_group in ("AE64", "E64", "elite") else "AE64"


def current_standing(team_id: int) -> tuple[int, int | None]:
    """Our total points and overall rank after the last finished GW (live API)."""
    from fplrank.data.fpl_api import FplApi

    last = FplApi().entry_history(team_id)["current"][-1]
    return last["total_points"], last.get("overall_rank")


def rank_goal_table(solutions, projections, eo, next_gw, target_rank, points, group, kappa=0.3, hit_cost=4) -> tuple[pd.DataFrame, str]:
    """S2c: P(finishing at or above the top-`target_rank` line) per λ, best first, and a line describing the gap.

    `points` are ours after GW next_gw - 1. If the collected line is older than that, it is moved on by its
    pace for the missing GWs, so both sides of the gap are after the same GW.
    """
    from fplrank.model import variance
    from fplrank.opt import rank_goal
    from fplrank.rank import target

    line = target.target_line(target_rank)
    drift, _ = target.line_drift(target_rank, group)
    gws_left = 38 - next_gw + 1
    stale = max(next_gw - 1 - line.gw, 0)
    now = line.now + stale * line.pace
    gap = now - points + drift * gws_left
    sd_line = 0.0 if math.isnan(line.sd) else line.sd  # one season of cut-offs: no spread to add
    vtable = variance.build()
    plans = {
        lam: {"moments": rank_goal.plan_moments(sol, projections, eo, vtable, kappa=kappa, hit_cost=hit_cost), "ev": sol["ev"]}
        for lam, sol in solutions.items()
    }
    table = rank_goal.choose_lambda(gap, gws_left, plans, sd_line=sd_line)
    moved = f" (GW{line.gw} line moved on {stale} GW at {line.pace:.0f} a GW)" if stale else ""
    text = (
        f"Top {target_rank:,} line {now:.0f} after GW{line.gw + stale}{moved}; we have {points}; drift vs {group} {drift:+.1f} a GW;"
        f" gap to close {gap:.0f} over {gws_left} GWs (κ = {kappa:g}, s = 1)"
    )
    return table, text
