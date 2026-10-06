"""EO projector idea 1: elite ownership flows from ΔEV and the price-band gap (B04b-1a refit).

Squad ownership moves one GW at a time; EO follows from it plus a captain part:

    logit(own[t+1]) = a + b·logit(own[t]) + c·xp + d·pts + e·ΔEV + f·gap + g·wc + h·wc·xp

- `own`: share of the group owning the player (squad, not EO), from the 2025-26 Elite 64 rebuild.
- `xp`: FPL `ep_next` for GW t+1 (Core Insights); `ΔEV = xp(t+1) - xp(t)`; `pts`: points in GW t.
- `gap`: best `xp` among other same-position players costing at most £0.5m more, minus his own.
  Big positive = sell pressure on owners; negative = he is the best buy in his band.
- `wc`: share of the group wildcarding in t+1 (chip weeks behave differently).
- Flows must balance: after the logistic step the forecast is shifted in logit space per position so
  the group still owns 2 G, 5 D, 5 M and 3 F per manager.
- Fitted per group (AE64, E64 behave differently: AE64 is sharper but more template).

EO forecast: `eo[t] - cap_eo[t] + (own_hat - own[t]) + cap_eo_hat`, where `cap_eo` is the captain
share times (1 + TC share of captains) and `cap_eo_hat` is v0's captain softmax on `own_hat` and `xp`.

The "v0 form" is the same model with only `a, b, c, d` (v0's equation on squad ownership).

Backtest (pass criteria fixed in docs/research/eo-projector.md before looking at results):
leave-one-GW-out per group over 2025-26; EO scored on players listed at t+1 (GW11-38); ownership on
players owned at t or t+1 (GW2-38); surge = |Δown| >= 0.20, caught if in that GW's top-10 predicted
risers (or fallers). Quiet weeks: no wildcard/free hit above 10% of the group and no surge.
`uv run python -m fplrank.model.eo_flow` prints the report (needs Core Insights and vaastav files).
"""

import numpy as np
import pandas as pd
from scipy.optimize import brentq, minimize
from scipy.special import expit

from fplrank.model.ownership import _shrunk_logit, fit_tau_arrays

GROUPS = ("AE64", "E64")
SQUAD = {"G": 2, "D": 5, "M": 5, "F": 3}
V0_FEATURES = ["const", "lo", "xp", "pts"]
FULL_FEATURES = [*V0_FEATURES, "dev", "gap", "wc", "wc_xp"]
# Added after the first backtest (so not part of the pre-registered test): gap as sell pressure on
# owners and buy pull on non-owners, as the doc describes it, instead of one slope for both
SPLIT_FEATURES = [*V0_FEATURES, "dev", "gap_own", "gap_not", "wc", "wc_xp"]
MODELS = {"v0": V0_FEATURES, "full": FULL_FEATURES, "split": SPLIT_FEATURES}
SURGE = 0.20
TOP = 10
PRICE_BAND = 0.5
# The big paired moves of 2025-26 (eo-projector.md, idea 2): every surge in these GWs is a test case
SURGE_WEEKS = (12, 18, 22, 23, 25)


# ---------------------------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------------------------


def price_gap(players: pd.DataFrame, band: float = PRICE_BAND) -> pd.Series:
    """Per row of `players` (`pos, price, xp`, one GW): best xp of another same-position player costing
    at most `price + band`, minus own xp. NaN if nobody else qualifies."""
    out = pd.Series(np.nan, index=players.index)
    for _, g in players.groupby("pos"):
        price, xp = g["price"].to_numpy(float), g["xp"].to_numpy(float)
        ok = price[None, :] <= price[:, None] + band + 1e-9
        np.fill_diagonal(ok, False)
        best = np.where(ok, xp[None, :], -np.inf).max(axis=1)
        out[g.index] = np.where(np.isfinite(best), best - xp, np.nan)
    return out


