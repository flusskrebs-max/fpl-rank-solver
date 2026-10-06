"""Naive field (idea 3 in docs/research/eo-projector.md): forecast a group's next-GW ownership and EO by
running Sertalp's solver at λ = 0 (pure EV) on every member's real squad.

For each AE64 / E64 member at GW t we rebuild their team state (squad, purchase and selling prices,
bank, free transfers) with his own `generate_team_json` (vendor/open-fpl-solver/dev/solver.py), served
from our collected picks, transfers and chips instead of the live API. Then his `solve_regular` runs
with the latest Solio file (settings unchanged apart from a short time limit) under a few transfer
settings:

- `1ft`, `2ft`: free transfers forced to 1 or 2 for everyone
- `banked`: each manager's real free transfers (his own FT count)
- `wc`: a wildcard in GW t+1 for everyone

The group's predicted ownership is the share of members whose solved squad holds the player in GW t+1;
predicted EO is the mean solved multiplier (XI 1, captain 2). Scored against persistence (GW t carried
forward) with the pass criteria fixed in eo-projector.md.

    uv run python -m fplrank.model.naive_field backtest --secs 20 --workers 6
    uv run python -m fplrank.model.naive_field forecast --gw 6    # next GW, to score after its deadline
"""

import argparse
import copy
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from fplrank.paths import COLLECTED_DIR, DATA_DIR, UPSTREAM_DIR
from fplrank.upstream import patched, solve_module

GROUPS = ("AE64", "E64")
VARIANTS = ("1ft", "2ft", "banked", "wc")
SURGE = 0.20  # a "big move": 20+ points of ownership in one GW
TOP_K = 10  # surge recall: a big move counts as caught if it is in the top-10 predicted risers or fallers
OUT_DIR = DATA_DIR / "derived" / "naive_field"


def _his_solver():
    """His `dev.solver` (vendored, unedited), importable once `upstream.solve_module()` has set the path."""
    solve_module()
    import dev.solver as solver

    return solver


# ---------------------------------------------------------------------------- inputs at a past deadline


def market_prices(transfers: pd.DataFrame, bootstrap: dict, gw: int) -> dict[int, int]:
    """Price of every player (tenths) at the GW `gw` deadline, from what collected managers paid.

    The FPL API only gives today's price, so for a past deadline we use the median `element_in_cost`
    of transfers made for `gw` (bought in the week before its deadline), else the latest earlier
    purchase, else the start price. Players nobody bought rarely move, so the fallback is small.
    """
    prices = {e["id"]: e["now_cost"] - e["cost_change_start"] for e in bootstrap["elements"]}
    seen = transfers[transfers["gw"] <= gw]
    if seen.empty:
        return prices
    by_gw = seen.groupby(["element_in", "gw"])["element_in_cost"].median().reset_index()
    last = by_gw.sort_values("gw").drop_duplicates("element_in", keep="last")
    prices.update({int(r.element_in): round(r.element_in_cost) for r in last.itertuples()})
    return prices


def bootstrap_at(bootstrap: dict, next_gw: int, prices: dict[int, int]) -> dict:
    """A copy of /bootstrap-static/ as it would have looked before the `next_gw` deadline (prices and event flags)."""
    b = copy.deepcopy(bootstrap)
    for e in b["elements"]:
        start = e["now_cost"] - e["cost_change_start"]
        e["now_cost"] = int(prices.get(e["id"], e["now_cost"]))
        e["cost_change_start"] = e["now_cost"] - start
    for ev in b["events"]:
        ev["is_next"] = ev["id"] == next_gw
        ev["is_current"] = ev["id"] == next_gw - 1
        ev["finished"] = ev["id"] < next_gw
    return b


