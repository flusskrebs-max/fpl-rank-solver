"""Combined EO forecast (docs/research/eo-blend.md): a weighted average of five cheap-to-rough inputs, with
non-negative weights summing to 1, fitted per group (AE64, E64) leave-one-GW-out over the naive-field weeks.

Inputs, for a group's GW t+1 EO, all known before the t+1 deadline:

- (a) `fair`: fair persistence. GW t squads and lineups with chips stripped: triple captain counted as an
  ordinary captain, bench-boost bench at 0, free-hit squads replaced by the manager's GW t-1 squad (the squad
  the free hit reverts to).
- (b) `repick`: (a)'s squads, no transfers, with XI and captain re-picked from Solio xP for GW t+1 (best valid
  formation, captain = highest-xP starter).
- (c) `drift`: (a) moved by projected EV over the next 5 GWs (`naive_field.cheap_forecast`, k fitted).
- (d) `banked`: the per-manager ("mass") solve with each manager's real free transfers (naive_field backtest).
- (e) `templates`: three wildcard squads solved from an empty team (naive_field compare), entering with weight
  equal to the expected wildcard share, since wildcarders are the only managers it describes.

Alex (2026-10-06): chip EO is real, but the blend isn't fitted on it. Weights for (a)-(d) are fitted on the
managers with no chip in GW t or t+1 only; the full-group forecast is
`(1 - s) x sum_i w_i x_i + s x templates`, with s the expected wildcard share (the mean share in the other
weeks). Chip weeks are reported separately.

    uv run python -m fplrank.model.eo_blend backtest    # needs naive_field backtest + compare outputs
    uv run python -m fplrank.model.eo_blend gaps        # MIP gaps of 50 re-solved banked states
"""

import argparse
import itertools
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd

from fplrank.model import naive_field as nf
from fplrank.paths import DATA_DIR, UPSTREAM_DIR

INPUTS = ("fair", "repick", "drift", "banked")  # (a)-(d); (e) templates enter by expected wildcard share
STEP = 0.05  # weight grid
OUT_DIR = DATA_DIR / "derived" / "eo_blend"
# Captain herding (`herd_captains`), set from 2025-26's pattern before scoring 2026-27 (eo-blend.md). HERD_CONC:
# median top-captain share per group (eo-patterns-2025-26.md §5); groups not listed (top 1k/10k herd much less) are
# not herded. HERD_TAU: a 0.5-point xP lead gives the top captain 84% of the herd, a 1-point lead 97%.
HERD_CONC = {"AE64": 0.97, "E64": 0.91}
HERD_TAU = 0.3
HERD_MIN_XI = 0.25  # captain candidates: in at least a quarter of the group's XIs


# ---------------------------------------------------------------------------- inputs (a) and (b)


def fair_rows(picks: pd.DataFrame, gw: int) -> pd.DataFrame:
    """Per-manager GW `gw` squads with chips stripped (input (a)): (entry_id, fpl_id, element_type, multiplier).

    XI (positions 1-11) count 1, bench 0 (bench boost or not), captain 2 (triple captain or not). A manager who
    free-hit in `gw` gets their latest earlier non-free-hit squad and lineup instead, which is what they hold at
    the next deadline. The same rule as `opt.ownership.chip_free_eo`, kept per manager here.
    """
    p = picks[picks["gw"] <= gw]
    own = p[p["active_chip"].ne("freehit")]
    fh = set(p.loc[(p["gw"] == gw) & p["active_chip"].eq("freehit"), "entry_id"])
    back = own[own["entry_id"].isin(fh) & (own["gw"] < gw)]
    back = back[back["gw"] == back.groupby("entry_id")["gw"].transform("max")]
    p = pd.concat([own[own["gw"] == gw], back])
    mult = (p["position"] <= 11).astype(int) + p["is_captain"].astype(int)
    return p.assign(multiplier=mult)[["entry_id", "fpl_id", "element_type", "multiplier"]].reset_index(drop=True)


