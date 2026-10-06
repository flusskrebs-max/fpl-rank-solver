"""`fplrank solve`: Sertalp's solve.py, plus our two extras (the EO and the λ choice).

    uv run fplrank solve [his flags]                                  # exactly his solver
    uv run fplrank solve [his flags] --eo AE64 --target 10000          # λ with the best P(top 10,000)
    uv run fplrank solve [his flags] --eo AE64 --lam 0.1               # a fixed λ
    uv run fplrank solve [his flags] --eo AE64 --target 10000 --sims 50  # plus his simulations at that λ

His flags (horizon, use_wc, banned, team_id, ...) and his settings files are passed to his
`run/solve.py::solve_regular` unchanged. With `--eo`, his projections are read as usual and scaled by
xP x (1 + λ x (EO - 1)) for the next GW only (`opt.ownership`), once per λ. The plan with the best
P(reaching the target line) (`opt.rank_goal`) is printed with his normal output under a short λ block.

`--sims N` then does what his `run/simulations.py` does, at the chosen λ: N runs of `solve_regular` with
`randomized` on (his noise, applied to the λ-scaled projections), followed by his `run/sensitivity.py`
summary of the plans those runs saved.
"""

import argparse
import contextlib
import io
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass

import pandas as pd

from fplrank.opt import ownership
from fplrank.upstream import patched, solve_module

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


def run(argv: list[str], adjust=None, request=None, quiet: bool = False, runtime_options: dict | None = None) -> Run:
    """Run his `solve_regular` with `argv` as his command line.

    adjust(projections, options) -> projections changes his projections after he reads them.
    quiet: capture what he prints in `Run.output` instead of printing it.
    runtime_options: handed to `solve_regular` the way his simulations script does.
    """
    solve = solve_module()
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
            patched(solve, solve_multi_period_fpl=keep, **requests),
            patched(solver, read_data=read_hook, **requests),
            patched(data_parser, **requests),
            contextlib.redirect_stdout(out) if quiet else contextlib.nullcontext(),
        ):
            solve.solve_regular(runtime_options)
    finally:
        sys.argv = argv_was
    return Run(solved[0][0], seen["options"], seen["projections"], out.getvalue())


def simulate(argv: list[str], n: int, gw: int, adjust=None, request=None) -> None:
    """His `run/simulations.py` (n runs of `solve_regular` with `randomized` on), then his `run/sensitivity.py`
    summary for GW `gw`.

    The runs go one at a time in this process (his default of 1 process) so `adjust` applies to each. His
    results folder is left as is; only the plans these runs saved are copied out and summarised.
    """
    solve = solve_module()
    import sensitivity

    results = solve.DATA_DIR / "results"
    results.mkdir(exist_ok=True)
    before = set(results.glob("*.csv"))
    options, start = {}, time.perf_counter()
    print(f"\n--- Sertalp's simulations: {n} runs ---")
    for i in range(1, n + 1):
        options = run(argv, adjust, request, quiet=True, runtime_options={"run_no": str(i), "randomized": True}).options
        print(f"  {i}/{n} done ({time.perf_counter() - start:.0f}s)", flush=True)
    wildcard = options.get("preseason") or gw in (options.get("use_wc") or [])
    with tempfile.TemporaryDirectory() as tmp:
        for f in set(results.glob("*.csv")) - before:
            shutil.copy(f, tmp)
        sensitivity.input = lambda *_: "n"  # his "Show top N results (y/n)?" prompt: show all
        try:
            if wildcard:
                sensitivity.process_wildcard_transfers(gw, tmp)
            else:
                sensitivity.process_regular_transfers(gw, tmp)
        finally:
            del sensitivity.input


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
    p.add_argument("--sims", type=int, help="then run his simulations N times at the chosen λ and print his summary")
    return p


def solve(argv: list[str], request=None, load_eo=ownership.pick_eo, standing=None) -> int:
    p = parser()
    ours, theirs = p.parse_known_args(argv)
    request = request or live_request()
    if ours.eo is None and ours.target is None and ours.lam is None:
        r = run(theirs, request=request)
        if ours.sims:
            simulate(theirs, ours.sims, next_gw(r.options, request(BOOTSTRAP)), request=request)
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
    if ours.sims:
        adjust = None if chosen == 0 else lambda proj, _: ownership.adjust_projections(proj, eo, chosen, gw)
        simulate(theirs, ours.sims, gw, adjust, request)
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    sys.stdout.reconfigure(encoding="utf-8")  # player names and λ on the Windows console
    if not argv or argv[0] != "solve":
        print("usage: fplrank solve [his solve.py flags] [--eo GROUP] [--target RANK] [--lam λ] [--points N] [--sims N]")
        return 2
    return solve(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