def team_state(entry_id: int, next_gw: int, picks: pd.DataFrame, transfers: pd.DataFrame, chips: pd.DataFrame, bootstrap_gw: dict) -> dict:
    """my_data for `entry_id` before the `next_gw` deadline, built by his `generate_team_json`.

    His function reads the entry's first-GW picks, transfer list and chip history from the API; here they
    come from the collected tables, cut at the deadline. Selling prices use `bootstrap_gw`'s prices.
    """
    solver = _his_solver()
    own = picks[picks["entry_id"] == entry_id]
    first_gw = int(own["gw"].min())
    t = transfers[(transfers["entry_id"] == entry_id) & (transfers["gw"] < next_gw)].sort_values("time", ascending=False)
    c = chips[(chips["entry_id"] == entry_id) & (chips["gw"] < next_gw)]
    payloads = {
        "bootstrap-static/": bootstrap_gw,
        f"entry/{entry_id}/transfers/": [
            {
                "element_in": int(r.element_in),
                "element_in_cost": int(r.element_in_cost),
                "element_out": int(r.element_out),
                "element_out_cost": int(r.element_out_cost),
                "event": int(r.gw),
            }
            for r in t.itertuples()
        ],
        f"entry/{entry_id}/history/": {
            "current": [{"event": first_gw}],
            "chips": [{"name": r.chip, "event": int(r.gw)} for r in c.itertuples()],
        },
        f"entry/{entry_id}/event/{first_gw}/picks/": {"picks": [{"element": int(e)} for e in own[own["gw"] == first_gw]["fpl_id"]]},
    }

    def request(url):
        return copy.deepcopy(payloads[url.split("/api/", 1)[1]])

    with patched(solver, cached_request=request):
        my_data = solver.generate_team_json(entry_id, {})
    my_data["chips"] = []  # chip availability is set per variant through his options, not his chip history
    return my_data


def variant_inputs(my_data: dict, variant: str, next_gw: int) -> tuple[dict, dict]:
    """(my_data, extra options) for one transfer setting."""
    data = copy.deepcopy(my_data)
    options = {}
    if variant == "1ft":
        data["transfers"]["limit"] = 1
    elif variant == "2ft":
        data["transfers"]["limit"] = 2
    elif variant == "wc":
        options["use_wc"] = [next_gw]
    elif variant != "banked":
        raise ValueError(f"unknown variant {variant!r}")
    return data, options


# ---------------------------------------------------------------------------- solving


_WORKER = {}


def _init_worker(projections_path: str, bootstrap_by_gw: dict, fixtures: list, secs: int, horizon: int | None):
    sys.stdout = open(os.devnull, "w")  # his solver prints a lot; workers stay quiet
    source = f"fplrank_nf{os.getpid()}"  # his projection file (his data/{source}.csv), one per process
    pd.read_csv(projections_path, encoding="utf-8-sig").to_csv(UPSTREAM_DIR / "data" / f"{source}.csv", index=False, encoding="utf-8")
    _WORKER.update(
        source=source,
        bootstraps=bootstrap_by_gw,
        fixtures=fixtures,
        secs=secs,
        horizon=horizon,
        results=tempfile.mkdtemp(prefix="naive_field_"),
    )


def _solve_one(key: tuple, my_data: dict, next_gw: int, variant: str) -> tuple[tuple, list[tuple[int, int]] | str]:
    """Solve one manager-variant through his `solve_regular`, called the way his run/simulations.py calls it.

    Returns (key, [(fpl_id, multiplier) for the solved GW next_gw squad]) or (key, error message).
    API payloads come from our snapshots; his per-solve result CSVs go to a temp folder.
    """
    solve, solver = solve_module(), _his_solver()
    from dev import data_parser

    data, extra = variant_inputs(my_data, variant, next_gw)
    options = {
        "datasource": _WORKER["source"],
        "team_data": "json_string",
        "team_json": json.dumps(data),
        "override_next_gw": next_gw,
        "secs": _WORKER["secs"],
        "verbose": False,
        "print_squads": False,
        "print_result_table": False,
        "print_transfer_chip_summary": False,
        "export_image": False,
        **({"horizon": _WORKER["horizon"]} if _WORKER["horizon"] else {}),
        **extra,
    }
    responses = {"bootstrap-static/": _WORKER["bootstraps"][next_gw], "fixtures/": _WORKER["fixtures"]}

    def request(url):
        return copy.deepcopy(responses[url.split("/api/", 1)[1]])

    solved, original = [], solve.solve_multi_period_fpl

    def keep(d, o):
        response = original(d, o)
        solved.append(response)
        return response

    argv, sys.argv = sys.argv, sys.argv[:1]  # his parser reads sys.argv
    try:
        with (
            patched(solve, cached_request=request, solve_multi_period_fpl=keep, DATA_DIR=Path(_WORKER["results"])),
            patched(solver, cached_request=request),
            patched(data_parser, cached_request=request),
        ):
            solve.solve_regular(options)
    except Exception as exc:  # one bad squad shouldn't stop the run
        return key, f"{type(exc).__name__}: {exc}"
    finally:
        sys.argv = argv
    p = solved[0][0]["picks"]
    p = p[(p["week"] == next_gw) & (p["squad"] == 1)]
    return key, [(int(r.id), int(r.multiplier)) for r in p.itertuples()]