def lineup(pos: np.ndarray, xp: np.ndarray) -> np.ndarray:
    """Multipliers (XI 1, captain 2, bench 0) for the best valid XI of a 2/5/5/3 squad on `xp`.

    Valid: 1 GK, at least 3 DEF, 2 MID, 1 FWD. Taking the best GK, the best 3/2/1 and then the best 4 other
    outfielders is optimal, because the formation rules are all minimums. Captain = highest-xP starter.
    """
    order = np.argsort(-xp, kind="stable")
    xi = np.zeros(len(pos), bool)
    for p, need in ((1, 1), (2, 3), (3, 2), (4, 1)):
        xi[[i for i in order if pos[i] == p][:need]] = True
    xi[[i for i in order if pos[i] != 1 and not xi[i]][:4]] = True
    mult = xi.astype(int)
    mult[next(i for i in order if xi[i])] = 2
    return mult


def repick_rows(rows: pd.DataFrame, xp: pd.Series) -> pd.DataFrame:
    """Input (b): each manager's XI and captain re-picked on `xp` (fpl_id -> GW t+1 xP), squads unchanged."""
    out = []
    for _, r in rows.groupby("entry_id", sort=False):
        x = xp.reindex(r["fpl_id"]).fillna(0.0).to_numpy(float)
        out.append(r.assign(multiplier=lineup(r["element_type"].to_numpy(), x)))
    return pd.concat(out, ignore_index=True)


def next_gw_eo(picks: pd.DataFrame, gw: int, xp: pd.Series, conc: float | None = None) -> tuple[pd.Series, int]:
    """A group's GW `gw` EO forecast (fpl_id -> fraction) and the GW of the picks it starts from.

    The method eo-blend.md found best: fair persistence (a) from the group's latest picks before `gw`, XI and
    captain re-picked on `xp` (GW `gw` xP) with no transfers (b), and with `conc` (the group's `HERD_CONC`) the
    armband herded (`herd_captains`). `picks` holds one group's managers only.
    """
    last = int(picks.loc[picks["gw"] < gw, "gw"].max())
    rows = repick_rows(fair_rows(picks, last), xp)
    if conc is not None:
        rows = herd_captains(rows, xp, conc)
    eo = rows.groupby("fpl_id")["multiplier"].sum() / rows["entry_id"].nunique()
    return eo[eo > 0].rename("eo"), last


def herd_captains(
    rows: pd.DataFrame, xp: pd.Series, conc: float = 0.94, tau: float = HERD_TAU, min_xi: float = HERD_MIN_XI
) -> pd.DataFrame:
    """(b) with the armband herded onto the group's consensus captain (eo-patterns-2025-26.md §5).

    The elite concentrate the armband far harder than "everyone captains their own highest xP": in 2025-26 one
    captain took 97% (AE64) and 91% (E64) of the armbands in a median week, splitting only when the top two
    premiums were close, and managers who don't own him buy him. So: candidates are the players in at least
    `min_xi` of the group's re-picked XIs, c1 and c2 the two with the highest xP, q = 1 / (1 + exp(-(xP1 - xP2) /
    tau)). Every manager's armband goes conc x q to c1, conc x (1 - q) to c2 and 1 - conc to their own re-picked
    captain. A manager who doesn't start c1 (or c2) buys him with that probability, starting him in place of
    their lowest-xP starter in his position. Multipliers are expected ones, so they can be fractional; `captain`
    is the expected armband.
    """
    xi = rows[rows["multiplier"] >= 1]
    share = xi.groupby("fpl_id")["entry_id"].nunique() / rows["entry_id"].nunique()
    x = xp.reindex(share.index[share >= min_xi]).fillna(0.0).sort_values(ascending=False, kind="stable")
    if len(x) < 2:
        return rows
    q = 1 / (1 + np.exp(-(x.iloc[0] - x.iloc[1]) / tau))
    pos = rows.drop_duplicates("fpl_id").set_index("fpl_id")["element_type"]
    out = []
    for _, r in rows.groupby("entry_id", sort=False):
        m = r.set_index("fpl_id")["multiplier"].astype(float)
        typ = r.set_index("fpl_id")["element_type"]
        cap = (m >= 2) * (1 - conc)
        m = m.clip(upper=1) + cap
        for c, a in ((x.index[0], conc * q), (x.index[1], conc * (1 - q))):
            if m.get(c, 0) < 1:  # buy (or start) him in place of the weakest starter in his position
                if c not in m:
                    m[c], typ[c], cap[c] = 0.0, pos[c], 0.0
                same = m.index[(typ == pos[c]) & (m >= 1) & (m.index != c)]
                if len(same):
                    m[xp.reindex(same).fillna(0.0).idxmin()] -= a
                m[c] += a
            m[c] += a
            cap[c] += a
        ids = m.index
        out.append(
            pd.DataFrame(
                {
                    "entry_id": r["entry_id"].iloc[0],
                    "fpl_id": ids,
                    "element_type": typ[ids].to_numpy(),
                    "multiplier": m.to_numpy(),
                    "captain": cap[ids].to_numpy(),
                }
            )
        )
    return pd.concat(out, ignore_index=True)


