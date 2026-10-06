"""Weekly report (R1): one command from live data to `reports/GW{n}.md`, read before the deadline.

The harness takes five inputs (`Inputs`): current EO, EV projections, our current team, our current
points and rank, and a rank goal. `run(inputs, mode)` turns them into the report:

- mode "optimum" (R1): the S1 λ sweep, then S2c picks the λ that maximises P(reaching the target line).
- mode "simulate" (R2): the optimum report, then `runs` re-solves at the chosen λ with upstream's
  `randomized` noise (seeds 1..runs; per GW and player `Pts x (92 - xMins) / 134 x N(0, 1) x noise`,
  added after the λ adjustment). The report adds how often each first-GW move set, captain and chip
  comes out on top, next to the recommended plan. See `docs/tasks/briefs/R1-weekly-report.md`.

The live CLI snapshots the FPL API (every call is saved under data/snapshots/), picks projections (newest
Solio file for the GW, else `ep_next` with a loud warning) and EO (last collected GW, B04's deadline
forecast with `--eo-forecast`, or Solio's per-GW forecast with `--eo solio`). `reports/` is git-ignored:
it holds Solio-derived numbers.

Run on Alex's PC (needs the live FPL API):

    uv run python -m fplrank.weekly --team <id> --target 10000
    uv run python -m fplrank.weekly --team <id> --eo solio --target 10000
    uv run python -m fplrank.weekly --team <id> --target 10000 --mode simulate --runs 30 --sim-secs 60
"""

import argparse
import contextlib
import io
import sys
from dataclasses import dataclass
from datetime import UTC, datetime

import pandas as pd

from fplrank.opt import ownership as ow
from fplrank.paths import PROJECT_ROOT

REPORTS_DIR = PROJECT_ROOT / "reports"
MODES = ("optimum", "simulate")
EP_NEXT_WARNING = "WARNING: no Solio file for this GW, so this uses FPL's ep_next (a form measure, not a projection). Don't use this plan."


@dataclass
class Inputs:
    """Everything the harness needs; `gather` fills it from the live API, tests build it from snapshots."""

    gw: int  # the GW being planned (the next deadline)
    team_id: int
    my_data: dict  # current team, as upstream's generate_team_json gives it
    bootstrap: dict
    fixtures: list
    projections: pd.DataFrame  # EV projections (Solio export shape)
    eo: pd.Series | pd.DataFrame  # current EO: fpl_id -> EO, or a per-GW table (Solio)
    points: int | None = None  # our total points now
    rank: int | None = None  # our overall rank now (shown in the report; the goal works on points)
    target: int | None = None  # rank goal, e.g. 10000; None recommends the EV plan
    sources: str = ""  # where the projections and EO came from
    ep_next: bool = False  # projections are FPL's ep_next, not Solio: the report carries a warning


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


def _move_set(sol: dict) -> str:
    buy, sell = sol["buy"], sol["sell"]
    return "no transfers" if buy in ("", "-") else f"in {buy}; out {sell}"


def _chip(sol: dict) -> str:
    return sol["chip"] if sol["chip"] not in ("", "-", None) else "no chip"


def simulate(inputs: "Inputs", lam: float, runs: int, options: dict, lam_gw: int | None, noise: float = 1.0) -> pd.DataFrame:
    """R2: `runs` solves at `lam` on noisy projections (upstream's `randomized`, seeds 1..runs).

    One row per run: seed, moves, captain, chip, and EV on the raw (noise-free) projections.
    """
    rows = []
    for seed in range(1, runs + 1):
        opts = {**options, "randomized": True, "randomization_seed": seed, "randomization_strength": noise}
        with contextlib.redirect_stdout(io.StringIO()):
            sol = ow.solve_with_ownership(
                inputs.my_data, inputs.projections, inputs.eo, lam, inputs.bootstrap, inputs.fixtures, opts, lam_gw
            )
        rows.append({"seed": seed, "moves": _move_set(sol), "captain": sol["captain"], "chip": _chip(sol), "ev": sol["ev"]})
    return pd.DataFrame(rows)