def run_solves(jobs: list[dict], projections_path, bootstrap_by_gw, fixtures, secs=20, horizon=None, workers=4, log=print) -> pd.DataFrame:
    """Solve every job ({entry_id, gw, variant, my_data}); identical states are solved once.

    Returns long rows: entry_id, gw (the GW solved for), variant, fpl_id, multiplier (0 = bench).
    """
    unique, owners = {}, {}
    for j in jobs:
        d, extra = variant_inputs(j["my_data"], j["variant"], j["gw"])
        squad = tuple(sorted((p["element"], p["selling_price"]) for p in d["picks"]))
        state = (j["gw"], bool(extra), d["transfers"]["bank"], d["transfers"]["limit"], squad)  # 1ft = banked when banked is 1
        unique.setdefault(state, j)
        owners.setdefault(state, []).append(j)
    log(f"{len(jobs)} solves, {len(unique)} unique states, {workers} workers, {secs}s limit")
    rows, errors, t0 = [], [], time.time()
    with ProcessPoolExecutor(
        workers, initializer=_init_worker, initargs=(str(projections_path), bootstrap_by_gw, fixtures, secs, horizon)
    ) as pool:
        futures = [pool.submit(_solve_one, state, j["my_data"], j["gw"], j["variant"]) for state, j in unique.items()]
        for i, f in enumerate(as_completed(futures), 1):
            state, result = f.result()
            if isinstance(result, str):
                errors.append((state[:2], result))
            else:
                for j in owners[state]:
                    rows += [(j["entry_id"], j["gw"], j["variant"], pid, mult) for pid, mult in result]
            if i % 25 == 0 or i == len(futures):
                log(f"  {i}/{len(futures)} solved ({time.time() - t0:.0f}s)")
    for f in (UPSTREAM_DIR / "data").glob("fplrank_nf*.csv"):
        f.unlink()
    for e in errors[:10]:
        log(f"  failed {e}")
    if errors:
        log(f"  {len(errors)} solves failed")
    return pd.DataFrame(rows, columns=["entry_id", "gw", "variant", "fpl_id", "multiplier"])


# ---------------------------------------------------------------------------- group forecasts and scoring


def group_table(rows: pd.DataFrame, members: pd.Series) -> pd.DataFrame:
    """Ownership (share holding) and EO (mean multiplier) over `members`, per GW and player.

    `rows`: entry_id, gw, fpl_id, multiplier (one row per squad player; multiplier 0 = bench).
    Members with no rows for a GW (e.g. a failed solve) are left out of that GW's denominator.
    """
    r = rows[rows["entry_id"].isin(members)]
    n = r.groupby("gw")["entry_id"].nunique()
    out = r.groupby(["gw", "fpl_id"]).agg(own=("entry_id", "nunique"), eo=("multiplier", "sum")).reset_index()
    out["own"] /= out["gw"].map(n)
    out["eo"] /= out["gw"].map(n)
    return out


