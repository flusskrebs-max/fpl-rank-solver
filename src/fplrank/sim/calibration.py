"""Out-of-sample calibration of the scenario engine (briefs B07, B07b).

Split: tune on 2023-24, test on 2024-25 (held out), final check on 2025-26. The "projection" is
vaastav's `xP` (FPL's expected points; populated in 37/38 GWs of 2023-24, 35/38 of 2024-25 and only
11/38 of 2025-26), and xMins is each player's average minutes per fixture over his previous 4 GWs.

For every player-GW (players with any recent minutes) we compare simulated and actual:

- P(<= 2), P(>= 10), P(>= 15) by position, price band and for the top 10 xP each GW (captain candidates),
  with 90% bootstrap bands for the actual frequencies (resampling whole GWs);
- correlation of (points - xP) between team-mates (attackers; defence) and opposing attackers;
- how well simulated means match xP (`match_summary`);
- one number per model: mean log score (-log P(actual points), smoothed) and mean CRPS per player-GW.

A simple empirical benchmark is scored the same way: points drawn from the training season's actual
points for the same position x xP band x xMins band, with a shared team factor (Gaussian copula).

Run: uv run python -m fplrank.sim.calibration   -> docs/research/scenario-calibration.md
"""

import sys
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

from fplrank.data import historical
from fplrank.paths import PROJECT_ROOT
from fplrank.sim.scenarios import DEFAULT_PARAMS, RULES, Params, match_summary, player_index, simulate

REPORT_PATH = PROJECT_ROOT / "docs" / "research" / "scenario-calibration.md"
POS = {"GK": "G", "GKP": "G", "DEF": "D", "MID": "M", "FWD": "F"}
PRICE_BANDS = pd.IntervalIndex.from_breaks([0, 5.0, 7.0, 10.0, 99], closed="left")
THRESHOLDS = {"P(<=2)": lambda x: x <= 2, "P(>=10)": lambda x: x >= 10, "P(>=15)": lambda x: x >= 15}
TRAIN, TEST, CHECK = "2023-24", "2024-25", "2025-26"
SUPPORT = np.arange(-10, 61)  # points support for the log score

# Pass criteria for the held-out season, fixed before it was run (B07b "Done when")
PASS_CRITERIA = """\
On the held-out season (2024-25), with 90% bootstrap bands over GWs:
1. P(>=10) and P(>=15) inside the band for every position (G, D, M, F).
2. Top 10 xP each GW: mean simulated points within 0.2 of mean xP, and P(<=2) inside the band.
3. Team-mate correlation inside the band for defence (G/D pairs); attackers reported too.
4. Compared with the empirical benchmark on log score, CRPS, hauls and correlations; if the engine
   does not beat it, the benchmark is the one to use for now."""


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
    pg["recent"] = per_fixture.groupby(pg["fpl_id"]).transform(lambda m: m.shift(1).rolling(4, min_periods=1).mean()).fillna(0)
    pg["price"] = pg["value"] / 10
    pg["xmins"] = projected_minutes(pg, season) * pg["n_fix"]
    return pg, fixtures


# Projected minutes for calibration. vaastav has no projected minutes, and recent minutes alone miss team
# news (players with xP 0 are flagged out and play only 7-21% of the time). So xMins = average minutes per
# fixture in the TRAINING season for the same keeper/outfield x xP band x recent-minutes band: information
# available before the deadline, like a projection's xMins. Fitted on 2023-24 only and reused unchanged.
MIN_XP_BANDS = [-0.01, 0, 0.5, 1, 1.5, 2, 3, 99]
MIN_RECENT_BANDS = [-0.01, 0, 30, 60, 80, 91]
_MINUTES_MODEL: dict = {}


def _minutes_keys(pg: pd.DataFrame) -> pd.MultiIndex:
    xp = pd.cut(pg["xpts"] / pg["n_fix"], MIN_XP_BANDS, labels=False)
    rec = pd.cut(pg["recent"], MIN_RECENT_BANDS, labels=False)
    return pd.MultiIndex.from_arrays([pg["pos"].eq("G"), xp, rec], names=["keeper", "xp", "recent"])


def projected_minutes(pg: pd.DataFrame, season: str) -> pd.Series:
    """Expected minutes per fixture for each player-GW, from the training season's table (see above)."""
    if "table" not in _MINUTES_MODEL:
        train = pg if season == TRAIN else season_inputs(TRAIN)[0]
        train = train[train["gw"].isin(gws_with_xp(train)) & (train["n_fix"] == 1)]
        per_fixture = pd.Series(train["minutes"].to_numpy(float), index=_minutes_keys(train))
        _MINUTES_MODEL["table"] = per_fixture.groupby(level=[0, 1, 2]).mean()
    table = _MINUTES_MODEL["table"]
    keys = _minutes_keys(pg)
    out = pd.Series(table.reindex(keys).to_numpy(), index=pg.index)
    # unseen cells: the recent minutes themselves
    return out.fillna(pg["recent"])