def render_stability(sims: pd.DataFrame, lam: float, recommended: dict, noise: float = 1.0) -> str:
    """The simulate section: how often each move set, captain and chip came out on top, against the recommendation."""
    n = len(sims)
    rec = {"moves": _move_set(recommended), "captain": recommended["captain"], "chip": _chip(recommended)}
    out = [
        f"## Stability: {n} noisy solves at λ = {lam:g}",
        "",
        f"Each run re-solves with upstream's projection noise (strength {noise:g}, seeds 1-{n}). "
        f"The recommended moves came out on top in {(sims['moves'] == rec['moves']).sum()} of {n} runs, "
        f"its captain in {(sims['captain'] == rec['captain']).sum()}, its chip choice in {(sims['chip'] == rec['chip']).sum()}.",
        "",
    ]
    for col, title in (("moves", "Moves"), ("captain", "Captain"), ("chip", "Chip")):
        g = sims.groupby(col).agg(runs=("seed", "size"), ev=("ev", "mean")).sort_values(["runs", "ev"], ascending=False)
        table = pd.DataFrame(
            {
                title: [f"{k} (recommended)" if k == rec[col] else str(k) for k in g.index],
                "runs": g["runs"].to_numpy(),
                "share": [f"{r / n:.0%}" for r in g["runs"]],
                "mean EV (raw)": [f"{v:.1f}" for v in g["ev"]],
            }
        )
        out += [f"### {title}", "", _md_table(table), ""]
    return "\n".join(out)


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


