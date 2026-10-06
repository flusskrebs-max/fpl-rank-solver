"""Ownership-weighted EV solve (S1): the upstream EV model with one "risk position" knob, λ.

Each projection is scaled by how much the target field owns the player:

    xP' = xP x (1 + λ x (EO - 1))

EO is effective ownership as a fraction (1.5 = 150%, captaincy included). λ > 0 favours players the
field owns (covering), λ < 0 favours differentials. The term is a linear proxy for the variance of our
score relative to the field, which HiGHS can't take directly (solver-design §1, §4 [C]). Centring at
EO = 1 is a scale choice, not a neutral point: it keeps adjusted values near raw xP, so λ mostly changes
*which* players are picked rather than how keen the solver is on hits. (For variance, owning a player
once is neutral at EO 0.5 and captaining him at EO 1.5.)

The CLI applies λ to the first GW of the horizon only by default (`lam_gw`): that is the GW being
decided now, and EO further out is much less certain. Later GWs use raw xP.

Every plan is then scored on the raw projections: its EV, its EV cost against λ = 0, how much of the
field's EO it holds, and its exposure (xP-weighted distance from the field), which S2 will use.

Run on Alex's PC (needs the live FPL API):

    uv run python -m fplrank.opt.ownership --team <id> --eo AE64 --lam 0 0.1 0.2
    uv run python -m fplrank.opt.ownership --team <id> --eo top1000 --sweep
    uv run python -m fplrank.opt.ownership --team <id> --eo AE64 --eo-forecast --sweep
"""

import argparse
import contextlib
import io
import re
import sys

import pandas as pd

from fplrank.baseline import solve_ev
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


def load_eo(group: str, gw: int | None = None, collected_dir=COLLECTED_DIR) -> tuple[pd.Series, int]:
    """Latest EO for `group` at or before `gw`, as fpl_id -> EO (fraction), and the GW it is from.

    Uses the collector's `eo.parquet` (exact EO for top1000, AE64, E64) and falls back to the
    transcribed Elite 64 graphics for AE64/E64. Players not listed have EO 0 (for the graphics that
    understates the tail by ~5%; see data-log).
    """
    frames = []
    path = collected_dir / "eo.parquet"
    if path.exists():
        frames.append(pd.read_parquet(path, columns=["gw", "group", "fpl_id", "eo"]))
    if group in ("AE64", "E64"):
        from fplrank.data import elite

        frames.append(elite.load_eo("elite64", "2026-27")[["gw", "group", "fpl_id", "eo"]])
    eo = pd.concat(frames) if frames else pd.DataFrame(columns=["gw", "group", "fpl_id", "eo"])
    eo = eo[eo["group"] == group]
    if gw is not None:
        eo = eo[eo["gw"] <= gw]
    if eo.empty:
        raise ValueError(f"No EO for group {group!r}" + (f" at or before GW{gw}" if gw else ""))
    latest = int(eo["gw"].max())
    # the collector is exact, so it wins over the graphics when both cover a GW
    eo = eo[eo["gw"] == latest].drop_duplicates("fpl_id", keep="first")
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


def solve_with_ownership(
    my_data: dict,
    projections: pd.DataFrame,
    eo: pd.Series,
    lam: float,
    bootstrap: dict,
    fixtures: list[dict],
    options: dict | None = None,
    lam_gw: int | None = None,
) -> dict:
    """EV solve on λ-adjusted projections; returns upstream's best solution plus `score_plan` metrics.

    `lam_gw`: apply λ to that GW only (see `adjust_projections`); None applies it to every GW.
    """
    adjusted = adjust_projections(projections, eo, lam, lam_gw)
    solution = solve_ev(my_data, adjusted, bootstrap, fixtures, options)[0]
    hit_cost = (options or {}).get("hit_cost", 4)
    return {**solution, "lam": lam, **score_plan(solution, projections, eo, hit_cost)}


def plan_key(solution: dict) -> tuple:
    """What the plan does this GW: XI, captain, bench and moves. Plans with the same key are duplicates."""
    picks = solution["picks"]
    rows = picks[picks["week"] == picks["week"].min()]
    xi = tuple(sorted(int(i) for i in rows.loc[rows["lineup"] == 1, "id"]))
    bench = tuple(int(i) for i in rows[rows["bench"] >= 0].sort_values("bench")["id"])
    cap = tuple(int(i) for i in rows.loc[rows["captain"] == 1, "id"])
    return xi, bench, cap, solution["buy"], solution["sell"], solution["chip"]