def score(prev: pd.DataFrame, actual: pd.DataFrame, pred: pd.DataFrame) -> dict:
    """Errors of a forecast and of persistence for one group and transition, in points (x100).

    Each frame: fpl_id, own, eo. `prev` = GW t (persistence), `actual` = GW t+1, `pred` = forecast for t+1.
    Errors are averaged over every player owned at t or t+1 or in the forecast.
    """
    ids = pd.Index(sorted(set(prev["fpl_id"]) | set(actual["fpl_id"]) | set(pred["fpl_id"])), name="fpl_id")
    a, b, f = (x.set_index("fpl_id")[["own", "eo"]].reindex(ids).fillna(0.0) * 100 for x in (prev, actual, pred))
    move = b["own"] - a["own"]
    surges = move[move.abs() >= SURGE * 100]
    dpred = f["own"] - a["own"]
    risers = set(dpred.nlargest(TOP_K).index[dpred.nlargest(TOP_K) > 0])
    fallers = set(dpred.nsmallest(TOP_K).index[dpred.nsmallest(TOP_K) < 0])
    caught = sum((pid in risers) if m > 0 else (pid in fallers) for pid, m in surges.items())
    return {
        "n_players": len(ids),
        "own_mae": (f["own"] - b["own"]).abs().mean(),
        "own_mae_persist": move.abs().mean(),
        "eo_mae": (f["eo"] - b["eo"]).abs().mean(),
        "eo_mae_persist": (b["eo"] - a["eo"]).abs().mean(),
        "surges": len(surges),
        "caught": caught,
    }


def eo_gap(prev: pd.DataFrame, a: pd.DataFrame, b: pd.DataFrame) -> float:
    """Mean absolute EO difference (points) between two forecasts, over players owned at t or in either."""
    ids = pd.Index(sorted(set(prev["fpl_id"]) | set(a["fpl_id"]) | set(b["fpl_id"])), name="fpl_id")
    x, y = (f.set_index("fpl_id")["eo"].reindex(ids).fillna(0.0) * 100 for f in (a, b))
    return (x - y).abs().mean()


def passes(table: pd.DataFrame) -> pd.DataFrame:
    """The pre-set checks (eo-projector.md) per group and variant, over the scored transitions."""
    out = []
    for (group, variant), t in table.groupby(["group", "variant"]):
        quiet = t[t["quiet"]]
        eo, eo_p = t["eo_mae"].mean(), t["eo_mae_persist"].mean()
        out.append(
            {
                "group": group,
                "variant": variant,
                "eo_mae": eo,
                "eo_mae_persist": eo_p,
                "eo_gain": 1 - eo / eo_p,
                "quiet_eo_mae": quiet["eo_mae"].mean() if len(quiet) else float("nan"),
                "quiet_eo_mae_persist": quiet["eo_mae_persist"].mean() if len(quiet) else float("nan"),
                "recall": t["caught"].sum() / t["surges"].sum() if t["surges"].sum() else float("nan"),
                "pass_eo": 1 - eo / eo_p >= 0.15,
                "pass_quiet": (quiet["eo_mae"].mean() <= quiet["eo_mae_persist"].mean()) if len(quiet) else None,
                "pass_recall": t["caught"].sum() >= 0.5 * t["surges"].sum(),
            }
        )
    return pd.DataFrame(out)


# ---------------------------------------------------------------------------- data plumbing (needs data/)


def _load(collected_dir=COLLECTED_DIR):
    read = lambda name: pd.read_parquet(Path(collected_dir) / f"{name}.parquet")  # noqa: E731
    members = read("members")
    members = members[members["set"].isin(GROUPS)][["set", "entry_id"]].rename(columns={"set": "group"})
    ids = members["entry_id"].unique()
    picks, transfers, chips = (read(n) for n in ("picks", "transfers", "chips"))
    picks = picks[picks["entry_id"].isin(ids)]
    chips = chips[chips["entry_id"].isin(ids)]
    eo = read("eo")
    eo = eo[eo["group"].isin(GROUPS)]
    return members, picks, transfers, chips, eo