def transitions(own: pd.DataFrame, stats: pd.DataFrame, pts: pd.DataFrame, chips: pd.DataFrame) -> pd.DataFrame:
    """One row per (gw_next, fpl_id) for one group.

    own: `gw, fpl_id, own, n` (squad ownership share, group size); stats: `gw, fpl_id, pos, xp, price`
    (xp for that GW, price at its deadline); pts: `gw, fpl_id, pts`; chips: `gw, wc` (wildcard share).
    Universe for t+1: everyone with stats in t+1 plus anyone owned in t or t+1. Missing ownership = 0.
    """
    rows = []
    pos = stats.drop_duplicates("fpl_id", keep="last").set_index("fpl_id")["pos"]
    wc = chips.set_index("gw")["wc"]
    for nxt in sorted(set(own["gw"]) & set(stats["gw"])):
        if nxt - 1 not in set(own["gw"]):
            continue
        now, later = own[own["gw"] == nxt - 1].set_index("fpl_id"), own[own["gw"] == nxt].set_index("fpl_id")
        s_now = stats[stats["gw"] == nxt - 1].set_index("fpl_id")
        s_next = stats[stats["gw"] == nxt].set_index("fpl_id")
        ids = s_next.index.union(now.index).union(later.index)
        f = pd.DataFrame(index=ids.rename("fpl_id"))
        f["gw_next"] = nxt
        f["pos"] = pos.reindex(ids)
        f["own_t"] = now["own"].reindex(ids).fillna(0)
        f["own_next"] = later["own"].reindex(ids).fillna(0)
        f["n"] = float(later["n"].iloc[0])
        f["xp"] = s_next["xp"].reindex(ids).fillna(0)
        f["price"] = s_next["price"].reindex(ids)
        f["dev"] = f["xp"] - s_now["xp"].reindex(ids).fillna(f["xp"])
        f["pts"] = pts[pts["gw"] == nxt - 1].set_index("fpl_id")["pts"].reindex(ids).fillna(0)
        f["wc"] = float(wc.get(nxt, 0.0))
        f = f.dropna(subset=["pos", "price"])
        f["gap"] = price_gap(f).fillna(0)
        rows.append(f.reset_index())
    out = pd.concat(rows, ignore_index=True)
    out["const"] = 1.0
    out["lo"] = _shrunk_logit(out["own_t"], out["n"])
    out["wc_xp"] = out["wc"] * out["xp"]
    out["gap_own"] = out["gap"] * out["own_t"]
    out["gap_not"] = out["gap"] * (1 - out["own_t"])
    return out


# ---------------------------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------------------------


def fit_flow(trans: pd.DataFrame, features=FULL_FEATURES) -> np.ndarray:
    """Coefficients for `features` by binomial likelihood of own_next (shares of n managers)."""
    x = trans[list(features)].to_numpy(float)
    y, n = trans["own_next"].to_numpy(float), trans["n"].to_numpy(float)
    total = n.sum()

    def nll(beta):
        z = x @ beta
        value = -np.sum(n * (y * -np.logaddexp(0, -z) + (1 - y) * -np.logaddexp(0, z))) / total
        return value, -x.T @ (n * (y - expit(z))) / total

    start = np.zeros(len(features))
    start[list(features).index("lo")] = 1.0
    return minimize(nll, start, jac=True, method="L-BFGS-B").x


def predict_own(trans: pd.DataFrame, beta: np.ndarray, features=FULL_FEATURES, balance: bool = True) -> np.ndarray:
    """Forecast own_next; with `balance`, shift logits per GW and position so each manager owns a full squad."""
    z = trans[list(features)].to_numpy(float) @ beta
    if not balance:
        return expit(z)
    out = np.empty(len(trans))
    for (_, pos), idx in trans.groupby(["gw_next", "pos"]).indices.items():
        target, zi = SQUAD[pos], z[idx]
        shift = brentq(lambda s, zi=zi, target=target: expit(zi + s).sum() - target, -30, 30)
        out[idx] = expit(zi + shift)
    return out


def captain_eo(own: np.ndarray, xp: np.ndarray, tau: float, tc: float) -> np.ndarray:
    """v0 captain softmax (`ownership.OwnershipModel.cap_shares`) times (1 + TC share of captains)."""
    w = np.asarray(own) * np.exp((np.asarray(xp) - np.max(xp)) / tau)
    return (w / w.sum() if w.sum() > 0 else w) * (1 + tc)


# ---------------------------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------------------------