def sweep(my_data, projections, eo, bootstrap, fixtures, lams=SWEEP, options=None, lam_gw=None) -> tuple[pd.DataFrame, dict]:
    """Solve for each λ; returns one row per distinct plan (with the λ values giving it) and the solutions.

    Plans are the same if they do the same thing this GW (`plan_key`); a merged row shows the figures of
    its λ closest to 0. ev_cost is the EV given up against the λ = 0 plan (solved even if 0 is not in `lams`).
    """
    lams = sorted(set(lams) | {0.0})
    solutions = {lam: solve_with_ownership(my_data, projections, eo, lam, bootstrap, fixtures, options, lam_gw) for lam in lams}
    base_ev = solutions[0.0]["ev"]
    rows = {}
    for lam in sorted(lams, key=abs):
        s = solutions[lam]
        key = plan_key(s)
        if key in rows:
            rows[key]["lams"].append(lam)
            continue
        cols = ("ev", "ev_next", "eo_held", "exposure", "captain", "buy", "sell", "chip")
        rows[key] = {"lams": [lam], **{k: s[k] for k in cols}, "ev_cost": round(base_ev - s["ev"], 2)}
    table = pd.DataFrame(sorted(rows.values(), key=lambda r: min(r["lams"])))
    table["lams"] = table["lams"].map(lambda ls: ", ".join(f"{x:g}" for x in sorted(ls)))
    return table, solutions


def forecast_eo(group: str, next_gw: int, model=None, table: pd.DataFrame | None = None) -> pd.Series:
    """S1c: the B04 one-step forecast of `group`'s EO at the `next_gw` deadline (`eo_mean`), fpl_id -> EO.

    The collector's EO for a GW exists only after its deadline, so this is the EO we would see at it.
    Chips are not forecast (none assumed). Needs the group's data for next_gw - 1 and a registered
    Solio file for next_gw.
    """
    from fplrank.model import ownership as dyn

    model = dyn.fit_default() if model is None else model
    state = dyn.state_for(group, next_gw, table, chips_known=False)
    fc = dyn.forecast_eo(group, next_gw, state, model)
    return fc.set_index("fpl_id")["eo_mean"].astype(float)


# ---------------------------------------------------------------------------------------------
# CLI (live API: Alex's PC)


def _live_inputs(team_id: int):
    from fplrank.data.fpl_api import FplApi
    from fplrank.data.team_state import load_team_state

    api = FplApi()
    cache = {}

    def request(url):
        endpoint = url.split("/api/", 1)[1]
        if endpoint not in cache:
            cache[endpoint] = api.get(endpoint)
        return cache[endpoint]

    my_data = load_team_state(team_id, request, api)  # exact when logged in, else a warned public estimate
    return (
        my_data,
        request("https://fantasy.premierleague.com/api/bootstrap-static/"),
        request("https://fantasy.premierleague.com/api/fixtures/"),
    )