def actual_table(picks: pd.DataFrame, eo: pd.DataFrame, members: pd.DataFrame, group: str) -> pd.DataFrame:
    """Real ownership (from picks) and deadline EO (collector) per GW for a group."""
    ids = members.loc[members["group"] == group, "entry_id"]
    p = picks[picks["entry_id"].isin(ids)]
    n = p.groupby("gw")["entry_id"].nunique()
    own = p.groupby(["gw", "fpl_id"])["entry_id"].nunique().rename("own").reset_index()
    own["own"] /= own["gw"].map(n)
    e = eo[eo["group"] == group][["gw", "fpl_id", "eo"]]
    return own.merge(e, on=["gw", "fpl_id"], how="outer").fillna(0.0)


def quiet_weeks(picks: pd.DataFrame, chips: pd.DataFrame, members: pd.DataFrame, actual: dict) -> dict:
    """{(group, gw): quiet?} as defined before the eo-flow-v1 run: wildcard + free hit under 10% of
    the group in GW gw, and no 20-point ownership move from gw-1."""
    out = {}
    for group in GROUPS:
        ids = members.loc[members["group"] == group, "entry_id"]
        c = chips[chips["entry_id"].isin(ids) & chips["chip"].isin(["wildcard", "freehit"])]
        a = actual[group].pivot_table(index="fpl_id", columns="gw", values="own", fill_value=0.0)
        for gw in a.columns[1:]:
            chip_share = (c["gw"] == gw).sum() / len(ids)
            big = (a[gw] - a[gw - 1]).abs().max() >= SURGE
            out[(group, int(gw))] = bool(chip_share < 0.10 and not big)
    return out


def _projection_for(gw: int, override=None) -> Path:
    from fplrank.data.projections import latest

    return Path(override) if override else latest(gw)


def _bootstrap_and_fixtures():
    from fplrank.data.fpl_api import latest_snapshot

    return latest_snapshot("bootstrap-static/"), latest_snapshot("fixtures/")


def build_jobs(next_gws, variants, members, picks, transfers, chips, bootstrap, sample=None, seed=0):
    ids = pd.Series(members["entry_id"].unique())
    if sample:
        ids = ids.sample(min(sample, len(ids)), random_state=seed)
    jobs, boots = [], {}
    for gw in next_gws:
        boots[gw] = bootstrap_at(bootstrap, gw, market_prices(transfers, bootstrap, gw))
        for entry_id in ids:
            if picks[(picks["entry_id"] == entry_id) & (picks["gw"] < gw)].empty:
                continue
            my_data = team_state(int(entry_id), gw, picks, transfers, chips, boots[gw])
            jobs += [{"entry_id": int(entry_id), "gw": gw, "variant": v, "my_data": my_data} for v in variants]
    return jobs, boots


