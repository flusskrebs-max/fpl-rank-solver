"""`fplrank solve`: Sertalp's solve.py, plus our two extras (the EO and the λ choice).

    uv run fplrank solve [his flags]                                  # exactly his solver
    uv run fplrank solve [his flags] --eo AE64 --target 10000          # λ with the best P(top 10,000)
    uv run fplrank solve [his flags] --eo AE64 --lam 0.1               # a fixed λ
    uv run fplrank solve [his flags] --eo AE64 --target 10000 --sims 50  # plus his simulations at that λ

His flags (horizon, use_wc, banned, team_id, ...) and his settings files are passed to his
`run/solve.py::solve_regular` unchanged. With `--eo`, his projections are read as usual and scaled by
xP x (1 + λ_k x (EO - 1)), λ_k = λ x d^k for the GW k weeks after the next (`--eo_decay` d, default 0.7; 0 = next GW
only), once per λ (`opt.ownership`). A collector group's EO is its
managers' latest squads re-picked on each GW's xP, drifting on later GWs towards three wildcard squads solved now with
his solver (`wildcard_templates`, `ownership.repick_eo`; `--eo_drift false` to keep squads as now). The plan with the best
P(reaching the target line) (`opt.rank_goal`) is printed with his normal output under a short λ block.

`--sims N` then does what his `run/simulations.py` does, at the chosen λ: N runs of `solve_regular` with
`randomized` on (his noise, applied to the λ-scaled projections), followed by his `run/sensitivity.py`
summary of the plans those runs saved.

The solves (each λ, the wildcard templates, the simulations) are independent MILPs and HiGHS solves each on about one
core, so they run side by side in `--workers` processes (default: half the logical CPUs, at most 8). Each solve is the same as it would be
on its own; `--workers 1` runs them one after another in this process, as before.
"""

import argparse
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

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


@dataclass
class LiveRequest:
    """His `cached_request`, served by our FPL API client (saves a dated snapshot of every payload). Picklable, so the
    worker processes get the payloads already fetched and only go to the API for anything new."""

    cache: dict = field(default_factory=dict)
    api: object = None

    def __call__(self, url):
        endpoint = url.split("/api/", 1)[1]
        if endpoint not in self.cache:
            if self.api is None:
                from fplrank.data.fpl_api import FplApi

                self.api = FplApi()
            self.cache[endpoint] = self.api.get(endpoint)
        return self.cache[endpoint]

    def __getstate__(self):
        return {"cache": self.cache, "api": None}


def live_request():
    return LiveRequest()


@dataclass
class Replay:
    """The payloads a request function served in this process, for a worker process: `fallback` (picklable, or None)
    for anything not seen yet."""

    seen: dict
    fallback: object = None

    def __call__(self, url):
        if url not in self.seen:
            if self.fallback is None:
                raise KeyError(f"{url} was not fetched before the workers started")
            self.seen[url] = self.fallback(url)
        return self.seen[url]


class Recorder:
    """Wraps a request function and keeps what it served, so `replay()` can hand it to worker processes."""

    def __init__(self, request):
        self.request, self.seen = request, {}

    def __call__(self, url):
        if url not in self.seen:
            self.seen[url] = self.request(url)
        return self.seen[url]

    def replay(self) -> Replay:
        return Replay(dict(self.seen), self.request if isinstance(self.request, LiveRequest) else None)


@dataclass
class Adjust:
    """λ on his projections (`ownership.adjust_projections`), as a picklable `adjust` for `run`."""

    eo: pd.DataFrame | pd.Series
    lam: float
    gw: int
    decay: float

    def __call__(self, proj, _options):
        return ownership.adjust_projections(proj, self.eo, self.lam, self.gw, self.decay)