def _main(argv=None):
    from fplrank.data import projections as proj_store

    p = argparse.ArgumentParser(description="Ownership-weighted EV solve (S1)")
    p.add_argument("--team", type=int, required=True, help="FPL team (entry) id")
    p.add_argument("--eo", default="AE64", help="EO group: AE64, E64, top1000, top10k, or solio (Solio's per-GW EO forecast)")
    p.add_argument("--lam", type=float, nargs="+", help="one or more λ values")
    p.add_argument("--sweep", action="store_true", help=f"λ in {SWEEP}")
    p.add_argument(
        "--eo-forecast",
        action="store_true",
        help="EO = the ownership model's forecast for the next deadline (B04), not last GW's collected EO",
    )
    p.add_argument("--lam-all-gws", action="store_true", help="apply λ to every GW of the horizon (default: the next GW only)")
    p.add_argument(
        "--projections",
        help="Solio CSV, or 'ep_next' for FPL's free projections (default: newest Solio file registered for the next GW, else ep_next)",
    )
    p.add_argument("--horizon", type=int, default=5)
    p.add_argument("--secs", type=int, default=600, help="time limit per solve (upstream default; solves usually finish in seconds)")
    p.add_argument("--target-rank", type=int, help="S2: also choose λ for finishing at or above this overall rank")
    p.add_argument("--points", type=int, help="S2: our total points now (default: from the FPL API)")
    p.add_argument("--drift-group", help="S2: collector group for the line's drift (default: --eo if AE64/E64, else AE64)")
    p.add_argument("--kappa", type=float, default=0.3, help="S2: share of our projected edge over the field taken as real")
    sys.stdout.reconfigure(encoding="utf-8")  # player names and λ on the Windows console
    args = p.parse_args(argv)

    my_data, bootstrap, fixtures = _live_inputs(args.team)
    next_gw = next(e["id"] for e in bootstrap["events"] if e["is_next"])
    path = args.projections
    if path is None:
        try:
            path = proj_store.latest(next_gw)
        except LookupError:
            print("No Solio file registered for this GW: using FPL's ep_next (crude, one GW repeated per fixture)")
            path = "ep_next"
    if str(path) == "ep_next":
        projections = proj_store.from_ep_next(bootstrap, fixtures, args.horizon)
    else:
        projections = pd.read_csv(path, encoding="utf-8-sig")
    if args.eo_forecast and args.eo == "solio":
        p.error("--eo-forecast forecasts a collected group's EO; Solio's export is already a forecast")
    if args.eo == "solio":
        eo = load_solio_eo(bootstrap)
        first = eo_for(eo, next_gw)
        eo_text = (
            f"Solio forecast GW{min(eo.columns)}-{max(eo.columns)} (GW{next_gw}: {int((first > 0).sum())} players, total {first.sum():.1f})"
        )
    elif args.eo_forecast:
        eo = forecast_eo(args.eo, next_gw)
        eo_text = f"{args.eo} forecast for the GW{next_gw} deadline, repeated ({int((eo > 0.005).sum())} players, total {eo.sum():.1f})"
    else:
        eo, eo_gw = load_eo(args.eo, next_gw - 1)
        eo_text = f"{args.eo} collected GW{eo_gw}, repeated ({len(eo)} players, total {eo.sum():.1f})"
    lam_gw = None if args.lam_all_gws else next_gw
    lam_text = "every GW" if lam_gw is None else f"GW{next_gw} only"
    print(f"GW{next_gw} plan, horizon {args.horizon}; projections {path}; EO {eo_text}; λ on {lam_text}")

    lams = SWEEP if args.sweep or not args.lam else args.lam
    options = {"horizon": args.horizon, "secs": args.secs}
    with contextlib.redirect_stdout(io.StringIO()):  # upstream prints a lot per solve
        table, solutions = sweep(my_data, projections, eo, bootstrap, fixtures, lams, options, lam_gw)
    with pd.option_context("display.width", 200, "display.max_colwidth", 60):
        print(table.to_string(index=False))
    if args.target_rank:
        _rank_goal(args, solutions, projections, eo, next_gw)


def _rank_goal(args, solutions, projections, eo, next_gw):
    """S2c: P(finishing at or above the target line) per λ, and the λ that maximises it."""
    from fplrank.data.fpl_api import FplApi
    from fplrank.model import variance
    from fplrank.opt import rank_goal
    from fplrank.rank import target

    points = args.points
    if points is None:
        points = FplApi().entry_history(args.team)["current"][-1]["total_points"]
    # top1000/top10k are today's top managers, so their drift is biased low (V1); default to a fixed list
    group = args.drift_group or (args.eo if args.eo in ("AE64", "E64") else "AE64")
    line = target.target_line(args.target_rank)
    drift, _ = target.line_drift(args.target_rank, group)
    gws_left = 38 - next_gw + 1
    gap = line.now - points + drift * gws_left
    vtable = variance.build()
    plans = {
        lam: {"moments": rank_goal.plan_moments(sol, projections, eo, vtable, kappa=args.kappa), "ev": sol["ev"]}
        for lam, sol in solutions.items()
    }
    table = rank_goal.choose_lambda(gap, gws_left, plans, sd_line=line.sd)
    print()
    print(
        f"Top {args.target_rank:,} line {line.now:.0f} after GW{line.gw}; we have {points}; drift vs {group} {drift:+.1f} a GW;"
        f" gap to close {gap:.0f} over {gws_left} GWs (κ = {args.kappa:g}, s = 1)"
    )
    with pd.option_context("display.width", 200):
        print(table.round(3).to_string(index=False))
    print(rank_goal.report(table, args.target_rank, args.kappa))


if __name__ == "__main__":
    sys.exit(_main())