def gws_with_xp(pg: pd.DataFrame, first: int = 5) -> list[int]:
    """GWs where vaastav's xP is populated (it is stored as 0 elsewhere), from GW `first` (needs minutes history)."""
    mean_xp = pg.groupby("gw")["xpts"].mean()
    return [int(gw) for gw, x in mean_xp.items() if x > 0 and gw >= first]


def _scores(sim: np.ndarray, actual: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per-column log score (-log P(actual), add-0.5 smoothing over SUPPORT) and CRPS, from samples `sim` (S, n)."""
    s = sim.shape[0]
    clipped = np.clip(actual, SUPPORT[0], SUPPORT[-1])
    hits = (sim == clipped).sum(axis=0)
    log_score = -np.log((hits + 0.5) / (s + 0.5 * len(SUPPORT)))
    x = np.sort(sim, axis=0)
    i = np.arange(1, s + 1)[:, None]
    spread = (2 * ((2 * i - s - 1) * x).sum(axis=0)) / s**2  # E|X - X'|
    crps = np.abs(sim - actual).mean(axis=0) - spread / 2
    return log_score, crps


def _collect(proj: pd.DataFrame, sim: np.ndarray, keep: int) -> pd.DataFrame:
    frame = proj.set_index("fpl_id").reindex(player_index(proj)).reset_index()
    frame["sim_mean"] = sim.mean(axis=0)
    for name, test in THRESHOLDS.items():
        frame[f"sim {name}"] = test(sim).mean(axis=0)
    frame["log_score"], frame["crps"] = _scores(sim, frame["pts"].to_numpy(float))
    frame["draws"] = list(sim[:keep].T)
    return frame


def simulate_season(pg, fixtures, gws, rules: str, params: Params = DEFAULT_PARAMS, S: int = 2000, keep: int = 20) -> pd.DataFrame:  # noqa: N803
    """Engine: per player-GW actual points, simulated frequencies and mean, scores, and `keep` raw draws."""
    out = []
    for gw in gws:
        proj = pg[(pg["gw"] == gw) & (pg["recent"] > 0)]
        if not proj.empty:
            sim = simulate(proj, fixtures, S=S, H=1, seed=int(gw), rules=rules, params=params)[:, 0, :]
            out.append(_collect(proj, sim.astype(float), keep))
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------------------------------------
# Empirical benchmark
# ---------------------------------------------------------------------------------------------

XP_BANDS = [-0.01, 0.5, 1, 2, 3, 4, 5, 6, 8, 99]
XMIN_BANDS = [-0.01, 30, 60, 80, 999]


@dataclass
class Empirical:
    """Points drawn from the training season's actual points for the same position x xP band x xMins band."""

    pools: dict  # (pos, xp_band, xmin_band) -> sorted array of actual points
    rho: dict  # position group ("att" / "def") -> loading on the shared team factor

    def keys(self, frame: pd.DataFrame) -> list:
        xb = pd.cut(frame["xpts"] / frame["n_fix"], XP_BANDS, labels=False)
        mb = pd.cut(frame["xmins"] / frame["n_fix"], XMIN_BANDS, labels=False)
        return list(zip(frame["pos"], xb, mb, strict=True))

    def sample(self, frame: pd.DataFrame, S: int, rng) -> np.ndarray:  # noqa: N803
        """`frame`: one GW's player rows (with team_id, n_fix). Correlated through one normal per team."""
        teams = frame["team_id"].to_numpy()
        team_ids = np.unique(teams)
        z = rng.standard_normal((S, len(team_ids)))
        zt = z[:, np.searchsorted(team_ids, teams)]
        rho = np.where(frame["pos"].isin(["G", "D"]), self.rho["def"], self.rho["att"])
        u = norm.cdf(rho * zt + np.sqrt(1 - rho**2) * rng.standard_normal((S, len(frame))))
        out = np.zeros((S, len(frame)))
        for j, key in enumerate(self.keys(frame)):
            pool = self.pools.get(key)
            if pool is None:  # unseen cell: fall back to position x xP band
                pool = self.pools.get((*key[:2], None), np.array([0.0]))
            out[:, j] = pool[np.minimum((u[:, j] * len(pool)).astype(int), len(pool) - 1)]
        # doubles: add the same cell's draw again, independently
        doubles = frame["n_fix"].to_numpy() > 1
        if doubles.any():
            extra = self.sample(frame[doubles].assign(n_fix=1, xpts=frame["xpts"][doubles] / frame["n_fix"][doubles]), S, rng)
            out[:, doubles] += extra
        return out


def fit_empirical(pg: pd.DataFrame, gws) -> Empirical:
    train = pg[pg["gw"].isin(gws) & (pg["recent"] > 0) & (pg["n_fix"] == 1)]
    emp = Empirical(pools={}, rho={"att": 0.0, "def": 0.0})
    keys = emp.keys(train)
    pts = train["pts"].to_numpy(float)
    by_key = pd.Series(range(len(train))).groupby(pd.Index(keys))
    emp.pools = {k: np.sort(pts[idx.to_numpy()]) for k, idx in by_key}
    coarse = pd.Series(range(len(train))).groupby(pd.Index([(*k[:2], None) for k in keys]))
    emp.pools |= {k: np.sort(pts[idx.to_numpy()]) for k, idx in coarse}
    # Gaussian-copula loadings: rho^2 ~ team-mates' residual correlation on the training season
    res = train.assign(r=train["pts"] - train["xpts"])
    for group, positions in (("att", {"M", "F"}), ("def", {"G", "D"})):
        p = res[res["pos"].isin(positions) & (res["xmins"] >= 60)]
        pairs = p.merge(p, on=["gw", "team_id"])
        pairs = pairs[pairs["fpl_id_x"] < pairs["fpl_id_y"]]
        emp.rho[group] = float(np.sqrt(max(np.corrcoef(pairs["r_x"], pairs["r_y"])[0, 1], 0)))
    return emp


def empirical_season(emp: Empirical, pg, gws, S: int = 2000, keep: int = 20) -> pd.DataFrame:  # noqa: N803
    out = []
    for gw in gws:
        proj = pg[(pg["gw"] == gw) & (pg["recent"] > 0)].sort_values("fpl_id")
        if not proj.empty:
            sim = np.rint(emp.sample(proj, S, np.random.default_rng(int(gw))))
            out.append(_collect(proj, sim, keep))
    return pd.concat(out, ignore_index=True)


# ---------------------------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------------------------


def _cluster_bootstrap(df: pd.DataFrame, stat, reps: int = 400, seed: int = 0) -> tuple[float, float]:
    """90% band of `stat(df)` resampling whole GWs."""
    rng = np.random.default_rng(seed)
    by_gw = dict(tuple(df.groupby("gw")))
    keys = list(by_gw)
    vals = [stat(pd.concat([by_gw[k] for k in rng.choice(keys, len(keys))], ignore_index=True)) for _ in range(reps)]
    return tuple(np.nanquantile(vals, [0.05, 0.95]))


def top10(res: pd.DataFrame) -> pd.DataFrame:
    return res.sort_values("xpts", ascending=False).groupby("gw").head(10)


def frequency_table(res: pd.DataFrame) -> pd.DataFrame:
    """Actual vs simulated frequencies by group, with bootstrap bands and a pass flag."""
    res = res.assign(band=pd.cut(res["price"], PRICE_BANDS).astype(str))
    groups = [("all", res)]
    groups += [(f"pos {p}", res[res["pos"] == p]) for p in ["G", "D", "M", "F"]]
    groups += [(f"price {b}", g) for b, g in res.groupby("band")]
    groups.append(("top 10 xP per GW", top10(res)))
    rows = []
    for label, g in groups:
        row = {"group": label, "n": len(g), "mean xP": g["xpts"].mean(), "mean actual": g["pts"].mean(), "mean sim": g["sim_mean"].mean()}
        for name, test in THRESHOLDS.items():
            lo, hi = _cluster_bootstrap(g, lambda d, test=test: test(d["pts"]).mean())
            sim = g[f"sim {name}"].mean()
            row |= {
                f"{name} actual": test(g["pts"]).mean(),
                f"{name} band": f"{lo:.3f}-{hi:.3f}",
                f"{name} sim": sim,
                f"{name} ok": lo <= sim <= hi,
            }
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


def match_from_results(res: pd.DataFrame) -> dict:
    report = res.assign(top10=res.index.isin(top10(res).index))
    return match_summary(report)


def summary(res: pd.DataFrame, freq: pd.DataFrame, corr: pd.DataFrame) -> dict:
    """The numbers the pass criteria and the scoreboard use."""
    pos = freq[freq["group"].str.startswith("pos ")]
    t10 = freq[freq["group"] == "top 10 xP per GW"].iloc[0]
    m = match_from_results(res)
    return {
        "log score": res["log_score"].mean(),
        "CRPS": res["crps"].mean(),
        "hauls ok (pos x 10+/15+)": f"{int(pos['P(>=10) ok'].sum() + pos['P(>=15) ok'].sum())}/8",
        "top10 mean gap": t10["mean sim"] - t10["mean xP"],
        "top10 P(<=2) ok": bool(t10["P(<=2) ok"]),
        "defence corr ok": bool(corr.iloc[1]["ok"]),
        "attack corr ok": bool(corr.iloc[0]["ok"]),
        "share |mean - xP| > 0.2": m["share_off"],
    }


def passes(s: dict) -> bool:
    return s["hauls ok (pos x 10+/15+)"] == "8/8" and abs(s["top10 mean gap"]) <= 0.2 and s["top10 P(<=2) ok"] and s["defence corr ok"]


def _fmt(df: pd.DataFrame) -> str:
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == float:
            out[c] = out[c].map("{:.3f}".format) if c.startswith("P(") or c in ("actual", "sim") else out[c].map("{:.2f}".format)
    return out.to_markdown(index=False)


def evaluate(season: str, params: Params = DEFAULT_PARAMS, emp: Empirical | None = None, S: int = 2000) -> dict:  # noqa: N803
    pg, fixtures = season_inputs(season)
    gws = gws_with_xp(pg)
    out = {"season": season, "gws": gws}
    res = simulate_season(pg, fixtures, gws, rules=season, params=params, S=S)
    out["engine"] = (res, frequency_table(res), correlation_table(res, fixtures))
    if emp is not None:
        eres = empirical_season(emp, pg, gws, S=S)
        out["empirical"] = (eres, frequency_table(eres), correlation_table(eres, fixtures))
    return out


def write_report(path=REPORT_PATH, params: Params = DEFAULT_PARAMS, S: int = 2000) -> str:  # noqa: N803
    pg_train, _ = season_inputs(TRAIN)
    emp = fit_empirical(pg_train, gws_with_xp(pg_train))
    runs = [evaluate(s, params, emp, S) for s in (TRAIN, TEST, CHECK)]
    board = []
    for run in runs:
        for model in ("engine", "empirical"):
            s = summary(*run[model])
            board.append({"season": run["season"], "model": model, **s, "passes criteria": passes(s)})
    board = pd.DataFrame(board)
    sections = []
    for run, role in zip(runs, ("training (tuned here)", "held out (test)", "final check"), strict=True):
        res, freq, corr = run["engine"]
        _, efreq, ecorr = run["empirical"]
        sections.append(
            f"""## {run["season"]}: {role}

GWs: {", ".join(map(str, run["gws"]))}; {len(res):,} player-GWs; {S:,} scenarios per GW.

### Engine: frequencies

{_fmt(freq)}

### Engine: correlation of (points - xP)

{_fmt(corr)}

### Empirical benchmark: frequencies

{_fmt(efreq)}

### Empirical benchmark: correlation of (points - xP)

{_fmt(ecorr)}
"""
        )
    constants = "\n".join(f"| `{k}` | {v} |" for k, v in params.__dict__.items() if k != "fitted")
    rules_text = ", ".join(f"{k}: DC {'on' if r.defensive_contributions else 'off'}, team goals {r.team_goals}" for k, r in RULES.items())
    text = f"""# Scenario engine calibration (out of sample)

Generated by `uv run python -m fplrank.sim.calibration`. Engine: `fplrank.sim.scenarios.simulate`;
benchmark: `fplrank.sim.calibration.Empirical`. Both fitted on {TRAIN} only.

**Inputs.** Projection = vaastav `xP` (FPL's expected points; well calibrated where present: mean xP
vs points 1.05/1.09 in 2023-24, 1.18/1.22 in 2024-25, 1.19/1.20 in 2025-26). It is stored as 0 in
GWs where FPL did not publish it, so only GWs with xP are used (from GW5, for minutes history).
xMins = average minutes per fixture over the previous 4 GWs (vaastav has no projected minutes).

## Pass criteria (fixed before the held-out season was run)

{PASS_CRITERIA}

## Scoreboard

Lower log score and CRPS are better.

{_fmt(board)}

## Constants

Every tunable constant (`fplrank.sim.scenarios.Params`; fitted values say where they come from in
the code). Rules per season: {rules_text}.
Empirical benchmark copula loadings (from {TRAIN}): attack {emp.rho["att"]:.3f}, defence {emp.rho["def"]:.3f}.

| constant | value |
|---|---|
{constants}

{"".join(sections)}"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


if __name__ == "__main__":
    print(write_report(*sys.argv[1:1]))
