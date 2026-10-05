# %% [markdown]
# # B04: Ownership dynamics v0
#
# Cell-marked script: VS Code opens it as a notebook ("Run Cell"), or run it top to bottom with
# `uv run python notebooks/b04_ownership_dynamics.py`. Needs local data: `data/collected/` (B03),
# registered projections (B02) and FPL snapshots. Write-up: docs/research/ownership-dynamics-v0.md.

# %%
import numpy as np
import pandas as pd

from fplrank.model import ownership as o

pd.set_option("display.width", 160)
groups = [o.TOP_GROUP, *o.ELITE_GROUPS]
tables = {g: o.group_table(g) for g in groups}
chips = pd.read_parquet(o.COLLECTED_DIR / "chips.parquet")

# %% [markdown]
# ## Q1: XI share transitions (fitted on all top-1000 transitions)

# %%
trans = o.transitions(tables[o.TOP_GROUP])
a, b, c, d = o.fit_xi(trans)
print(f"logit(xi[t+1]) = {a:.2f} + {b:.2f} logit(xi[t]) + {c:.2f} xpts[t+1] + {d:.3f} pts[t]   (n = {len(trans)} player-GWs)")
for xpts in (2, 4, 6):
    for xi in (0.05, 0.3, 0.8):
        print(f"  xi {xi:.0%}, next-GW xpts {xpts}: -> {o.OwnershipModel(np.array([a, b, c, d])).xi_next(xi, 1000, xpts, 0):.0%}")

# %% [markdown]
# ## Q2: captain temperature per group (all GWs)

# %%
taus = {g: o.fit_tau(t) for g, t in tables.items()}
print({g: round(t, 2) for g, t in taus.items()})
for g, t in taus.items():
    print(f"  {g}: captaincy odds vs a player projected 1 point less: x{np.exp(1 / t):.1f}")

# %% [markdown]
# ## Q3: chip weeks. How many XI places does a manager change, by chip played this GW?

# %%
picks = pd.read_parquet(o.COLLECTED_DIR / "picks.parquet")
xi_sets = picks[picks["position"] <= 11].groupby(["entry_id", "gw"])["fpl_id"].apply(frozenset)
changes = []
for (entry, gw), now in xi_sets.items():
    if (entry, gw - 1) in xi_sets.index:
        changes.append({"entry_id": entry, "gw": gw, "changed": len(now - xi_sets[(entry, gw - 1)])})
changes = pd.DataFrame(changes)
played = chips.rename(columns={"chip": "chip_now"})[["entry_id", "gw", "chip_now"]]
prev = chips.assign(gw=chips["gw"] + 1).rename(columns={"chip": "chip_prev"})[["entry_id", "gw", "chip_prev"]]
changes = changes.merge(played, how="left").merge(prev, how="left").fillna({"chip_now": "none", "chip_prev": "none"})
changes["kind"] = np.where(changes["chip_prev"] == "freehit", "after Free Hit", changes["chip_now"])
print(changes.groupby("kind")["changed"].agg(["mean", "count"]).round(2))
print(
    "\nTop-1000 chip use by GW:\n",
    chips[chips["gw"] <= 5].pivot_table(index="gw", columns="chip", values="entry_id", aggfunc="count").fillna(0).astype(int),
)

# %% [markdown]
# ## Q4: does AE64 lead E64?
# Regress next week's E64 change on this week's AE64 - E64 gap (players listed in both).

# %%
ae = tables["AE64"].set_index(["gw", "fpl_id"])["eo"]
e = tables["E64"].set_index(["gw", "fpl_id"])["eo"]
rows = []
for gw in range(1, 5):
    for pid in set(ae.xs(gw).index) & set(e.xs(gw).index):
        if (gw + 1, pid) in e.index and (gw + 1, pid) in ae.index:
            rows.append(
                {
                    "gw": gw,
                    "gap": ae[(gw, pid)] - e[(gw, pid)],
                    "dE": e[(gw + 1, pid)] - e[(gw, pid)],
                    "dA": ae[(gw + 1, pid)] - ae[(gw, pid)],
                }
            )
lead = pd.DataFrame(rows)
for target, sign in (("dE", 1), ("dA", -1)):
    gap = sign * lead["gap"]
    slope, corr = np.polyfit(gap, lead[target], 1)[0], gap.corr(lead[target])
    print(f"{target} on {'AE64-E64' if sign == 1 else 'E64-AE64'} gap: slope {slope:.2f}, corr {corr:.2f}, n {len(lead)}")

# %% [markdown]
# ## Backtest: leave one GW out, model vs "next week = this week" (no chip information)

# %%
errors, summary, params = o.backtest(groups, chips_known=False)
print(summary.round(3).to_string(index=False))
print(summary.groupby("group")[["mae_model", "mae_persist"]].mean().round(3))
_, summary_known, _ = o.backtest(groups, chips_known=True)
print("\nWith next GW's chip use known:\n", summary_known.groupby("group")[["mae_model", "mae_persist"]].mean().round(3))
print("\nxi params by held-out GW:", {gw: np.round(p["xi"], 2).tolist() for gw, p in params.items()})

# %% [markdown]
# ## Error bands: 80% band from the backtest residuals, coverage on the same GWs

# %%
model = o.fit_default(groups)
for g in groups:
    err = errors[errors["group"] == g]
    q = model.residual_q[g].to_numpy()[pd.cut(err["eo_mean"], o.BUCKETS).cat.codes]
    inside = (err["eo"] >= err["eo_mean"] + q[:, 0]) & (err["eo"] <= err["eo_mean"] + q[:, 1])
    print(f"{g}: {inside.mean():.0%} of actual EOs inside the band (in-sample, so optimistic)")
print(model.residual_q[o.TOP_GROUP].round(3))

# %% [markdown]
# ## Example: forecast for GW6 (no chips assumed)

# %%
fc = o.forecast_eo(o.TOP_GROUP, 6, o.state_for(o.TOP_GROUP, 6, tables[o.TOP_GROUP], chips_known=False), model)
print(fc.head(12).round(2).to_string(index=False))
