"""Calibrate the scenario engine against a past season's actual points (brief B07).

The "projection" is vaastav's `xP` (FPL's own expected points for the GW). vaastav has no projected
minutes, so xMins is each player's average minutes per fixture over his previous 4 GWs. For every GW
we simulate each player and compare event frequencies with what happened:

- P(<= 2 points), P(>= 10), P(>= 15) by position and price band, and for captain candidates
  (the 5 highest xP each GW);
- correlation of points between team-mates (attackers; defenders and keepers), and between
  opposing attackers.

Actual frequencies get 90% bootstrap bands by resampling GWs (players in the same GW are not
independent). A row passes when the simulated value is inside the band.

Run: uv run python -m fplrank.sim.calibration [season]   -> docs/research/scenario-calibration.md
"""

import sys

import numpy as np
import pandas as pd

from fplrank.data import historical
from fplrank.paths import PROJECT_ROOT
from fplrank.sim.scenarios import player_index, simulate

REPORT_PATH = PROJECT_ROOT / "docs" / "research" / "scenario-calibration.md"
POS = {"GK": "G", "GKP": "G", "DEF": "D", "MID": "M", "FWD": "F"}
PRICE_BANDS = pd.IntervalIndex.from_breaks([0, 5.0, 7.0, 10.0, 99], closed="left")
THRESHOLDS = {"P(<=2)": lambda x: x <= 2, "P(>=10)": lambda x: x >= 10, "P(>=15)": lambda x: x >= 15}