def surge_recall(errors: pd.DataFrame, pred: str, threshold: float = SURGE, top: int = TOP) -> pd.DataFrame:
    """Surges (|own_next - own_t| >= threshold) with `hit` = in that GW's top-`top` predicted movers that way."""
    rows = []
    for gw, g in errors.groupby("gw_next"):
        move, fc = g["own_next"] - g["own_t"], g[pred] - g["own_t"]
        risers, fallers = set(fc.nlargest(top).index), set(fc.nsmallest(top).index)
        for i in g.index[move.abs() >= threshold]:
            rows.append({"gw_next": gw, "fpl_id": g.at[i, "fpl_id"], "move": move[i], "hit": i in (risers if move[i] > 0 else fallers)})
    return pd.DataFrame(rows, columns=["gw_next", "fpl_id", "move", "hit"])


def backtest_group(trans: pd.DataFrame, eo: pd.DataFrame, cap: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Leave-one-GW-out for one group.

    trans: from `transitions`; eo: `gw, fpl_id, eo, listed` (complete panel); cap: `gw, fpl_id, cap_eo`
    (actual captain EO incl. TC) plus `gw, tc` per GW in `cap.attrs["tc"]` (a Series by GW).
    Returns (ownership rows with forecasts, EO rows scored on listed players).
    """
    tc = cap.attrs["tc"]
    cap_tab = cap.set_index(["gw", "fpl_id"])["cap_eo"]
    eo_tab = eo.set_index(["gw", "fpl_id"])
    own_rows, eo_rows = [], []
    gws = sorted(trans["gw_next"].unique())
    tau_data = {}
    for gw in gws:  # captain data per GW for the tau fit: (own, xp, captain share)
        g = trans[trans["gw_next"] == gw]
        c = cap_tab.reindex(list(zip([gw] * len(g), g["fpl_id"], strict=True))).fillna(0).to_numpy() / (1 + tc.get(gw, 0.0))
        tau_data[gw] = (g["own_next"].to_numpy(), g["xp"].to_numpy(), c)
    for gw in gws:
        train, test = trans[trans["gw_next"] != gw], trans[trans["gw_next"] == gw].copy()
        for name, feats in MODELS.items():
            test[name] = predict_own(test, fit_flow(train, feats), feats)
        own_rows.append(test)
        if gw - 1 not in set(eo["gw"]) or gw not in set(eo["gw"]):
            continue
        tau = fit_tau_arrays([v for k, v in tau_data.items() if k != gw])
        ids = test["fpl_id"].to_numpy()
        eo_t = eo_tab["eo"].reindex(list(zip([gw - 1] * len(ids), ids, strict=True))).fillna(0).to_numpy()
        cap_t = cap_tab.reindex(list(zip([gw - 1] * len(ids), ids, strict=True))).fillna(0).to_numpy()
        base = eo_t - cap_t
        frame = pd.DataFrame({"gw_next": gw, "fpl_id": ids, "persist": eo_t})
        frame["captain_only"] = base + captain_eo(test["own_t"], test["xp"], tau, tc.get(gw, 0.0))
        for name in MODELS:
            frame[name] = base + (test[name] - test["own_t"]).to_numpy() + captain_eo(test[name], test["xp"], tau, tc.get(gw, 0.0))
        nxt = eo_tab.loc[gw]
        listed = nxt.index[nxt["listed"]]
        frame = frame.set_index("fpl_id").reindex(listed).fillna({"persist": 0}).reset_index()
        frame["gw_next"] = gw
        for col in ("captain_only", *MODELS):  # listed but outside the universe: carry forward
            frame[col] = frame[col].fillna(frame["persist"]).clip(lower=0)
        frame["eo"] = nxt.loc[listed, "eo"].to_numpy()
        eo_rows.append(frame)
    return pd.concat(own_rows, ignore_index=True), pd.concat(eo_rows, ignore_index=True)


def score(own_rows: pd.DataFrame, eo_rows: pd.DataFrame, quiet_gws, surge_weeks=SURGE_WEEKS) -> dict:
    """Headline numbers for one group, with the pass/fail verdict from eo-projector.md."""
    owned = own_rows[(own_rows["own_t"] > 0) | (own_rows["own_next"] > 0)]
    own_mae = {m: float((owned[m] - owned["own_next"]).abs().mean()) for m in ("own_t", *MODELS)}
    eo_mae = {m: float((eo_rows[m] - eo_rows["eo"]).abs().mean()) for m in ("persist", "captain_only", *MODELS)}
    quiet = eo_rows[eo_rows["gw_next"].isin(quiet_gws)]
    quiet_mae = {m: float((quiet[m] - quiet["eo"]).abs().mean()) for m in ("persist", *MODELS)} if len(quiet) else {}
    surges = {m: surge_recall(owned, m) for m in MODELS}
    recall = {m: float(s["hit"].mean()) for m, s in surges.items()}
    week = surges["full"][surges["full"]["gw_next"].isin(surge_weeks)]
    gain = 1 - eo_mae["full"] / eo_mae["persist"]
    checks = {
        "eo_15pct": gain >= 0.15,
        "quiet_no_worse": bool(quiet_mae) and quiet_mae["full"] <= quiet_mae["persist"],
        "recall_50": recall["full"] >= 0.5,
        "recall_50_surge_weeks": len(week) > 0 and float(week["hit"].mean()) >= 0.5,
    }
    return {
        "own_mae": own_mae,
        "eo_mae": eo_mae,
        "eo_gain": gain,
        "quiet_gws": sorted(quiet_gws),
        "quiet_mae": quiet_mae,
        "recall": recall,
        "surges": len(surges["full"]),
        "surge_week_recall": float(week["hit"].mean()) if len(week) else float("nan"),
        "surge_week_table": week,
        "checks": checks,
        "passed": all(checks.values()),
    }


# ---------------------------------------------------------------------------------------------
# 2025-26 data (repo files; not used by tests)
# ---------------------------------------------------------------------------------------------


def season_inputs(season: str = "2025-26") -> dict:
    """Everything `run` needs, per group, from datasets/ plus the cached Core Insights and vaastav files."""
    from fplrank.data import core_insights, historical
    from fplrank.data.elite import POS_BY_ELEMENT_TYPE, eo_panel, load_eo, load_meta
    from fplrank.data.elite import elite_ownership as load_own

    stats = core_insights.playerstats(season).rename(columns={"ep_next": "xp", "now_cost": "price"})[["gw", "fpl_id", "xp", "price"]]
    raw = historical.players_raw(season)
    stats["pos"] = stats["fpl_id"].map(dict(zip(raw["id"], raw["element_type"].map(POS_BY_ELEMENT_TYPE), strict=True)))
    mg = historical.merged_gw(season)
    pts = mg.groupby(["GW", "element"])["total_points"].sum().reset_index()
    pts.columns = ["gw", "fpl_id", "pts"]
    own_all = load_own(season)
    meta = load_meta(season=season)
    panel = eo_panel(season)
    listed = load_eo(season=season)
    names = own_all.drop_duplicates("fpl_id", keep="last").set_index("fpl_id")["player"]
    out = {}
    for group in GROUPS:
        own = own_all[own_all["group"] == group].copy()
        own["n"] = (own["count"] / own["own"]).where(own["own"] > 0).groupby(own["gw"]).transform("median")
        chip = (
            meta[(meta["group"] == group) & (meta["table"] == "chip_active")]
            .pivot_table(index="gw", columns="item", values="count", aggfunc="sum")
            .fillna(0)
        )
        chip = chip.reindex(columns=sorted(set(chip.columns) | {"WC", "FH", "TC"}), fill_value=0)
        share = chip.div(chip.sum(axis=1), axis=0)
        caps = meta[(meta["group"] == group) & (meta["table"] == "captain")].dropna(subset=["fpl_id"])
        caps = caps.groupby(["gw", "fpl_id"])["count"].sum().reset_index()
        size = caps.groupby("gw")["count"].transform("sum")
        tc = (share["TC"] * chip.sum(axis=1) / caps.groupby("gw")["count"].sum()).fillna(0)
        caps["cap_eo"] = caps["count"] / size * (1 + caps["gw"].map(tc))
        caps.attrs["tc"] = tc
        eo = panel[panel["group"] == group][["gw", "fpl_id", "eo", "censored"]].astype({"fpl_id": "int64"})
        eo["listed"] = ~eo["censored"]
        ids = set(listed.loc[listed["group"] == group, "fpl_id"].dropna().astype(int))
        assert ids <= set(eo["fpl_id"])
        out[group] = {
            "trans": transitions(
                own[["gw", "fpl_id", "own", "n"]].astype({"fpl_id": "int64"}), stats, pts, share["WC"].rename("wc").reset_index()
            ),
            "eo": eo,
            "cap": caps,
            "chip_share": share,
        }
    out["names"] = names
    return out


def quiet_weeks(trans: pd.DataFrame, chip_share: pd.DataFrame, chip_cut: float = 0.10, threshold: float = SURGE) -> list[int]:
    """GWs with wildcard + free hit under `chip_cut` of the group and no ownership move of `threshold` or more."""
    move = (trans["own_next"] - trans["own_t"]).abs().groupby(trans["gw_next"]).max()
    chips = (chip_share["WC"] + chip_share["FH"]).reindex(move.index).fillna(0)
    return [int(g) for g in move.index if move[g] < threshold and chips[g] < chip_cut]


def week_kind(chip_share: pd.DataFrame, gw: int, cut: float = 0.10) -> str:
    """ "chip" if any chip (WC, FH, TC, BB) is played by `cut` or more of the group in `gw`, else "normal"."""
    row = chip_share.reindex(columns=["WC", "FH", "TC", "BB"], fill_value=0).loc[gw] if gw in chip_share.index else None
    return "chip" if row is not None and (row >= cut).any() else "normal"


def run(season: str = "2025-26") -> dict:
    inputs = season_inputs(season)
    results = {}
    for group in GROUPS:
        d = inputs[group]
        own_rows, eo_rows = backtest_group(d["trans"], d["eo"], d["cap"])
        res = score(own_rows, eo_rows, quiet_weeks(d["trans"], d["chip_share"]))
        res["coef"] = {m: dict(zip(f, fit_flow(d["trans"], f), strict=True)) for m, f in MODELS.items() if m != "v0"}
        eo_rows["kind"] = eo_rows["gw_next"].map(lambda g, cs=d["chip_share"]: week_kind(cs, g))
        res["own_rows"], res["eo_rows"] = own_rows, eo_rows
        results[group] = res
    results["names"] = inputs["names"]
    return results


def report(results: dict) -> str:
    names = results["names"]
    cols = ["persist", "captain_only", *MODELS]
    head = "| | persistence | captain only | v0 form | v0 + ΔEV + gap | post-hoc: gap split |"
    lines = []
    for group in GROUPS:
        r = results[group]
        e, o, q, rec = r["eo_mae"], r["own_mae"], r["quiet_mae"], r["recall"]
        kinds = {k: {m: 100 * (g[m] - g["eo"]).abs().mean() for m in cols} for k, g in r["eo_rows"].groupby("kind")}
        lines += [f"## {group}", "", head, "|---|---|---|---|---|---|"]
        lines.append("| EO MAE (pts), GW11-38 | " + " | ".join(f"{100 * e[m]:.2f}" for m in cols) + " |")
        for k, v in kinds.items():
            lines.append(f"| ... {k} weeks | " + " | ".join(f"{v[m]:.2f}" for m in cols) + " |")
        lines.append(f"| ... quiet weeks | {100 * q['persist']:.2f} | | " + " | ".join(f"{100 * q[m]:.2f}" for m in MODELS) + " |")
        lines.append(
            f"| Ownership MAE (pts), GW2-38 | {100 * o['own_t']:.2f} | | " + " | ".join(f"{100 * o[m]:.2f}" for m in MODELS) + " |"
        )
        lines.append(f"| Surge recall ({r['surges']} surges) | | | " + " | ".join(f"{rec[m]:.0%}" for m in MODELS) + " |")
        lines += [
            "",
            f"Pre-registered model (v0 + ΔEV + gap): EO error {-r['eo_gain']:+.0%} vs persistence (pass needs -15% or better); "
            f"surge recall {rec['full']:.0%}, {r['surge_week_recall']:.0%} in GW{'/'.join(map(str, SURGE_WEEKS))}. "
            f"Quiet weeks: {r['quiet_gws']}.",
            "Checks: "
            + ", ".join(f"{k} {'pass' if v else 'FAIL'}" for k, v in r["checks"].items())
            + f". **{'PASS' if r['passed'] else 'FAIL'}**",
            "",
        ]
        for m, coef in r["coef"].items():
            lines.append(f"Coefficients, {m} (all GWs): " + ", ".join(f"{k} {v:+.3f}" for k, v in coef.items()))
        week = r["surge_week_table"]
        if len(week):
            lines += [
                "",
                "Surges in the five test weeks (pre-registered model): "
                + "; ".join(
                    f"GW{w.gw_next} {names.get(w.fpl_id, w.fpl_id)} {100 * w.move:+.0f} {'hit' if w.hit else 'miss'}"
                    for w in week.itertuples()
                ),
            ]
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report(run()))
