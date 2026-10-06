"""Choose λ from the rank goal (S2c): P(finishing at or above the target line) for each S1 plan.

Brief S2 (revised after the critical review, 2026-10-06). Our score relative to the EO group:

    per GW, μ = κ x Σ (m - EO) x xP - hits,   var = s² x Σ (m - EO)² x v(xP)

m = our multiplier (0 bench, 1, 2 captain, 3 TC), EO the group's, v(xP) from `model.variance`. κ (default
0.3) shrinks our projected edge over the field, since projections are noisy and the field sees them too;
s (default 1) scales sd until V1 calibrates it. Covariance between players is ignored.

Season: the plan covers H GWs; the remaining GWs left - H are assumed to go like the λ = 0 plan's average
GW (a plan for this week is not repeated for the season). The gap to close is relative to the group:

    G = T_X(now) - ours(now) + drift x GWs left       (drift: `rank.target.line_drift`)

and P = Φ((μ_tot - G) / sqrt(var_tot + sd_line²)), sd_line from `rank.target.target_line`.
"""

import math
from dataclasses import dataclass

import pandas as pd

from fplrank.model import variance
from fplrank.opt.ownership import _raw_xp, eo_for

KAPPA = 0.3


@dataclass(frozen=True)
class Moments:
    mu: float  # expected relative score over the plan's GWs
    var: float  # its variance
    gws: int  # number of GWs in the plan


def plan_moments(solution: dict, projections: pd.DataFrame, eo, vtable: pd.DataFrame, kappa=KAPPA, s=1.0, hit_cost=4) -> Moments:
    """Mean and variance of a plan's relative score over its horizon."""
    picks = solution["picks"]
    xp = _raw_xp(projections)
    pos = projections.set_index("ID")["Pos"]
    mu = var = 0.0
    weeks = sorted(int(w) for w in picks["week"].unique())
    for w in weeks:
        rows = picks[picks["week"] == w]
        ours = {int(r.id): r.multiplier for r in rows.itertuples() if r.multiplier > 0}
        field = eo_for(eo, w)
        ids = pd.Index(sorted(set(ours) | {int(i) for i in field.index if field[i] > 0}))
        ids = ids[ids.isin(pos.index)]
        m = pd.Series([ours.get(i, 0) for i in ids], index=ids, dtype=float)
        e = field.reindex(ids).fillna(0.0)
        week_xp = pd.Series([xp.get((i, w), 0.0) for i in ids], index=ids)
        # v(xP) is banded within this source and GW, over every player it projects
        all_ids = projections["ID"]
        all_xp = pd.Series([xp.get((int(i), w), 0.0) for i in all_ids], index=all_ids.to_numpy())
        v = variance.lookup(vtable, pos.reindex(all_xp.index), all_xp).reindex(ids).fillna(0.0)
        hits = solution["statistics"].get(w, {}).get("pt", 0) * hit_cost
        mu += kappa * float(((m - e) * week_xp).sum()) - hits
        var += s**2 * float(((m - e) ** 2 * v).sum())
    return Moments(mu, var, len(weeks))


def season_moments(plan: Moments, base: Moments, gws_left: int) -> tuple[float, float]:
    """Mean and variance to GW38: the plan's horizon, then the λ = 0 plan's average GW for the rest."""
    rest = max(gws_left - plan.gws, 0)
    return plan.mu + base.mu / base.gws * rest, plan.var + base.var / base.gws * rest


def probability(mu: float, var: float, gap: float, sd_line: float = 0.0) -> float:
    sd = math.sqrt(var + sd_line**2)
    return 0.5 * (1 + math.erf((mu - gap) / (sd * math.sqrt(2)))) if sd > 0 else float(mu > gap)


def choose_lambda(gap: float, gws_left: int, plans: dict, sd_line: float = 0.0) -> pd.DataFrame:
    """One row per λ: P(reaching the line), mean, sd and EV; the best row first.

    plans: λ -> {"moments": Moments, "ev": float}; must include λ = 0 (the base for later GWs).
    """
    base = plans[0.0]["moments"]
    rows = []
    for lam, p in plans.items():
        mu, var = season_moments(p["moments"], base, gws_left)
        rows.append({"lam": lam, "p": probability(mu, var, gap, sd_line), "mu": mu, "sd": math.sqrt(var), "ev": p["ev"]})
    table = pd.DataFrame(rows)
    table["ev_cost"] = table.loc[table["lam"] == 0.0, "ev"].iloc[0] - table["ev"]
    return table.sort_values(["p", "ev"], ascending=False, ignore_index=True)


def report(table: pd.DataFrame, target_rank: int, kappa: float = KAPPA) -> str:
    best = table.iloc[0]
    ev0 = table[table["lam"] == 0.0].iloc[0]
    return (
        f"λ = {best['lam']:g}: P(top {target_rank:,}) {best['p']:.0%} vs {ev0['p']:.0%} for the EV plan, "
        f"EV cost {best['ev_cost']:.1f} points (κ = {kappa:g})"
    )