def run(
    inputs: Inputs,
    mode: str = "optimum",
    horizon: int = 5,
    secs: int = 600,
    kappa: float = 0.3,
    drift_group: str = "AE64",
    lam_all_gws: bool = False,
    lams=ow.SWEEP,
    options: dict | None = None,
    now: datetime | None = None,
    runs: int = 30,
    sim_secs: int = 60,
    noise: float = 1.0,
) -> str:
    """The weekly report for `inputs` as markdown. `options` go to the upstream solve on top of horizon/secs.

    mode "simulate" adds `runs` noisy solves at the chosen λ, each limited to `sim_secs`.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}, not {mode!r}")
    if mode == "simulate" and runs < 1:
        raise ValueError("mode 'simulate' needs runs >= 1")
    if inputs.target is not None and inputs.points is None:
        raise ValueError("a rank goal needs our current points")

    opts = {"horizon": horizon, "secs": secs, **(options or {})}
    lam_gw = None if lam_all_gws else inputs.gw
    with contextlib.redirect_stdout(io.StringIO()):  # upstream prints a lot per solve
        table, solutions = ow.sweep(inputs.my_data, inputs.projections, inputs.eo, inputs.bootstrap, inputs.fixtures, lams, opts, lam_gw)
    rank = None
    if inputs.target:
        rtable, gap_text = ow.rank_goal_table(
            solutions, inputs.projections, inputs.eo, inputs.gw, inputs.target, inputs.points, drift_group, kappa
        )
        rank = (rtable, gap_text, inputs.target, kappa)

    standing = []
    if inputs.points is not None:
        standing.append(f"{inputs.points} points")
    if inputs.rank is not None:
        standing.append(f"overall rank {inputs.rank:,}")
    goal = f"goal top {inputs.target:,}" if inputs.target else "no rank goal"
    lam_text = "every GW" if lam_gw is None else f"GW{inputs.gw} only"
    sources = f"Now: {', '.join(standing) or 'standing unknown'}; {goal}. {inputs.sources} Horizon {horizon} GWs, λ on {lam_text}."
    if inputs.ep_next:
        sources = f"> **{EP_NEXT_WARNING}**\n\n{sources}"
    text = render(inputs.gw, inputs.team_id, sources, table, solutions, rank, now)
    if mode == "simulate":
        lam = 0.0 if rank is None else float(rank[0].iloc[0]["lam"])
        sims = simulate(inputs, lam, runs, {**opts, "secs": sim_secs}, lam_gw, noise)
        text += "\n" + render_stability(sims, lam, solutions[lam], noise)
    return text


def gather(args) -> Inputs:
    """Inputs from the live FPL API (snapshotted), registered Solio files and collected EO."""
    my_data, bootstrap, fixtures = ow._live_inputs(args.team)
    gw = next(e["id"] for e in bootstrap["events"] if e["is_next"])
    projections, proj_text = ow.pick_projections(args.projections, bootstrap, fixtures, gw, args.horizon)
    eo, eo_text = ow.pick_eo(args.eo, bootstrap, gw, forecast=args.eo_forecast)
    points, rank = ow.current_standing(args.team)
    ep_next = proj_text == "ep_next"
    if ep_next:
        print("\n" + "!" * 100 + f"\n{EP_NEXT_WARNING}\n" + "!" * 100 + "\n")
    return Inputs(
        gw=gw,
        team_id=args.team,
        my_data=my_data,
        bootstrap=bootstrap,
        fixtures=fixtures,
        projections=projections,
        eo=eo,
        points=points if args.points is None else args.points,
        rank=rank if args.rank is None else args.rank,
        target=args.target,
        sources=f"Projections: {proj_text}. EO: {eo_text}.",
        ep_next=ep_next,
    )


def _main(argv=None):
    p = argparse.ArgumentParser(description="Weekly report: snapshot, S1 sweep, S2c choice, reports/GW{n}.md")
    p.add_argument("--team", type=int, required=True, help="FPL team (entry) id")
    p.add_argument("--target", type=int, help="target overall rank, e.g. 10000 (without it the EV plan is recommended)")
    p.add_argument(
        "--mode",
        choices=MODES,
        default="optimum",
        help="optimum: S1 + S2c (R1); simulate: optimum plus noisy re-solves at the chosen λ (R2)",
    )
    p.add_argument("--eo", default="AE64", help="EO group: AE64, E64, top1000, top10k or solio")
    p.add_argument("--eo-forecast", action="store_true", help="EO = B04's forecast for the deadline, not last GW's collected EO")
    p.add_argument("--lam-all-gws", action="store_true", help="apply λ to every GW of the horizon (default: the next GW only)")
    p.add_argument("--points", type=int, help="our total points now (default: from the FPL API)")
    p.add_argument("--rank", type=int, help="our overall rank now (default: from the FPL API)")
    p.add_argument("--projections", help="Solio CSV or 'ep_next' (default: newest Solio file for the GW, else ep_next)")
    p.add_argument("--horizon", type=int, default=5)
    p.add_argument("--secs", type=int, default=600, help="time limit per solve")
    p.add_argument("--runs", type=int, default=30, help="simulate: number of noisy solves")
    p.add_argument("--sim-secs", type=int, default=60, help="simulate: time limit per noisy solve")
    p.add_argument("--noise", type=float, default=1.0, help="simulate: upstream's randomization_strength")
    p.add_argument("--kappa", type=float, default=0.3, help="share of our projected edge over the field taken as real")
    p.add_argument("--drift-group", help="collector group for the line's drift (default: --eo if AE64/E64, else AE64)")
    p.add_argument("--out", help="report path (default: reports/GW{n}.md)")
    args = p.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if args.eo_forecast and args.eo == "solio":
        p.error("--eo-forecast forecasts a collected group's EO; Solio's export is already a forecast")
    if args.mode == "simulate" and args.runs < 1:
        p.error("--runs must be at least 1")

    inputs = gather(args)
    print(f"GW{inputs.gw}: solving {len(ow.SWEEP)} values of λ ...")
    if args.mode == "simulate":
        print(f"then {args.runs} noisy solves at the chosen λ (up to {args.sim_secs}s each) ...")
    group = ow.drift_group(args.eo, args.drift_group)
    text = run(
        inputs,
        args.mode,
        args.horizon,
        args.secs,
        args.kappa,
        group,
        args.lam_all_gws,
        runs=args.runs,
        sim_secs=args.sim_secs,
        noise=args.noise,
    )
    path = REPORTS_DIR / f"GW{inputs.gw}.md" if args.out is None else args.out
    REPORTS_DIR.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    print(f"\nSaved {path}")


if __name__ == "__main__":
    sys.exit(_main())