class Deferred:
    """A job for `InlineExecutor`: it runs in this process when its result is first asked for."""

    def __init__(self, fn, args, kwargs):
        self.call, self.value, self.ran = (fn, args, kwargs), None, False

    def result(self):
        if not self.ran:
            fn, args, kwargs = self.call
            self.value, self.ran = fn(*args, **kwargs), True
        return self.value


class InlineExecutor:
    """`--workers 1`: the jobs run one at a time in this process, in the order they were submitted."""

    def submit(self, fn, *args, **kwargs) -> Deferred:
        return Deferred(fn, args, kwargs)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class Pool(ProcessPoolExecutor):
    """A process pool that drops the jobs not yet started if the block fails (a solve that fails, Ctrl+C)."""

    def __exit__(self, exc_type, *_):
        self.shutdown(wait=True, cancel_futures=exc_type is not None)
        return False


def executor(workers: int, jobs: int):
    """Process pool for `jobs` independent solves (spawned, as on Windows), or in this process for one worker."""
    workers = max(1, min(workers, jobs))
    if workers == 1:
        return InlineExecutor()
    import multiprocessing

    return Pool(workers, mp_context=multiprocessing.get_context("spawn"))


def finished(jobs):
    """The jobs as they finish (in submission order for `InlineExecutor`, which runs them here as it goes)."""
    if all(isinstance(j, Deferred) for j in jobs):
        for j in jobs:
            j.result()
            yield j
    else:
        yield from as_completed(jobs)


MAX_DEFAULT_WORKERS = 8  # each running solve holds roughly 300-500 MB