def chip_managers(chips: pd.DataFrame, gw: int) -> set:
    """Managers who played any chip in GW gw-1 or gw (the weeks a GW gw forecast and its baseline span)."""
    return set(chips.loc[chips["gw"].isin([gw - 1, gw]), "entry_id"])


# ---------------------------------------------------------------------------- weights


def simplex(m: int, step: float = STEP) -> np.ndarray:
    """Every weight vector of length m with non-negative multiples of `step` summing to 1."""
    n = round(1 / step)
    return np.array([c for c in itertools.product(range(n + 1), repeat=m) if sum(c) == n], float) / n


def fit(cases: list[dict], inputs=INPUTS, ks=nf.KS, step=STEP) -> tuple[float, np.ndarray, float]:
    """Best (k, weights, error) over the grid: mean EO error across `cases`, weighted by managers per case.

    Each case: {"X": {k: DataFrame [players x inputs]}, "y": Series [players], "n": managers}. The drift column is
    the only one that depends on k; with no drift input, k is irrelevant and the first k is returned.
    """
    grid = simplex(len(inputs), step)
    best = (None, None, np.inf)
    for k in ks if "drift" in inputs else ks[:1]:
        err = sum(c["n"] * np.abs(c["X"][k][list(inputs)].to_numpy() @ grid.T - c["y"].to_numpy()[:, None]).mean(0) for c in cases)
        err = err / sum(c["n"] for c in cases)
        i = int(np.argmin(err))
        if err[i] < best[2]:
            best = (k, grid[i], float(err[i]))
    return best


# ---------------------------------------------------------------------------- scoring


def errors(f: pd.Series, actual: pd.Series, xp: pd.Series) -> dict:
    """EO errors in points on the frames' (shared) player set: mean, summed and xP-weighted (GW t+1 xP >= 0)."""
    e = (f - actual).abs()
    w = xp.reindex(e.index).fillna(0.0).clip(lower=0)
    return {"eo_mae": e.mean(), "eo_sum": e.sum(), "eo_xpw": (e * w).sum() / w.sum() if w.sum() else np.nan}


def surges(prev_own: pd.Series, now_own: pd.Series, base_own: pd.Series | None = None, cut=nf.SURGE * 100) -> dict:
    """20+ point ownership moves t -> t+1: rises and falls, and (with `base_own`, e.g. (a) with free hits reverted)
    how many are still 20+ moves measured from that base."""
    move = now_own - prev_own
    out = {"rises": int((move >= cut).sum()), "falls": int((move <= -cut).sum())}
    if base_own is not None:
        big = move.abs() >= cut
        out["still_vs_base"] = int((big & ((now_own - base_own).abs() >= cut)).sum())
    return out