def backtest(secs=20, workers=4, sample=None, variants=VARIANTS, horizon=None, log=print) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Forecast every collected transition t -> t+1 and score it. Returns (per-transition table, pass table)."""
    members, picks, transfers, chips, eo = _load()
    bootstrap, fixtures = _bootstrap_and_fixtures()
    actual = {g: actual_table(picks, eo, members, g) for g in GROUPS}
    quiet = quiet_weeks(picks, chips, members, actual)
    rows = []
    next_gws = sorted(int(g) for g in picks["gw"].unique() if g > picks["gw"].min())
    # one projection file per run of solves: the newest made at or before each deadline
    by_file = {}
    for gw in next_gws:
        by_file.setdefault(_projection_for(gw), []).append(gw)
    solved = []
    for path, gws in by_file.items():
        log(f"{path.name}: GW {gws}")
        jobs, boots = build_jobs(gws, variants, members, picks, transfers, chips, bootstrap, sample)
        r = run_solves(jobs, path, boots, fixtures, secs, horizon, workers, log)
        r["projection"] = path.name
        solved.append(r)
    solved = pd.concat(solved)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    solved.to_parquet(OUT_DIR / "backtest_solves.parquet")
    for group in GROUPS:
        ids = members.loc[members["group"] == group, "entry_id"]
        for variant in variants:
            pred = group_table(solved[solved["variant"] == variant], ids)
            for gw in next_gws:
                act = actual[group]
                s = score(act[act["gw"] == gw - 1], act[act["gw"] == gw], pred[pred["gw"] == gw])
                proj = solved.loc[solved["gw"] == gw, "projection"].iloc[0]
                rows.append({"group": group, "variant": variant, "gw": gw, "projection": proj, "quiet": quiet[(group, gw)], **s})
    table = pd.DataFrame(rows)
    table.to_csv(OUT_DIR / "backtest_table.csv", index=False)
    return table, passes(table)


# ---------------------------------------------------------------------------- the cheap alternative (Alex, 2026-10-06)
#
# "Current EO x some function of future EV x default wildcards": a few solves per GW, not one per manager.
#   drift:     own[t+1] = own[t] x exp(k x (EV_i - EV_ref)), rescaled per position so each manager still owns
#              2/5/5/3; EV_i = projected points over the next 5 GWs, EV_ref = the ownership-weighted mean of
#              the position. EO scales with ownership.
#   templates: wildcard squads from an empty team with the group's average budget (his solver), at horizons
#              3, 5 and 8, averaged (own = share of templates holding the player, EO = mean multiplier).
#   blend:     (1 - w) x drift + w x templates.
# Variants: `cheap` fits k and w leave-one-GW-out on EO error against actual EO (no chip information);
# `cheap_wcshare` fits k and sets w to the share of the group that wildcarded in t+1 (an input, as chips are in
# v0); `cheap_approx` fits k and w to match the per-manager `mix` forecast instead (Alex: the cheap blend
# only has to approximate the intensive run). `mix` = per-manager wildcard solve for real wildcarders, banked-FT
# solve for the rest. `eo_gap_mix` / `eo_gap_banked` = how far a forecast's EO is from the per-manager ones.

KS = (0.0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.6)
WS = (0.0, 0.05, 0.1, 0.2, 0.3, 0.5)
TEMPLATE_HORIZONS = (3, 5, 8)


def future_ev(projections: pd.DataFrame, next_gw: int, horizon: int) -> pd.Series:
    """fpl_id -> projected points over GWs next_gw .. next_gw + horizon - 1 (his CSV format)."""
    cols = [f"{g}_Pts" for g in range(next_gw, next_gw + horizon) if f"{g}_Pts" in projections]
    return projections.set_index("ID")[cols].fillna(0).sum(axis=1)


def cheap_forecast(prev: pd.DataFrame, ev: pd.Series, pos: pd.Series, k: float, wc: pd.DataFrame | None = None, w: float = 0.0):
    """Forecast (fpl_id, own, eo) for t+1 from GW t's (fpl_id, own, eo); see the block comment above.

    `wc`: the wildcard squad as (fpl_id, own=1, eo=multiplier); `w`: share wildcarding.
    """
    p = prev[prev["own"] > 0].set_index("fpl_id")[["own", "eo"]].copy()
    p["ev"] = ev.reindex(p.index).fillna(0.0)
    p["pos"] = pos.reindex(p.index)
    ref = p.groupby("pos").apply(lambda g: (g["own"] * g["ev"]).sum() / g["own"].sum())
    raw = p["own"] * np.exp(k * (p["ev"] - p["pos"].map(ref)))
    scale = p.groupby("pos")["own"].sum() / raw.groupby(p["pos"]).sum()
    own = (raw * p["pos"].map(scale)).clip(upper=1.0)
    out = pd.DataFrame({"own": own, "eo": p["eo"] * own / p["own"]})
    if wc is not None and w > 0:
        wc = wc.set_index("fpl_id")[["own", "eo"]]
        ids = out.index.union(wc.index)
        out = (1 - w) * out.reindex(ids).fillna(0.0) + w * wc.reindex(ids).fillna(0.0)
    return out.rename_axis("fpl_id").reset_index()


def compare(secs=15, horizon=5, log=print) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score the cheap model and the per-manager "mix" against persistence, on the backtest's weeks.

    Reads the per-manager solves saved by `backtest`; runs one wildcard solve per group and GW.
    """
    members, picks, transfers, chips, eo = _load()
    bootstrap, fixtures = _bootstrap_and_fixtures()
    solved = pd.read_parquet(OUT_DIR / "backtest_solves.parquet")
    actual = {g: actual_table(picks, eo, members, g) for g in GROUPS}
    quiet = quiet_weeks(picks, chips, members, actual)
    pos = pd.Series({e["id"]: e["element_type"] for e in bootstrap["elements"]})
    next_gws = sorted(solved["gw"].unique())
    wildcards = chips[chips["chip"] == "wildcard"]

    # a few template wildcard solves per group and GW (timed)
    t0, templates = time.time(), {}
    for gw in next_gws:
        path = _projection_for(gw)
        boots = {gw: bootstrap_at(bootstrap, gw, market_prices(transfers, bootstrap, gw))}
        _init_worker(str(path), boots, fixtures, secs, horizon)
        sys.stdout = sys.__stdout__
        for group in GROUPS:
            ids = members.loc[members["group"] == group, "entry_id"]
            states = [team_state(int(e), gw, picks, transfers, chips, boots[gw]) for e in ids]
            budget = round(sum(d["transfers"]["bank"] + sum(p["selling_price"] for p in d["picks"]) for d in states) / len(states))
            empty = {"picks": [], "chips": [], "transfers": {"limit": None, "bank": budget, "made": 0}}
            squads = []
            for h in TEMPLATE_HORIZONS:
                _WORKER.update(horizon=h, secs=max(secs, 30))
                _, squad = _solve_one((group, gw, h), empty, gw, "banked")
                squads.append(pd.DataFrame(squad, columns=["fpl_id", "eo"]).assign(own=1.0))
            n = len(squads)
            templates[(group, gw)] = pd.concat(squads).groupby("fpl_id")[["own", "eo"]].sum().div(n).reset_index()
    for f in (UPSTREAM_DIR / "data").glob("fplrank_nf*.csv"):
        f.unlink()
    wc_secs = time.time() - t0
    log(f"{len(templates) * len(TEMPLATE_HORIZONS)} template wildcard solves in {wc_secs:.0f}s")

    rows = []
    for group in GROUPS:
        ids = members.loc[members["group"] == group, "entry_id"]
        act = actual[group]
        wc_ids = {gw: set(wildcards.loc[(wildcards["gw"] == gw) & wildcards["entry_id"].isin(ids), "entry_id"]) for gw in next_gws}
        # per-manager mix: the wildcard solve for those who wildcarded, the banked-FT solve for the rest
        s = solved[solved["entry_id"].isin(ids)]
        is_wc = pd.Series([e in wc_ids[g] for e, g in zip(s["entry_id"], s["gw"], strict=True)], index=s.index)
        mix_pred = group_table(s[((s["variant"] == "wc") & is_wc) | ((s["variant"] == "banked") & ~is_wc)], ids)
        banked_pred = group_table(s[s["variant"] == "banked"], ids)
        for gw in next_gws:
            prev, now = act[act["gw"] == gw - 1], act[act["gw"] == gw]
            ev = future_ev(pd.read_csv(_projection_for(gw), encoding="utf-8-sig"), gw, 5)
            share = len(wc_ids[gw]) / len(ids)
            base = {"group": group, "gw": gw, "quiet": quiet[(group, gw)], "wc_share": share}
            mix_gw, banked_gw = mix_pred[mix_pred["gw"] == gw], banked_pred[banked_pred["gw"] == gw]

            def scored(f, prev=prev, now=now, mix_gw=mix_gw, banked_gw=banked_gw):
                return {**score(prev, now, f), "eo_gap_mix": eo_gap(prev, f, mix_gw), "eo_gap_banked": eo_gap(prev, f, banked_gw)}

            rows.append({**base, "variant": "mix", **scored(mix_gw)})
            rows.append({**base, "variant": "persistence", **scored(prev)})
            for k in KS:
                f = cheap_forecast(prev, ev, pos, k, templates[(group, gw)], share)
                rows.append({**base, "variant": "cheap_wcshare", "k": k, "w": share, **scored(f)})
                for w in WS:
                    f = scored(cheap_forecast(prev, ev, pos, k, templates[(group, gw)], w))
                    rows.append({**base, "variant": "cheap", "k": k, "w": w, **f})
                    rows.append({**base, "variant": "cheap_approx", "k": k, "w": w, **f})
    table = pd.DataFrame(rows)
    # leave-one-GW-out choice of (k, w) for the cheap models
    picked, fixed = [], table[table["variant"].isin(["mix", "persistence"])]
    for (_, variant), t in table[~table.index.isin(fixed.index)].groupby(["group", "variant"]):
        target = "eo_gap_mix" if variant == "cheap_approx" else "eo_mae"
        for gw in next_gws:
            k, w = t[t["gw"] != gw].groupby(["k", "w"])[target].mean().idxmin()
            picked.append(t[(t["gw"] == gw) & (t["k"] == k) & ((t["w"] == w) | (variant == "cheap_wcshare"))])
    table = pd.concat([fixed, *picked])
    table.to_csv(OUT_DIR / "compare_table.csv", index=False)
    return table, passes(table)