def season_inputs(season: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(player-GW table with projection inputs and actual points, fixtures) for a past season."""
    merged = historical.merged_gw(season)
    teams = historical.teams(season)
    fixtures = historical.fixtures(season).dropna(subset=["event"]).astype({"event": int})
    merged["team_id"] = merged["team"].map(dict(zip(teams["name"], teams["id"], strict=True)))
    pg = merged.groupby(["element", "round"]).agg(
        xpts=("xP", "first"),
        pts=("total_points", "sum"),
        minutes=("minutes", "sum"),
        n_fix=("fixture", "size"),
        value=("value", "first"),
        pos=("position", "first"),
        team_id=("team_id", "first"),
    )
    pg = pg.reset_index().rename(columns={"element": "fpl_id", "round": "gw"}).sort_values(["fpl_id", "gw"])
    pg["pos"] = pg["pos"].map(POS)
    per_fixture = pg["minutes"] / pg["n_fix"]
    recent = per_fixture.groupby(pg["fpl_id"]).transform(lambda m: m.shift(1).rolling(4, min_periods=1).mean())
    pg["xmins"] = recent.fillna(0) * pg["n_fix"]
    pg["price"] = pg["value"] / 10
    return pg, fixtures


def simulate_season(pg: pd.DataFrame, fixtures: pd.DataFrame, gws, S: int = 2000, keep: int = 20) -> pd.DataFrame:  # noqa: N803
    """Per player-GW: actual points, simulated P(<=2)/P(>=10)/P(>=15), sim mean, and `keep` raw draws."""
    out = []
    for gw in gws:
        proj = pg[(pg["gw"] == gw) & (pg["xmins"] > 0)]
        if proj.empty:
            continue
        sim = simulate(proj, fixtures, S=S, H=1, seed=int(gw))[:, 0, :].astype(float)
        frame = proj.set_index("fpl_id").reindex(player_index(proj)).reset_index()
        frame["sim_mean"] = sim.mean(axis=0)
        for name, test in THRESHOLDS.items():
            frame[f"sim {name}"] = test(sim).mean(axis=0)
        frame["draws"] = list(sim[:keep].T)
        out.append(frame)
    return pd.concat(out, ignore_index=True)


def _cluster_bootstrap(df: pd.DataFrame, stat, reps: int = 500, seed: int = 0) -> tuple[float, float]:
    """90% band of `stat(df)` resampling whole GWs."""
    rng = np.random.default_rng(seed)
    by_gw = dict(tuple(df.groupby("gw")))
    keys = list(by_gw)
    vals = [stat(pd.concat([by_gw[k] for k in rng.choice(keys, len(keys))], ignore_index=True)) for _ in range(reps)]
    return tuple(np.nanquantile(vals, [0.05, 0.95]))


def frequency_table(res: pd.DataFrame) -> pd.DataFrame:
    """Actual vs simulated frequencies by group, with bootstrap bands and a pass flag."""
    res = res.assign(band=pd.cut(res["price"], PRICE_BANDS).astype(str))
    captains = res.sort_values("xpts", ascending=False).groupby("gw").head(5)
    groups = [("all", res)]
    groups += [(f"pos {p}", res[res["pos"] == p]) for p in ["G", "D", "M", "F"]]
    groups += [(f"price {b}", g) for b, g in res.groupby("band")]
    groups.append(("captain candidates (top-5 xP)", captains))
    rows = []
    for label, g in groups:
        row = {
            "group": label,
            "player-GWs": len(g),
            "mean xP": g["xpts"].mean(),
            "mean actual": g["pts"].mean(),
            "mean sim": g["sim_mean"].mean(),
        }
        for name, test in THRESHOLDS.items():
            actual = test(g["pts"]).mean()
            lo, hi = _cluster_bootstrap(g, lambda d, test=test: test(d["pts"]).mean())
            sim = g[f"sim {name}"].mean()
            row |= {f"{name} actual": actual, f"{name} band": f"{lo:.3f}-{hi:.3f}", f"{name} sim": sim, f"{name} ok": lo <= sim <= hi}
        rows.append(row)
    return pd.DataFrame(rows)


def _teammate_pairs(res: pd.DataFrame, positions: set[str], min_xmins: float = 60) -> pd.DataFrame:
    p = res[res["pos"].isin(positions) & (res["xmins"] >= min_xmins)][["gw", "fpl_id", "team_id", "pts", "xpts", "draws"]]
    pairs = p.merge(p, on=["gw", "team_id"])
    return pairs[pairs["fpl_id_x"] < pairs["fpl_id_y"]]


def correlation_table(res: pd.DataFrame, fixtures: pd.DataFrame) -> pd.DataFrame:
    """Correlation of (points - xP) between pairs of players: actual (with band) vs simulated."""
    opp_of = pd.concat(
        [
            fixtures[["event", "team_h", "team_a"]].rename(columns={"event": "gw", "team_h": "a", "team_a": "b"}),
            fixtures[["event", "team_h", "team_a"]].rename(columns={"event": "gw", "team_a": "a", "team_h": "b"}),
        ]
    )
    rows = [
        _corr_row("team-mates, attackers (M/F, 60+ xMins)", _teammate_pairs(res, {"M", "F"})),
        _corr_row("team-mates, defence (G/D, 60+ xMins)", _teammate_pairs(res, {"G", "D"})),
    ]
    att = res[res["pos"].isin({"M", "F"}) & (res["xmins"] >= 60)][["gw", "fpl_id", "team_id", "pts", "xpts", "draws"]]
    opp = att.merge(opp_of, left_on=["gw", "team_id"], right_on=["gw", "a"]).merge(att, left_on=["gw", "b"], right_on=["gw", "team_id"])
    rows.append(_corr_row("opponents, attackers (M/F, 60+ xMins)", opp[opp["fpl_id_x"] < opp["fpl_id_y"]]))
    return pd.DataFrame(rows)


def _corr_row(label: str, pairs: pd.DataFrame) -> dict:
    def actual_corr(d):
        return np.corrcoef(d["pts_x"] - d["xpts_x"], d["pts_y"] - d["xpts_y"])[0, 1]

    lo, hi = _cluster_bootstrap(pairs, actual_corr)
    dx = np.concatenate(pairs["draws_x"].to_numpy())
    dy = np.concatenate(pairs["draws_y"].to_numpy())
    k = len(pairs["draws_x"].iloc[0])
    sim = np.corrcoef(dx - np.repeat(pairs["xpts_x"].to_numpy(), k), dy - np.repeat(pairs["xpts_y"].to_numpy(), k))[0, 1]
    return {"pairs": label, "n": len(pairs), "actual": actual_corr(pairs), "band": f"{lo:.3f}-{hi:.3f}", "sim": sim, "ok": lo <= sim <= hi}


def gws_with_xp(pg: pd.DataFrame) -> list[int]:
    """GWs where vaastav's xP is populated (2025-26: only 11 of 38; elsewhere it is stored as 0), from GW2."""
    mean_xp = pg.groupby("gw")["xpts"].mean()
    return [int(gw) for gw, x in mean_xp.items() if x > 0 and gw >= 2]


def write_report(season: str = "2025-26", gws=None, S: int = 4000, path=REPORT_PATH) -> str:  # noqa: N803
    pg, fixtures = season_inputs(season)
    gws = gws_with_xp(pg) if gws is None else list(gws)
    res = simulate_season(pg, fixtures, gws, S=S)
    freq = frequency_table(res)
    corr = correlation_table(res, fixtures)
    fmt = freq.copy()
    for c in fmt.columns:
        if fmt[c].dtype == float:
            fmt[c] = fmt[c].map("{:.3f}".format) if c.startswith("P(") else fmt[c].map("{:.2f}".format)
    passed = int(sum(freq[f"{n} ok"].sum() for n in THRESHOLDS))
    total = len(freq) * len(THRESHOLDS)
    text = f"""# Scenario engine calibration ({season})

Generated by `uv run python -m fplrank.sim.calibration {season}`: `fplrank.sim.scenarios.simulate` vs
{season} actuals, GWs {", ".join(map(str, gws))}, {S:,} scenarios per GW, {len(res):,} player-GWs
(players with any recent minutes).

**Inputs.** Projection = vaastav `xP` (FPL's expected points). In 2025-26 vaastav stores xP as 0 in 27
of 38 GWs, so only the GWs where it is populated are used (there it is well calibrated: mean xP
1.19 vs mean points 1.20, and binned means line up). xMins = average minutes per fixture over the
previous 4 GWs (vaastav has no projected minutes). Some gaps below come from these inputs, not
the engine: compare "mean actual" with "mean xP". The simulated mean matches xP by construction.

**Test.** Actual frequencies get 90% bands from resampling whole GWs. A row passes when the
simulated value is inside the band. {passed}/{total} frequency checks pass;
correlations: {int(corr["ok"].sum())}/{len(corr)}.

## Frequencies (P(<=2) = blank, P(>=10) / P(>=15) = hauls)

{fmt.to_markdown(index=False)}

## Correlation of (points - xP) between pairs of players

{corr.assign(actual=corr["actual"].round(3), sim=corr["sim"].round(3)).to_markdown(index=False)}

Team-mate correlation comes from the shared team-goals draw (attackers) and the shared goals
against (clean sheets, goals conceded) for defenders and keepers. Opponents' attackers have only
weak dependence in the engine (none in goals; bonus is shared within a fixture). `SHARED_WEIGHT`
(how often a player's goal/assist draw uses his team's goals) was set to 0.7 on these same GWs, so
the attacker correlation row is in-sample.

## Reading (v0, 2026-10-05)

- **Blanks are right:** P(<=2) is inside the band for every position and price band.
- **Hauls are too frequent:** P(>=10) and P(>=15) run high for keepers, defenders and midfielders
  (all players: about 4.9% vs 3.5% for 10+). Likely causes: clean sheet, defensive contribution and
  bonus are independent in the engine but not in reality (busy defenders keep fewer clean sheets),
  and bonus is allocated by a rough BPS proxy.
- **Defence correlation is too low** (about 0.33 vs 0.53): team-mates share clean sheets and goals
  conceded, but the independent defensive contributions and bonus noise dilute it.
- **Captain candidates fall short of their mean** (about 8.0 vs 9.1 xP for the top 5 each GW):
  the per-position scoring caps still bind for the very best fixtures, and the xMins stand-in
  (recent minutes) understates nailed starters.
- Next steps: link defensive contributions to the opponent's attack, a real BPS model, caps based
  on share of team goals only, and re-running against projections with real xMins (e.g. this
  season's Solio files once GWs have been played).

Speed: 10,000 scenarios x 6 GWs x all players (562) take 35-45 seconds on Alex's PC.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    print(write_report(*sys.argv[1:2]))