def top_captain(rows: pd.DataFrame) -> tuple[int, float]:
    """(fpl_id, share of managers) of the most-captained player: the multiplier-2+ pick, or `herd_captains`'
    expected armband."""
    cap = rows["captain"] if "captain" in rows else rows["multiplier"].ge(2).astype(float)
    counts = cap.groupby(rows["fpl_id"]).sum().sort_values(ascending=False)
    return int(counts.index[0]), counts.iloc[0] / rows["entry_id"].nunique()


def bootstrap(mats: dict, n_boot=1000, seed=0, pairs=(("banked", "persistence"), ("banked", "fair"))) -> pd.DataFrame:
    """Manager bootstrap of EO error gains, the same resampled managers in every GW.

    `mats`: {gw: {source: array [managers x players]}} of multipliers x100, managers in the same order in every
    array and GW, including "actual". Gain of a over b = 1 - error(a) / error(b), errors averaged over GWs.
    Returns per pair the full-sample gain and the 5%, 50% and 95% bootstrap quantiles.
    """
    rng = np.random.default_rng(seed)
    n = next(iter(next(iter(mats.values())).values())).shape[0]
    idx = rng.integers(0, n, (n_boot, n))
    counts = np.zeros((n_boot, n))
    np.add.at(counts, (np.arange(n_boot)[:, None], idx), 1)
    counts = np.vstack([np.ones(n), counts]) / n  # row 0: the full sample
    err = {}
    for m in mats.values():
        y = counts @ m["actual"]
        for s, x in m.items():
            if s != "actual":
                err[s] = err.get(s, 0) + np.abs(counts @ x - y).mean(1) / len(mats)
    rows = []
    for a, b in pairs:
        g = 1 - err[a] / err[b]
        q = np.quantile(g[1:], [0.05, 0.5, 0.95])
        rows.append({"gain": f"{a} vs {b}", "full_sample": g[0], "p05": q[0], "p50": q[1], "p95": q[2]})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------- the backtest (needs data/)


def _xp(path, gw: int) -> pd.Series:
    p = pd.read_csv(path, encoding="utf-8-sig").set_index("ID")
    return p[f"{gw}_Pts"].fillna(0.0) if f"{gw}_Pts" in p else pd.Series(dtype=float)


def _table(rows: pd.DataFrame, ids) -> pd.DataFrame:
    return nf.group_table(rows.assign(gw=0), pd.Series(list(ids)))[["fpl_id", "own", "eo"]]