def forecast(next_gw: int, secs=20, workers=4, variants=VARIANTS, horizon=None, projection=None, log=print) -> pd.DataFrame:
    """Naive-field ownership and EO for `next_gw` per group and variant, saved to data/derived/naive_field/."""
    members, picks, transfers, chips, _ = _load()
    bootstrap, fixtures = _bootstrap_and_fixtures()
    path = _projection_for(next_gw, projection)
    jobs, boots = build_jobs([next_gw], variants, members, picks, transfers, chips, bootstrap)
    solved = run_solves(jobs, path, boots, fixtures, secs, horizon, workers, log)
    frames = []
    for group in GROUPS:
        ids = members.loc[members["group"] == group, "entry_id"]
        for variant in variants:
            t = group_table(solved[solved["variant"] == variant], ids)
            frames.append(t.assign(group=group, variant=variant))
    out = pd.concat(frames)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_DIR / f"forecast_GW{next_gw}.csv", index=False)
    return out


def _main(argv=None):
    p = argparse.ArgumentParser(prog="python -m fplrank.model.naive_field", description=__doc__.split("\n\n")[0])
    p.add_argument("mode", choices=["backtest", "forecast", "compare"])
    p.add_argument("--gw", type=int, help="forecast: the GW to forecast")
    p.add_argument("--secs", type=int, default=15, help="time limit per solve (his `secs`)")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--sample", type=int, help="backtest: solve only this many managers (random)")
    p.add_argument("--horizon", type=int, default=5, help="his horizon (0 = his settings, 8)")
    p.add_argument("--variants", nargs="+", default=list(VARIANTS), choices=VARIANTS)
    p.add_argument("--projection", help="forecast: Solio file (default: newest registered for --gw)")
    args = p.parse_args(argv)
    pd.set_option("display.width", 200)
    if args.mode == "backtest":
        table, check = backtest(args.secs, args.workers, args.sample, tuple(args.variants), args.horizon)
        print(table.round(2).to_string(index=False))
        print(check.round(3).to_string(index=False))
    elif args.mode == "compare":
        table, check = compare(args.secs, args.horizon)
        print(table.round(2).to_string(index=False))
        print(check.round(3).to_string(index=False))
    else:
        out = forecast(args.gw, args.secs, args.workers, tuple(args.variants), args.horizon, args.projection)
        print(out.sort_values("own", ascending=False).head(40).to_string(index=False))


if __name__ == "__main__":
    _main()
