"""Ownership-weighted EV solve (S1): the upstream EV model with one "risk position" knob, λ.

Each projection is scaled by how much the target field owns the player:

    xP' = xP x (1 + λ x (EO - 1))

EO is effective ownership as a fraction (1.5 = 150%, captaincy included). λ > 0 favours players the
field owns (covering), λ < 0 favours differentials. The term is a linear proxy for the variance of our
score relative to the field, which HiGHS can't take directly (solver-design §1, §4 [C]). Centring at
EO = 1 is a scale choice, not a neutral point: it keeps adjusted values near raw xP, so λ mostly changes
*which* players are picked rather than how keen the solver is on hits. (For variance, owning a player
once is neutral at EO 0.5 and captaining him at EO 1.5.)

Every plan is then scored on the raw projections: its EV, its EV cost against λ = 0, how much of the
field's EO it holds, and its exposure (xP-weighted distance from the field), which S2 will use.

Run on Alex's PC (needs the live FPL API):

    uv run python -m fplrank.opt.ownership --team <id> --eo AE64 --lam 0 0.1 0.2
    uv run python -m fplrank.opt.ownership --team <id> --eo top1000 --sweep
"""

import argparse
import contextlib
import io
import re
import sys

import pandas as pd

from fplrank.baseline import _patched, _upstream, solve_ev
from fplrank.paths import COLLECTED_DIR

SWEEP = (-0.3, -0.2, -0.1, -0.05, 0.0, 0.05, 0.1, 0.2, 0.3)
_PTS = re.compile(r"^(\d+)_Pts$")


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


def adjust_projections(projections: pd.DataFrame, eo: pd.Series, lam: float) -> pd.DataFrame:
    """Scale every `{gw}_Pts` column by (1 + lam x (EO - 1)). The same EO is used for every GW."""
    out = projections.copy()
    factor = 1 + lam * (out["ID"].map(eo).fillna(0.0) - 1)
    for col in out.columns:
        if _PTS.match(col):
            out[col] = out[col] * factor
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
) -> dict:
    """EV solve on λ-adjusted projections; returns upstream's best solution plus `score_plan` metrics."""
    adjusted = adjust_projections(projections, eo, lam)
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


def sweep(my_data, projections, eo, bootstrap, fixtures, lams=SWEEP, options=None) -> tuple[pd.DataFrame, dict]:
    """Solve for each λ; returns one row per distinct plan (with the λ values giving it) and the solutions.

    Plans are the same if they do the same thing this GW (`plan_key`); a merged row shows the figures of
    its λ closest to 0. ev_cost is the EV given up against the λ = 0 plan (solved even if 0 is not in `lams`).
    """
    lams = sorted(set(lams) | {0.0})
    solutions = {lam: solve_with_ownership(my_data, projections, eo, lam, bootstrap, fixtures, options) for lam in lams}
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


# ---------------------------------------------------------------------------------------------
# CLI (live API: Alex's PC)


def _live_inputs(team_id: int):
    from fplrank.data.fpl_api import FplApi

    api = FplApi()
    cache = {}

    def request(url):
        endpoint = url.split("/api/", 1)[1]
        if endpoint not in cache:
            cache[endpoint] = api.get(endpoint)
        return cache[endpoint]

    solver = _upstream()
    with _patched(solver, cached_request=request):
        my_data = solver.generate_team_json(team_id, {})
    return (
        my_data,
        request("https://fantasy.premierleague.com/api/bootstrap-static/"),
        request("https://fantasy.premierleague.com/api/fixtures/"),
    )


def _main(argv=None):
    from fplrank.data import projections as proj_store

    p = argparse.ArgumentParser(description="Ownership-weighted EV solve (S1)")
    p.add_argument("--team", type=int, required=True, help="FPL team (entry) id")
    p.add_argument("--eo", default="AE64", help="EO group: AE64, E64 or top1000")
    p.add_argument("--lam", type=float, nargs="+", help="one or more λ values")
    p.add_argument("--sweep", action="store_true", help=f"λ in {SWEEP}")
    p.add_argument(
        "--projections",
        help="Solio CSV, or 'ep_next' for FPL's free projections (default: newest Solio file registered for the next GW, else ep_next)",
    )
    p.add_argument("--horizon", type=int, default=5)
    p.add_argument("--secs", type=int, default=600, help="time limit per solve (upstream default; solves usually finish in seconds)")
    args = p.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")  # player names on the Windows console

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
    eo, eo_gw = load_eo(args.eo, next_gw - 1)
    print(f"GW{next_gw} plan, horizon {args.horizon}; projections {path}; EO {args.eo} GW{eo_gw} ({len(eo)} players, total {eo.sum():.1f})")

    lams = SWEEP if args.sweep or not args.lam else args.lam
    options = {"horizon": args.horizon, "secs": args.secs}
    with contextlib.redirect_stdout(io.StringIO()):  # upstream prints a lot per solve
        table, _ = sweep(my_data, projections, eo, bootstrap, fixtures, lams, options)
    with pd.option_context("display.width", 200, "display.max_colwidth", 60):
        print(table.to_string(index=False))


if __name__ == "__main__":
    sys.exit(_main())