def backtest(log=print) -> dict[str, pd.DataFrame]:
    """Inputs, LOWO blend and the critique's checks for every naive-field transition. Saves to data/derived/eo_blend/."""
    members, picks, _, chips, _ = nf._load()
    bootstrap_json, _ = nf._bootstrap_and_fixtures()
    pos = pd.Series({e["id"]: e["element_type"] for e in bootstrap_json["elements"]})
    names = {e["id"]: e["web_name"] for e in bootstrap_json["elements"]}
    solved = pd.read_parquet(nf.OUT_DIR / "backtest_solves.parquet")
    templates = pd.read_parquet(nf.OUT_DIR / "templates.parquet")
    cheap_k = pd.read_csv(nf.OUT_DIR / "compare_table.csv").query("variant == 'cheap'")
    deadline = nf.deadline_rows(picks)
    gws = sorted(int(g) for g in solved["gw"].unique())
    wc = chips[chips["chip"] == "wildcard"]

    # per-manager rows for every source and target GW
    src = {}
    for gw in gws:
        path = nf._projection_for(gw)
        xp = _xp(path, gw)
        fair = fair_rows(picks, gw - 1)
        repick = repick_rows(fair, xp)
        src[gw] = {
            "actual": deadline[deadline["gw"] == gw],
            "persistence": deadline[deadline["gw"] == gw - 1],
            "fair": fair,
            "repick": repick,
            "banked": solved[(solved["gw"] == gw) & (solved["variant"] == "banked")],
            "xp": xp,
            "ev": nf.future_ev(pd.read_csv(path, encoding="utf-8-sig"), gw, 5),
        }

    def group_inputs(gw, ids, group):
        """Group-level (own, eo) frames x100 on one fixed player set, per source and drift k."""
        s = src[gw]
        t = {n: _table(s[n], ids) for n in ("actual", "persistence", "fair", "repick", "herd", "banked")}
        drift = {k: nf.cheap_forecast(t["fair"], s["ev"], pos, k) for k in nf.KS}
        t["templates"] = templates[(templates["group"] == group) & (templates["gw"] == gw)][["fpl_id", "own", "eo"]]
        c = cheap_k[(cheap_k["group"] == group) & (cheap_k["gw"] == gw)].iloc[0]
        t["cheap"] = nf.cheap_forecast(t["persistence"], s["ev"], pos, c["k"], t["templates"], c["w"])
        frames = [*t.values(), *drift.values()]
        ids_ = pd.Index(sorted(set().union(*(set(f.loc[(f["own"] > 0) | (f["eo"] > 0), "fpl_id"]) for f in frames))), name="fpl_id")

        def col(f, what):
            return f.set_index("fpl_id")[what].reindex(ids_).fillna(0.0) * 100

        own = pd.DataFrame({n: col(f, "own") for n, f in t.items()})
        eo = pd.DataFrame({n: col(f, "eo") for n, f in t.items()})
        xs = {k: eo.assign(drift=col(d, "eo")) for k, d in drift.items()}
        owns = {k: own.assign(drift=col(d, "own")) for k, d in drift.items()}
        return xs, owns

    rows, weights, surge_rows, captain_rows, mats = [], [], [], [], {g: {} for g in nf.GROUPS}
    for group in nf.GROUPS:
        ids = set(members.loc[members["group"] == group, "entry_id"])
        for gw in gws:  # herding is per group (some managers are in both), so set for this group's pass
            s = src[gw]
            s["herd"] = herd_captains(s["repick"][s["repick"]["entry_id"].isin(ids)], s["xp"], HERD_CONC[group])
        share = {gw: wc.loc[(wc["gw"] == gw) & wc["entry_id"].isin(ids), "entry_id"].nunique() / len(ids) for gw in gws}
        cases = {}
        for gw in gws:
            chip = chip_managers(chips[chips["entry_id"].isin(ids)], gw)
            subsets = {"all": ids, "no chip": ids - chip, "chip": ids & chip}
            cases[gw] = {m: (sub, *group_inputs(gw, sub, group)) for m, sub in subsets.items() if sub}

        for gw in gws:
            s_hat = np.mean([share[g] for g in gws if g != gw])  # expected wildcard share: the other weeks' mean
            train = [
                {"X": cases[g]["no chip"][1], "y": cases[g]["no chip"][1][nf.KS[0]]["actual"], "n": len(cases[g]["no chip"][0])}
                for g in gws
                if g != gw and "no chip" in cases[g]
            ]
            fits = {"blend": fit(train), "blend_ab": fit(train, ("fair", "repick"))}
            for name, (k, w, err) in fits.items():
                inputs = INPUTS if name == "blend" else ("fair", "repick")
                weights.append(
                    {"group": group, "gw": gw, "blend": name, "k": k, **dict(zip(inputs, w, strict=True)), "train_mae": err, "s_hat": s_hat}
                )
            k = fits["blend"][0]
            for managers, (sub, xs, owns) in cases[gw].items():
                eo, own = xs[k].copy(), owns[k].copy()
                for name, (kb, w, _) in fits.items():
                    inputs = INPUTS if name == "blend" else ("fair", "repick")
                    eo[name] = xs[kb][list(inputs)] @ w
                    own[name] = owns[kb][list(inputs)] @ w
                    if managers == "all":  # wildcarders: the templates, at the expected (and, for reference, real) share
                        for tag, s in (("", s_hat), ("_wcshare", share[gw])):
                            eo[name + tag] = (1 - s) * eo[name] + s * eo["templates"]
                            own[name + tag] = (1 - s) * own[name] + s * own["templates"]
                prev = own["persistence"]
                move = own["actual"] - prev
                big = move[move.abs() >= nf.SURGE * 100]
                for f in eo.columns.drop("actual"):
                    if managers != "all" and f in ("templates", "cheap"):
                        continue
                    d = own[f] - prev
                    risers, fallers = (
                        set(d.nlargest(nf.TOP_K).index[d.nlargest(nf.TOP_K) > 0]),
                        set(d.nsmallest(nf.TOP_K).index[d.nsmallest(nf.TOP_K) < 0]),
                    )
                    rows.append(
                        {
                            "group": group,
                            "gw": gw,
                            "managers": managers,
                            "n_managers": len(sub),
                            "n_players": len(eo),
                            "forecast": f,
                            **errors(eo[f], eo["actual"], src[gw]["xp"]),
                            "own_mae": (own[f] - own["actual"]).abs().mean(),
                            "gap_banked": (eo[f] - eo["banked"]).abs().mean(),
                            "surges": len(big),
                            "caught": sum((p in risers) if m > 0 else (p in fallers) for p, m in big.items()),
                        }
                    )
                if managers == "all":
                    fh = chips.loc[
                        (chips["gw"] == gw - 1) & (chips["chip"] == "freehit") & chips["entry_id"].isin(ids), "entry_id"
                    ].nunique()
                    surge_rows.append({"group": group, "gw": gw, "freehit_prev": fh, **surges(prev, own["actual"], own["fair"])})
                    cap = {}
                    for name in ("actual", "persistence", "fair", "repick", "herd", "banked"):
                        r = src[gw][name]
                        r = r[r["entry_id"].isin(sub)]
                        r = r.assign(multiplier=r["multiplier"].clip(upper=2)) if name == "actual" else r
                        pid, sh = top_captain(r)
                        cap |= {f"{name}": names.get(pid, pid), f"{name}_share": sh}
                    captain_rows.append({"group": group, "gw": gw, **cap})

            # per-manager matrices for the bootstrap (all managers, chip weeks included)
            order = sorted(ids)
            players = sorted(
                set().union(
                    *(
                        set(src[gw][n].loc[src[gw][n]["entry_id"].isin(ids), "fpl_id"])
                        for n in ("actual", "persistence", "fair", "repick", "herd", "banked")
                    )
                )
            )
            mats[group][gw] = {
                n: src[gw][n][src[gw][n]["entry_id"].isin(ids)]
                .pivot_table(index="entry_id", columns="fpl_id", values="multiplier", aggfunc="sum")
                .reindex(index=order, columns=players)
                .fillna(0)
                .to_numpy()
                * 100
                for n in ("actual", "persistence", "fair", "repick", "herd", "banked")
            }

    pairs = (
        ("banked", "persistence"),
        ("banked", "fair"),
        ("banked", "repick"),
        ("repick", "fair"),
        ("fair", "persistence"),
        ("herd", "repick"),
    )
    boot = pd.concat([bootstrap(mats[g], pairs=pairs).assign(group=g) for g in nf.GROUPS])
    out = {
        "blend_table": pd.DataFrame(rows),
        "weights": pd.DataFrame(weights),
        "surges": pd.DataFrame(surge_rows),
        "captains": pd.DataFrame(captain_rows),
        "bootstrap": boot,
        "n_players": _n_players(),
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, t in out.items():
        t.to_csv(OUT_DIR / f"{name}.csv", index=False)
    return out


def _n_players() -> pd.DataFrame:
    """Critique check 1: players scored per row of naive_field's tables (each forecast had its own player set)."""
    b = pd.read_csv(nf.OUT_DIR / "backtest_table.csv").assign(table="backtest")
    c = pd.read_csv(nf.OUT_DIR / "compare_table.csv").assign(table="compare")
    return (
        pd.concat([b, c]).pivot_table(index=["table", "group", "variant"], columns="gw", values="n_players", aggfunc="first").reset_index()
    )


# ---------------------------------------------------------------------------- MIP gaps (critique check 7)

_GAPS = []


def _gap_init(*args):
    nf._init_worker(*args)
    import highspy

    run = highspy.Highs.run

    def logged(self):
        t0 = time.time()
        r = run(self)
        info = self.getInfo()
        _GAPS.append(
            {
                "status": self.modelStatusToString(self.getModelStatus()),
                "mip_gap": info.mip_gap,
                "objective": info.objective_function_value,
                "bound": info.mip_dual_bound,
                "secs": time.time() - t0,
            }
        )
        return r

    highspy.Highs.run = logged


def _gap_one(key, my_data, gw):
    _GAPS.clear()
    _, result = nf._solve_one(key, my_data, gw, "banked")
    return key, list(_GAPS), result


def mip_gaps(n=50, secs=15, horizon=5, workers=6, seed=0, log=print) -> pd.DataFrame:
    """Re-solve `n` random banked states with the backtest's settings and record what HiGHS reports.

    Also checks whether the re-solve returns the same GW t+1 squad and multipliers as the saved backtest solve.
    """
    members, picks, transfers, chips, _ = nf._load()
    bootstrap_json, fixtures = nf._bootstrap_and_fixtures()
    solved = pd.read_parquet(nf.OUT_DIR / "backtest_solves.parquet")
    solved = solved[solved["variant"] == "banked"]
    gws = sorted(int(g) for g in solved["gw"].unique())
    rng = np.random.default_rng(seed)
    pairs = [(int(e), int(g)) for e in sorted(members["entry_id"].unique()) for g in gws]
    pairs = [pairs[i] for i in rng.choice(len(pairs), n, replace=False)]
    by_file = {}
    for e, g in pairs:
        by_file.setdefault(nf._projection_for(g), []).append((e, g))
    rows = []
    for path, todo in by_file.items():
        boots = {g: nf.bootstrap_at(bootstrap_json, g, nf.market_prices(transfers, bootstrap_json, g)) for g in {g for _, g in todo}}
        states = {(e, g): nf.team_state(e, g, picks, transfers, chips, boots[g]) for e, g in todo}
        with ProcessPoolExecutor(workers, initializer=_gap_init, initargs=(str(path), boots, fixtures, secs, horizon)) as pool:
            futures = [pool.submit(_gap_one, key, d, key[1]) for key, d in states.items()]
            for i, f in enumerate(as_completed(futures), 1):
                (e, g), gaps, result = f.result()
                saved = solved[(solved["entry_id"] == e) & (solved["gw"] == g)]
                same = None if isinstance(result, str) else set(result) == set(zip(saved["fpl_id"], saved["multiplier"], strict=True))
                rows.append(
                    {
                        "entry_id": e,
                        "gw": g,
                        **(gaps[0] if gaps else {}),
                        "error": result if isinstance(result, str) else None,
                        "same_as_saved": same,
                    }
                )
                log(f"  {i}/{len(futures)}")
    for f in (UPSTREAM_DIR / "data").glob("fplrank_nf*.csv"):
        f.unlink()
    out = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT_DIR / "mip_gaps.csv", index=False)
    return out


def _main(argv=None):
    p = argparse.ArgumentParser(prog="python -m fplrank.model.eo_blend", description=__doc__.split("\n\n")[0])
    p.add_argument("mode", choices=["backtest", "gaps"])
    p.add_argument("--n", type=int, default=50, help="gaps: states to re-solve")
    p.add_argument("--workers", type=int, default=6)
    args = p.parse_args(argv)
    pd.set_option("display.width", 250)
    if args.mode == "backtest":
        for name, t in backtest().items():
            print(f"\n{name}\n{t.round(3).to_string(index=False)}")
    else:
        sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, "reconfigure") else None
        g = mip_gaps(args.n, workers=args.workers)
        print(g.round(4).to_string(index=False))
        print(g["mip_gap"].describe(percentiles=[0.5, 0.9]).round(4).to_string())
        print("same squad as saved:", g["same_as_saved"].mean())


if __name__ == "__main__":
    _main()