def default_workers() -> int:
    """Half the logical CPUs (about one per physical core, where HiGHS gains little from the second thread), at most
    `MAX_DEFAULT_WORKERS`."""
    return max(1, min((os.cpu_count() or 1) // 2, MAX_DEFAULT_WORKERS))


class _Prepared(Exception):  # noqa: N818 (not an error: a dry run stops here)
    pass


def run(argv: list[str], adjust=None, request=None, quiet: bool = False, runtime_options: dict | None = None, dry: bool = False) -> Run:
    """Run his `solve_regular` with `argv` as his command line.

    adjust(projections, options) -> projections changes his projections after he reads them.
    quiet: capture what he prints in `Run.output` instead of printing it.
    runtime_options: handed to `solve_regular` the way his simulations script does.
    dry: stop before the solve (his options and projections only; `Run.solution` is None).
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
        if dry:
            raise _Prepared
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
    except _Prepared:
        pass
    finally:
        sys.argv = argv_was
    return Run(solved[0][0] if solved else None, seen["options"], seen["projections"], out.getvalue())


def _job(argv, adjust, request, runtime_options) -> Run:
    """One quiet `run` in a worker process."""
    return run(argv, adjust, request, quiet=True, runtime_options=runtime_options)


def simulate(argv: list[str], n: int, gw: int, adjust=None, request=None, workers: int = 1) -> None:
    """His `run/simulations.py` (n runs of `solve_regular` with `randomized` on), then his `run/sensitivity.py`
    summary for GW `gw`.

    The runs go side by side in `workers` processes (his `run_parallel.py` idea) with `adjust` applied in each. His
    results folder is left as is; only the plans these runs saved are copied out and summarised.
    """
    solve = solve_module()
    import sensitivity

    results = solve.DATA_DIR / "results"
    results.mkdir(exist_ok=True)
    before = set(results.glob("*.csv"))
    options, start = {}, time.perf_counter()
    print(f"\n--- Sertalp's simulations: {n} runs ---")
    if not isinstance(request, Replay):
        request = Recorder(request)
        run(argv, request=request, quiet=True, dry=True)  # fetch what his runs need once, here
        request = request.replay()
    with executor(workers, n) as pool:
        jobs = [pool.submit(_job, argv, adjust, request, {"run_no": str(i), "randomized": True}) for i in range(1, n + 1)]
        for i, done in enumerate(finished(jobs), 1):
            options = done.result().options
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


TEMPLATE_HORIZONS = (3, 5, 8)  # as naive_field's templates (eo-blend.md (e))
TEMPLATE_SECS = 120  # time limit for each: a rough target, so near-optimal is plenty


def wildcard_templates(argv: list[str], gw: int, request=None, pool=None) -> pd.DataFrame:
    """Where the field drifts to: his solver run with a wildcard in GW `gw` on our team (budget and all) at horizons
    3, 5 and 8, other chips off, on his raw projections, at most `TEMPLATE_SECS` each (side by side in `pool` if
    given). Returns (template, fpl_id, element_type) for each GW `gw` squad.
    """
    pool = pool or InlineExecutor()
    chips = {"use_wc": [gw], "use_bb": [], "use_fh": [], "use_tc": []}
    jobs = [pool.submit(_job, argv, None, request, {**chips, "horizon": h, "secs": TEMPLATE_SECS}) for h in TEMPLATE_HORIZONS]
    out = []
    for i, job in enumerate(jobs):
        p = job.result().solution["picks"]
        p = p[(p["week"] == gw) & (p["squad"] == 1)]
        out.append(pd.DataFrame({"template": i, "fpl_id": p["id"].astype(int), "element_type": p["type"].astype(int)}))
    return pd.concat(out, ignore_index=True)


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
    p.add_argument(
        "--eo",
        help="EO group: AE64, E64, elite (AE64+E64 average), top1000, top10k, solio, or a mix such as AE64:0.4+E64:0.4+top10k:0.2 "
        "(default AE64 with --target)",
    )
    p.add_argument("--target", type=int, help="target overall rank: choose the λ with the best P(finishing at or above it)")
    p.add_argument("--lam", type=float, help="fix λ instead of choosing it (0 = his EV plan)")
    p.add_argument("--points", type=int, help="our total points now, for --target (default: from the FPL API)")
    p.add_argument("--kappa", type=float, help="share of our projected edge over the field that counts, for --target (default 0.75)")
    p.add_argument(
        "--eo_decay",
        type=float,
        default=ownership.EO_DECAY,
        help=f"λ's decay a GW after the next one, on top of his decay_base (default {ownership.EO_DECAY:g}; 0 = next GW only)",
    )
    p.add_argument(
        "--eo_drift",
        type=lambda v: v.lower() in ("true", "1", "yes", "on"),
        default=True,
        help="later GWs' EO drifts towards three wildcard solves (default true; false = squads as now)",
    )
    p.add_argument("--sims", type=int, help="then run his simulations N times at the chosen λ and print his summary")
    p.add_argument(
        "--workers",
        type=int,
        default=default_workers(),
        help=f"solves run side by side in this many processes (default: half the logical CPUs, {default_workers()} here; 1 = in turn)",
    )
    return p


def solve(argv: list[str], request=None, load_eo=ownership.pick_eo, standing=None) -> int:
    p = parser()
    ours, theirs = p.parse_known_args(argv)
    request = request or live_request()
    if ours.eo is None and ours.target is None and ours.lam is None:
        r = run(theirs, request=request)
        if ours.sims:
            simulate(theirs, ours.sims, next_gw(r.options, request(BOOTSTRAP)), request=request, workers=ours.workers)
        return 0
    if ours.target is None and ours.lam is None:
        p.error("--eo needs --target (to choose λ) or --lam (to fix it)")
    group = ours.eo or "AE64"
    if group != "solio":
        try:
            ownership.group_weights(group)
        except ValueError as e:
            p.error(str(e))
    lams = sorted({0.0} | ({ours.lam} if ours.lam is not None else set(ownership.SWEEP)), key=abs)

    request = Recorder(request)
    prepared = run(theirs, request=request, quiet=True, dry=True)  # his options and projections, before any solve
    gw = next_gw(prepared.options, request(BOOTSTRAP))
    replay = request.replay()  # what the workers need from the FPL API, fetched once here
    drift = ours.eo_drift and ours.eo_decay
    runs, start = {}, time.perf_counter()
    with executor(ours.workers, len(lams) + (len(TEMPLATE_HORIZONS) if drift else 0)) as pool:
        jobs = {pool.submit(_job, theirs, None, replay, None): 0.0}
        templates = (lambda: wildcard_templates(theirs, gw, replay, pool)) if drift else None
        eo, eo_text = load_eo(group, request(BOOTSTRAP), gw, prepared.projections, templates=templates)
        for lam in lams[1:]:
            jobs[pool.submit(_job, theirs, Adjust(eo, lam, gw, ours.eo_decay), replay, None)] = lam
        for i, job in enumerate(finished(jobs), 1):
            runs[jobs[job]] = job.result()
            print(f"  {i}/{len(lams)}: λ = {jobs[job]:g} solved in {time.perf_counter() - start:.0f}s", flush=True)
    runs = {lam: runs[lam] for lam in lams}

    base = runs[0.0]
    hit_cost = base.options.get("hit_cost", 4)
    solutions = {lam: {**r.solution, **ownership.score_plan(r.solution, base.projections, eo, hit_cost)} for lam, r in runs.items()}
    print()
    decay_base = 1.0 if base.options.get("objective") == "regular" else base.options.get("decay_base", 0.84)
    if ours.eo_decay:
        term = decay_base * ours.eo_decay
        print(
            f"EO {eo_text}; λ in full on GW{gw}, then x{ours.eo_decay:g} a GW (EO term x{term:.2f} a GW with his decay_base {decay_base:g})"
        )
    else:
        print(f"EO {eo_text}; λ on GW{gw} only")
    if ours.target:
        points = ours.points
        if points is None:
            team_id = base.options.get("team_id")
            if team_id is None:
                p.error("--target needs --points or his --team_id")
            points = (standing or ownership.current_standing)(int(team_id))[0]
        table, gap_text = ownership.rank_goal_table(
            solutions, base.projections, eo, gw, ours.target, points, ownership.drift_group(group), ours.kappa, hit_cost
        )
        if ours.lam is not None:  # fixed λ: report it, not the best one
            table = pd.concat([table[table["lam"] == ours.lam], table[table["lam"] != ours.lam]], ignore_index=True)
        chosen = float(table.iloc[0]["lam"])
        print(gap_text)
        print("P by λ: " + ", ".join(f"{r.lam:g} {r.p:.0%}" for r in table.sort_values("lam").itertuples()))
        from fplrank.opt import rank_goal

        print(rank_goal.report(table, ours.target, rank_goal.KAPPA if ours.kappa is None else ours.kappa))
    else:
        chosen = ours.lam
        cost = solutions[0.0]["ev"] - solutions[chosen]["ev"]
        print(f"λ = {chosen:g} (fixed), EV cost {cost:.1f} points")
    print(f"\n--- Sertalp's solver, plan for λ = {chosen:g} ---")
    print(runs[chosen].output)
    if ours.sims:
        adjust = None if chosen == 0 else Adjust(eo, chosen, gw, ours.eo_decay)
        simulate(theirs, ours.sims, gw, adjust, replay, ours.workers)
    return 0


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    sys.stdout.reconfigure(encoding="utf-8")  # player names and λ on the Windows console
    if argv and argv[0] == "page":  # the Streamlit page that fills in these flags (fplrank.ui)
        page = Path(__file__).parent / "ui" / "page.py"
        return subprocess.call([sys.executable, "-m", "streamlit", "run", str(page), *argv[1:]])
    if not argv or argv[0] != "solve":
        print(
            "usage: fplrank page | fplrank solve [his solve.py flags] [--eo GROUP] [--target RANK] [--lam λ] [--points N] [--kappa κ]",
            end="",
        )
        print(" [--eo_decay d] [--sims N]")
        return 2
    return solve(argv[1:])


if __name__ == "__main__":
    sys.exit(main())
