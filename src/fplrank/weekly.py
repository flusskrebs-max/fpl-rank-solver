"""Weekly report (R1): one command from live data to `reports/GW{n}.md`, read before the deadline.

Snapshots the FPL API (every call is saved under data/snapshots/), picks projections (newest Solio file
for the GW, else `ep_next`) and EO, runs the S1 λ sweep and, with `--target`, S2c's choice of λ. The
report gives the recommended plan (moves, captain, chip, XI), the EV plan if different, the two nearest
alternatives and the whole sweep. `reports/` is git-ignored: it holds Solio-derived numbers.

Run on Alex's PC (needs the live FPL API):

    uv run python -m fplrank.weekly --team <id> --target 10000
    uv run python -m fplrank.weekly --team <id> --eo solio --target 10000
"""

import argparse
import contextlib
import io
import sys
from datetime import UTC, datetime

import pandas as pd

from fplrank.opt import ownership as ow
from fplrank.paths import PROJECT_ROOT

REPORTS_DIR = PROJECT_ROOT / "reports"


def _md_table(df: pd.DataFrame) -> str:
    rows = [[str(c) for c in df.columns], ["---"] * len(df.columns)]
    rows += [[str(v) for v in r] for r in df.itertuples(index=False)]
    return "\n".join("| " + " | ".join(r) + " |" for r in rows)


def _moves(sol: dict) -> str:
    buy, sell = sol["buy"], sol["sell"]
    moves = "no transfers" if buy in ("", "-") else f"in {buy}; out {sell}"
    chip = sol["chip"] if sol["chip"] not in ("", "-", None) else "no chip"
    return f"{moves} · captain {sol['captain']} · {chip}"


def _team(sol: dict) -> str:
    picks = sol["picks"]
    rows = picks[picks["week"] == picks["week"].min()]
    xi = [f"{r.name} (C)" if r.captain == 1 else r.name for r in rows[rows["lineup"] == 1].itertuples()]
    bench = rows[rows["bench"] >= 0].sort_values("bench")["name"]
    return f"XI: {', '.join(xi)}. Bench: {', '.join(bench)}."


def _plan_block(title: str, sol: dict, extra: str = "") -> list[str]:
    return [
        f"## {title}",
        "",
        f"- {_moves(sol)}",
        f"- EV {sol['ev']:.1f} over the horizon, {sol['ev_next']:.1f} this GW{extra}",
        f"- {_team(sol)}",
        "",
    ]


def render(
    gw: int,
    team_id: int,
    sources: str,
    sweep_table: pd.DataFrame,
    solutions: dict,
    rank: tuple[pd.DataFrame, str, int, float] | None = None,
    now: datetime | None = None,
) -> str:
    """The report as markdown.

    rank: S2c's (table best first, gap line, target rank, κ), or None to recommend the EV plan (λ = 0).
    """
    now = now or datetime.now(UTC)
    out = [f"# GW{gw} weekly report, team {team_id}", "", f"Made {now:%Y-%m-%d %H:%M} UTC. {sources}", ""]
    base = solutions[0.0]
    if rank is None:
        out += ["No target rank given, so the recommendation is the EV plan (λ = 0).", ""]
        out += _plan_block("Recommended: λ = 0 (EV plan)", base)
    else:
        table, gap_text, target_rank, kappa = rank
        p = table.set_index("lam")["p"]
        best = float(table.iloc[0]["lam"])
        sol = solutions[best]
        out += [gap_text + ".", ""]
        cost = base["ev"] - sol["ev"]
        extra = f"; P(top {target_rank:,}) {p[best]:.0%} vs {p[0.0]:.0%} for the EV plan; EV cost {cost:.1f} (κ = {kappa:g})"
        out += _plan_block(f"Recommended: λ = {best:g}", sol, extra)
        if ow.plan_key(sol) != ow.plan_key(base):
            out += _plan_block("EV plan (λ = 0)", base, f"; P(top {target_rank:,}) {p[0.0]:.0%}")
        # the two best-scoring plans that differ from the recommended one and from each other
        seen, alts = {ow.plan_key(sol)}, []
        for lam in table["lam"]:
            key = ow.plan_key(solutions[lam])
            if key not in seen and len(alts) < 2:
                seen.add(key)
                s = solutions[lam]
                alts.append(
                    {
                        "λ": f"{lam:g}",
                        "P": f"{p[lam]:.0%}",
                        "EV cost": f"{base['ev'] - s['ev']:.1f}",
                        "captain": s["captain"],
                        "in": s["buy"],
                        "out": s["sell"],
                        "chip": s["chip"],
                    }
                )
        if alts:
            out += ["## Nearest alternatives", "", _md_table(pd.DataFrame(alts)), ""]
    out += ["## All plans (S1 sweep)", "", _md_table(sweep_table), ""]
    return "\n".join(out)


def _main(argv=None):
    p = argparse.ArgumentParser(description="Weekly report: snapshot, S1 sweep, S2c choice, reports/GW{n}.md")
    p.add_argument("--team", type=int, required=True, help="FPL team (entry) id")
    p.add_argument("--target", type=int, help="target overall rank, e.g. 10000 (without it the EV plan is recommended)")
    p.add_argument("--eo", default="AE64", help="EO group: AE64, E64, top1000, top10k or solio")
    p.add_argument("--points", type=int, help="our total points now (default: from the FPL API)")
    p.add_argument("--projections", help="Solio CSV or 'ep_next' (default: newest Solio file for the GW, else ep_next)")
    p.add_argument("--horizon", type=int, default=5)
    p.add_argument("--secs", type=int, default=600, help="time limit per solve")
    p.add_argument("--kappa", type=float, default=0.3, help="share of our projected edge over the field taken as real")
    p.add_argument("--drift-group", help="collector group for the line's drift (default: --eo if AE64/E64, else AE64)")
    p.add_argument("--out", help="report path (default: reports/GW{n}.md)")
    args = p.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")

    my_data, bootstrap, fixtures = ow._live_inputs(args.team)
    gw = next(e["id"] for e in bootstrap["events"] if e["is_next"])
    projections, proj_text = ow.pick_projections(args.projections, bootstrap, fixtures, gw, args.horizon)
    eo, eo_text = ow.pick_eo(args.eo, bootstrap, gw)
    sources = f"Projections: {proj_text}. EO: {eo_text}. Horizon {args.horizon} GWs."
    if proj_text == "ep_next":
        warning = "WARNING: no Solio file for this GW, so this uses FPL's ep_next (a form measure, not a projection). Don't use this plan."
        print(warning)
        sources += f"\n\n> **{warning}**"
    print(f"GW{gw}: solving {len(ow.SWEEP)} values of λ ...")

    with contextlib.redirect_stdout(io.StringIO()):  # upstream prints a lot per solve
        table, solutions = ow.sweep(my_data, projections, eo, bootstrap, fixtures, ow.SWEEP, {"horizon": args.horizon, "secs": args.secs})
    rank = None
    if args.target:
        points = args.points if args.points is not None else ow.current_points(args.team)
        group = ow.drift_group(args.eo, args.drift_group)
        rtable, gap_text = ow.rank_goal_table(solutions, projections, eo, gw, args.target, points, group, args.kappa)
        rank = (rtable, gap_text, args.target, args.kappa)

    path = REPORTS_DIR / f"GW{gw}.md" if args.out is None else args.out
    text = render(gw, args.team, sources, table, solutions, rank)
    REPORTS_DIR.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    print(f"\nSaved {path}")


if __name__ == "__main__":
    sys.exit(_main())
