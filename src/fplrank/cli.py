"""`fplrank solve`: Sertalp's solve.py, plus our two extras (the EO and the λ choice).

    uv run fplrank solve [his flags]                                  # exactly his solver
    uv run fplrank solve [his flags] --eo AE64 --target 10000          # λ with the best P(top 10,000)
    uv run fplrank solve [his flags] --eo AE64 --lam 0.1               # a fixed λ

His flags (horizon, use_wc, banned, team_id, ...) and his settings files are passed to his
`run/solve.py::solve_regular` unchanged. With `--eo`, his projections are read as usual and scaled by
xP x (1 + λ x (EO - 1)) for the next GW only (`opt.ownership`), once per λ. The plan with the best
P(reaching the target line) (`opt.rank_goal`) is printed with his normal output under a short λ block.
"""

import argparse
import contextlib
import io
import sys
import time
from dataclasses import dataclass

import pandas as pd

from fplrank.baseline import _patched, _solve_module
from fplrank.opt import ownership

BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"


@dataclass
class Run:
    solution: dict  # his best solution (first of his iterations)
    options: dict  # his options after settings files and flags
    projections: pd.DataFrame  # his projections as read, before any λ
    output: str  # what he printed ("" when not captured)


def live_request():
    """His `cached_request`, served by our FPL API client (saves a dated snapshot of every payload)."""
    from fplrank.data.fpl_api import FplApi

    api = FplApi()
    cache = {}

    def request(url):
        endpoint = url.split("/api/", 1)[1]
        if endpoint not in cache:
            cache[endpoint] = api.get(endpoint)
        return cache[endpoint]

    return request


def run(argv: list[str], adjust=None, request=None, quiet: bool = False) -> Run:
    """Run his `solve_regular` with `argv` as his command line.

    adjust(projections, options) -> projections changes his projections after he reads them.
    quiet: capture what he prints in `Run.output` instead of printing it.
    """
    solve = _solve_module()
    from dev import data_parser, solver

    seen, solved = {}, []
    read, solve_mp = solver.read_data, solve.solve_multi_period_fpl

    def read_hook(options, source=None):
        raw = read(options, source)
        seen.update(options=options, projections=raw)
        return adjust(raw, options) if adjust else raw

    def keep(data, opts):
        response = solve_mp(data, opts)
        solved.append(response)
        return response

    requests = {"cached_request": request} if request else {}
    out = io.StringIO()
    argv_was = sys.argv
    sys.argv = ["solve.py", *argv]
    try:
        with (
            _patched(solve, solve_multi_period_fpl=keep, **requests),
            _patched(solver, read_data=read_hook, **requests),
            _patched(data_parser, **requests),
            contextlib.redirect_stdout(out) if quiet else contextlib.nullcontext(),
        ):
            solve.solve_regular()
    finally:
        sys.argv = argv_was
    return Run(solved[0][0], seen["options"], seen["projections"], out.getvalue())


def next_gw(options: dict, bootstrap: dict) -> int:
    """The GW he plans from: his `override_next_gw`, else FPL's next event."""
    if options.get("override_next_gw"):
        return int(options["override_next_gw"])
    return next(e["id"] for e in bootstrap["events"] if e["is_next"])


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fplrank solve",
        description="Sertalp's solve.py (all his flags pass through unchanged) plus the EO and λ choice.",
    )
    p.add_argument("--eo", help="EO group: AE64, E64, top1000, top10k or solio (default AE64 when --target is given)")
    p.add_argument("--target", type=int, help="target overall rank: choose the λ with the best P(finishing at or above it)")
    p.add_argument("--lam", type=float, help="fix λ instead of choosing it (0 = his EV plan)")
    p.add_argument("--points", type=int, help="our total points now, for --target (default: from the FPL API)")
    return p


def solve(argv: list[str], request=None, load_eo=ownership.pick_eo, standing=None) -> int:
    p = parser()
    ours, theirs = p.parse_known_args(argv)
    request = request or live_request()
    if ours.eo is None and ours.target is None and ours.lam is None:
        run(theirs, request=request)
        return 0
    if ours.target is None and ours.lam is None:
        p.error("--eo needs --target (to choose λ) or --lam (to fix it)")
    group = ours.eo or "AE64"
    lams = sorted({0.0} | ({ours.lam} if ours.lam is not None else set(ownership.SWEEP)), key=abs)

    runs, eo, gw, eo_text = {}, None, None, ""
    for i, lam in enumerate(lams, 1):
        start = time.perf_counter()
        if lam == 0.0:
            runs[lam] = run(theirs, request=request, quiet=True)
            gw = next_gw(runs[lam].options, request(BOOTSTRAP))
            eo, eo_text = load_eo(group, request(BOOTSTRAP), gw)
        else:
            runs[lam] = run(
                theirs, lambda proj, _, lam=lam, eo=eo, gw=gw: ownership.adjust_projections(proj, eo, lam, gw), request, quiet=True
            )
        print(f"  {i}/{len(lams)}: λ = {lam:g} solved in {time.perf_counter() - start:.0f}s", flush=True)

    base = runs[0.0]
    hit_cost = base.options.get("hit_cost", 4)
    solutions = {lam: {**r.solution, **ownership.score_plan(r.solution, base.projections, eo, hit_cost)} for lam, r in runs.items()}
    print()
    print(f"EO {eo_text}; λ on GW{gw} only")
    if ours.target:
        points = ours.points
        if points is None:
            team_id = base.options.get("team_id")
            if team_id is None:
                p.error("--target needs --points or his --team_id")
            points = (standing or ownership.current_standing)(int(team_id))[0]
        table, gap_text = ownership.rank_goal_table(solutions, base.projections, eo, gw, ours.target, points, ownership.drift_group(group))
        if ours.lam is not None:  # fixed λ: report it, not the best one
            table = pd.concat([table[table["lam"] == ours.lam], table[table["lam"] != ours.lam]], ignore_index=True)
        chosen = float(table.iloc[0]["lam"])
        print(gap_text)
        print("P by λ: " + ", ".join(f"{r.lam:g} {r.p:.0%}" for r in table.sort_values("lam").itertuples()))
        from fplrank.opt import rank_goal

        print(rank_goal.report(table, ours.target))
    else:
        chosen = ours.lam
        cost = solutions[0.0]["ev"] - solutions[chosen]["ev"]
        print(f"λ = {chosen:g} (fixed), EV cost {cost:.1f} points")
    print(f"\n--- Sertalp's solver, plan for λ = {chosen:g} ---")
    print(runs[chosen].output)
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    sys.stdout.reconfigure(encoding="utf-8")  # player names and λ on the Windows console
    if not argv or argv[0] != "solve":
        print("usage: fplrank solve [his solve.py flags] [--eo GROUP] [--target RANK] [--lam λ] [--points N]")
        return 2
    return solve(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
