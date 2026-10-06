"""Scenario engine ([A] in docs/research/solver-design.md; briefs B07, B07b).

`simulate(projections, fixtures, S, H, seed, rules=...)` returns integer FPL points, `array[S, H, players]`,
for the first H GWs of `projections`, correlated within teams and fixtures, with each player's mean
matched to his projection where possible.

Per player and fixture (a double GW is two fixtures, a blank none):

- **Minutes**: 0 / 1-59 / 60+ with probabilities read from an empirical table by projected xMins
  (`Params.minutes_table`). Minutes come only from xMins; mean matching never changes them.
- **Team goals**: one Poisson draw per team per fixture. A team's goals for are its opponent's goals
  against, so attackers rise together and defenders share clean sheets and goals conceded exactly.
  Expected goals: the season's goals per team per match (`Rules.team_goals`, taken from the
  previous season) times each team's attack index, the projected points of its midfielders and
  forwards in that fixture relative to the average.
- **Events**: each team goal is the player's (or his assist) with probability rate x minutes share /
  expected team goals; with probability `shared_weight` the draw uses his team's actual goals,
  otherwise an independent draw of the same size. Clean sheet (60+ and nothing conceded), goals
  conceded (-1 per 2, GK/DEF on 60+), saves (GK, more against stronger attacks), defensive
  contributions (when the season's rules have them; likelier the more the opponent scores), cards,
  and bonus 3/2/1 to the top three of a BPS-like score per fixture.
- **Matching means**: each player-fixture's attacking rate is fitted so the simulated mean equals the
  projection, capped by the share of his team's goals and assists he can take
  (`max_goal_share`, `max_assist_share`). Where the cap binds the mean stays below the projection;
  where non-attacking points alone exceed it the mean stays above. `match_report` reports both.

Every tunable constant is in `Params`, with where it was fitted.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

POSITIONS = ["G", "D", "M", "F"]
GOAL_PTS = np.array([10, 6, 5, 4])  # by position index (keepers never score in the engine)
CS_PTS = np.array([4, 4, 1, 0])
GC_APPLIES = np.array([True, True, False, False])
ATTACK_GOAL_SHARE = np.array([0.0, 1.0, 1.0, 1.0])  # keepers: assists only
BPS_GOAL = np.array([12, 12, 18, 24])


@dataclass(frozen=True)
class Rules:
    """Scoring rules and scoring environment of a season."""

    defensive_contributions: bool
    team_goals: float  # goals per team per match: the PREVIOUS season's actual, so tests stay out of sample


RULES = {
    "2023-24": Rules(defensive_contributions=False, team_goals=1.639),  # training season: its own value
    "2024-25": Rules(defensive_contributions=False, team_goals=1.639),  # from 2023-24
    "2025-26": Rules(defensive_contributions=True, team_goals=1.467),  # from 2024-25
    "2026-27": Rules(defensive_contributions=True, team_goals=1.375),  # from 2025-26
}


@dataclass(frozen=True)
class Params:
    """Every tunable constant, with where it was fitted (vaastav merged_gw unless said otherwise)."""

    # Minutes: P(0) and P(1-59) by xMins (expected minutes per fixture). Fitted on 2023-24 against the
    # calibration's projected minutes (training-season average minutes for the same keeper/outfield x xP band
    # x recent-minutes band; see fplrank.sim.calibration.projected_minutes). xMins 0 means "out": P(0) = 1.
    minutes_table: tuple = (  # outfield players; the 90 point is judgement (only 32 cases above 85)
        (4.6, 19.1, 38.7, 61.5, 76.2, 82.5, 90),  # xMins
        (0.859, 0.498, 0.228, 0.117, 0.050, 0.024, 0.020),  # P(0)
        (0.100, 0.350, 0.418, 0.231, 0.102, 0.055, 0.030),  # P(1-59)
    )
    keeper_minutes_table: tuple = (  # keepers: almost never part of a game
        (18.4, 43.4, 62.8, 74.3, 83.5, 87.9),
        (0.806, 0.535, 0.291, 0.174, 0.056, 0.017),
        (0.028, 0.028, 0.047, 0.000, 0.032, 0.009),
    )
    mins_sub: float = 21.9  # average minutes in 1-59 appearances (2023-24)
    mins_full: float = 85.5  # average minutes in 60+ appearances (2023-24)
    assist_per_goal: tuple = (0.0, 1.49, 0.968, 0.447)  # by position, 60+ appearances (2023-24)
    yellow_prob: tuple = (0.077, 0.175, 0.184, 0.120)  # per 60+ appearance (2023-24)
    red_prob: float = 0.004  # (2023-24)
    saves_per_game: float = 3.28  # keepers, 60+ (2023-24)
    dc_prob: tuple = (0.0, 0.27, 0.179, 0.012)  # defensive contribution per 60+ appearance (2025-26, the only season with them)
    # Relative change in DC chance per goal conceded. Fitted on the 2025-26 GWs without xP (so outside the
    # final check): D -0.02, M -0.04 per goal, i.e. no relationship, so 0 ("busy defenders" not supported)
    dc_per_goal_against: float = 0.0
    lambda_range: tuple = (0.6, 3.0)  # expected team goals per match (judgement)
    max_goal_share: float = 0.6  # of his team's goals (brief: top players take 50-60% of involvements)
    max_assist_share: float = 0.5
    keeper_max_assist_share: float = 0.01  # keepers assist ~0.3% of games (2023-24): not a lever for their projection
    shared_weight: float = 0.85  # tuned on 2023-24: 0.7 gave attacker correlation 0.055, 1.0 gave 0.123, actual 0.099
    bps_noise: float = 6.0  # sd of the BPS-like score's noise; tuned on 2023-24
    fitted: dict = field(default_factory=dict, compare=False)  # notes from the latest tuning run


DEFAULT_PARAMS = Params()


def minutes_states(xmins, params: Params = DEFAULT_PARAMS, keeper=False) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """P(0), P(1-59), P(60+) for one fixture, interpolated from the outfield or keeper minutes table."""
    x = np.clip(np.asarray(xmins, float), 0, 90)
    keeper = np.broadcast_to(np.asarray(keeper, bool), x.shape)

    def read(table):
        grid, t0, t1 = (np.array(v, float) for v in table)
        return np.interp(x, grid, t0), np.interp(x, grid, t1)

    (o0, o1), (k0, k1) = read(params.minutes_table), read(params.keeper_minutes_table)
    p0, p1 = np.where(keeper, k0, o0), np.where(keeper, k1, o1)
    out = x <= 0
    p0, p1 = np.where(out, 1.0, p0), np.where(out, 0.0, p1)
    return p0, p1, 1 - p0 - p1


@dataclass
class Slots:
    """One row per player per fixture in one GW."""

    player: np.ndarray  # index into the players axis
    pos: np.ndarray  # 0-3
    fixture: np.ndarray  # index into the GW's fixtures
    side: np.ndarray  # team-side index (2 per fixture: home 2f, away 2f+1)
    opp_side: np.ndarray
    xpts: np.ndarray
    p1: np.ndarray
    p2: np.ndarray
    lam: np.ndarray  # expected team goals per side (length 2 * fixtures)


def _gw_slots(proj_gw: pd.DataFrame, fix_gw: pd.DataFrame, players: pd.Index, rules: Rules, params: Params) -> Slots | None:
    if fix_gw.empty:
        return None
    fix_gw = fix_gw.reset_index(drop=True)
    idx = fix_gw.index
    sides = pd.concat(
        [
            pd.DataFrame({"team_id": fix_gw["team_h"], "fixture": idx, "side": 2 * idx, "opp_side": 2 * idx + 1}),
            pd.DataFrame({"team_id": fix_gw["team_a"], "fixture": idx, "side": 2 * idx + 1, "opp_side": 2 * idx}),
        ]
    )
    rows = proj_gw.merge(sides, on="team_id")
    if rows.empty:
        return None
    n_fix = rows.groupby("fpl_id")["fixture"].transform("size")
    rows["xpts_f"] = rows["xpts"] / n_fix
    rows["xmins_f"] = rows["xmins"] / n_fix
    rows["pos_i"] = rows["pos"].map({p: i for i, p in enumerate(POSITIONS)})
    attack = rows[rows["pos_i"] >= 2].groupby("side")["xpts_f"].sum().reindex(range(2 * len(fix_gw)), fill_value=0)
    lam = rules.team_goals * (attack / attack.mean() if attack.mean() > 0 else 1.0)
    _, p1, p2 = minutes_states(rows["xmins_f"], params, keeper=rows["pos_i"].to_numpy() == 0)
    return Slots(
        player=players.get_indexer(rows["fpl_id"]),
        pos=rows["pos_i"].to_numpy(),
        fixture=rows["fixture"].to_numpy(),
        side=rows["side"].to_numpy(),
        opp_side=rows["opp_side"].to_numpy(),
        xpts=rows["xpts_f"].to_numpy(float),
        p1=np.asarray(p1, float),
        p2=np.asarray(p2, float),
        lam=np.clip(np.broadcast_to(np.asarray(lam, float), (2 * len(fix_gw),)), *params.lambda_range).copy(),
    )


def _simulate_slots(sl: Slots, rate, s: int, rng: np.random.Generator, rules: Rules, params: Params, detail: bool = False):
    """Points per slot, shape (s, slots), for attacking rates `rate` (goals per 90 at his team's expected scoring)."""
    n = len(sl.pos)
    pos = sl.pos
    goals_side = rng.poisson(sl.lam, size=(s, len(sl.lam)))
    g_for, g_against = goals_side[:, sl.side], goals_side[:, sl.opp_side]
    lam_for, lam_against = sl.lam[sl.side], sl.lam[sl.opp_side]
    u = rng.random((s, n))
    full = u < sl.p2
    sub = ~full & (u < sl.p2 + sl.p1)
    played = full | sub
    full_share = params.mins_full / 90
    share = full * full_share + sub * (params.mins_sub / 90)
    per_team_goal = share / lam_for

    def team_goals():
        return np.where(rng.random((s, n)) < params.shared_weight, g_for, rng.poisson(lam_for, size=(s, n)))

    apg = np.array(params.assist_per_goal)
    goals = rng.binomial(team_goals(), np.clip(rate * ATTACK_GOAL_SHARE[pos] * per_team_goal, 0, params.max_goal_share))
    assist_rate = rate * np.where(pos == 0, 1.0, apg[pos])
    assist_cap = np.where(pos == 0, params.keeper_max_assist_share, params.max_assist_share)
    assists = rng.binomial(team_goals(), np.clip(assist_rate * per_team_goal, 0, assist_cap))
    gk_def = GC_APPLIES[pos]
    clean = full & (g_against == 0)
    conceded = np.where(full & gk_def, g_against // 2, 0)
    saves = np.where(played & (pos == 0), rng.poisson(params.saves_per_game * share / full_share * lam_against / lam_against.mean()), 0)
    if rules.defensive_contributions:
        pressure = 1 + params.dc_per_goal_against * (g_against - lam_against)
        dc = played & (rng.random((s, n)) < np.clip(np.array(params.dc_prob)[pos] * share / full_share * pressure, 0, 1))
    else:
        dc = np.zeros((s, n), dtype=bool)
    yellow = played & (rng.random((s, n)) < np.array(params.yellow_prob)[pos] * share / full_share)
    red = played & (rng.random((s, n)) < params.red_prob * share / full_share)

    bps = (
        6 * full
        + 3 * sub
        + BPS_GOAL[pos] * goals
        + 9 * assists
        + 12 * (clean & gk_def)
        + 2 * saves
        + 5 * dc  # clearances, blocks, interceptions and tackles score BPS too
        - 4 * np.where(full & gk_def, g_against, 0)
        - 3 * yellow
        + rng.normal(0, params.bps_noise, (s, n))
    )
    bps = np.where(played, bps, -np.inf)
    bonus = np.zeros((s, n), dtype=np.int16)
    rows = np.arange(s)
    for f in np.unique(sl.fixture):
        idx = np.flatnonzero(sl.fixture == f)
        top = np.argsort(-bps[:, idx], axis=1)[:, :3]
        for rank, pts in enumerate((3, 2, 1)):
            if rank < len(idx):
                cols = idx[top[:, rank]]
                ok = np.isfinite(bps[rows, cols])
                bonus[rows[ok], cols[ok]] = pts

    points = (
        2 * full
        + 1 * sub
        + GOAL_PTS[pos] * goals
        + 3 * assists
        + CS_PTS[pos] * clean
        - conceded
        + saves // 3
        + 2 * dc
        + bonus
        - yellow
        - 3 * red
    )
    if detail:  # components, for diagnostics and tests
        parts = {"full": full, "sub": sub, "goals": goals, "assists": assists, "clean": clean, "dc": dc, "bonus": bonus, "saves": saves}
        return points.astype(np.int16), parts
    return points.astype(np.int16)


def _rate_cap(sl: Slots, params: Params) -> np.ndarray:
    """Highest attacking rate before a full-match player takes `max_goal_share` / `max_assist_share` of his team's goals."""
    lam_for = sl.lam[sl.side]
    full_share = params.mins_full / 90
    apg = np.where(sl.pos == 0, 1.0, np.array(params.assist_per_goal)[sl.pos])
    goal_cap = np.where(sl.pos == 0, np.inf, params.max_goal_share * lam_for / full_share)
    assist_share = np.where(sl.pos == 0, params.keeper_max_assist_share, params.max_assist_share)
    return np.minimum(goal_cap, assist_share * lam_for / (apg * full_share))


def _fit_rates(sl: Slots, rng: np.random.Generator, rules: Rules, params: Params, s: int = 4000, iterations: int = 6) -> np.ndarray:
    """Attacking rate per slot so the simulated mean matches the projection, within `_rate_cap`. Minutes are never changed."""
    apg = np.where(sl.pos == 0, 1.0, np.array(params.assist_per_goal)[sl.pos])
    exp_share = (sl.p2 * params.mins_full + sl.p1 * params.mins_sub) / 90
    per_unit = np.maximum(exp_share * (GOAL_PTS[sl.pos] * ATTACK_GOAL_SHARE[sl.pos] + 3.6 * apg + 0.6), 1e-6)
    can_attack = exp_share > 0.01
    cap = _rate_cap(sl, params)
    rate = np.zeros(len(sl.pos))
    for _ in range(iterations):
        mean = _simulate_slots(sl, rate, s, rng, rules, params).mean(axis=0)
        rate = np.where(can_attack, np.clip(rate + (sl.xpts - mean) / per_unit, 0.0, cap), 0.0)
    return rate


def player_index(projections: pd.DataFrame) -> pd.Index:
    """The players axis of `simulate`'s output: sorted fpl_ids."""
    return pd.Index(sorted(projections["fpl_id"].unique()), name="fpl_id")


def gws_of(projections: pd.DataFrame, H: int) -> list[int]:  # noqa: N803 (S, H as in the design doc)
    return sorted(projections["gw"].unique())[:H]


def simulate(
    projections: pd.DataFrame,
    fixtures: pd.DataFrame,
    S: int,  # noqa: N803 (S, H as in the design doc)
    H: int,  # noqa: N803
    seed: int = 0,
    rules: str | Rules = "2026-27",
    params: Params = DEFAULT_PARAMS,
    chunk: int = 2500,
) -> np.ndarray:
    """Simulated FPL points, int16 `array[S, H, players]`.

    `projections`: long table with `gw, fpl_id, pos (G/D/M/F), team_id, xmins, xpts` (e.g. `load_solio`
    plus `with_team_ids`). `fixtures`: `event, team_h, team_a` (FPL fixtures). `rules`: a season in
    `RULES` or a `Rules`. The GW axis is the first H GWs in `projections`; the players axis is
    `player_index(projections)`.
    """
    rules = RULES[rules] if isinstance(rules, str) else rules
    rng = np.random.default_rng(seed)
    players = player_index(projections)
    gws = gws_of(projections, H)
    out = np.zeros((S, len(gws), len(players)), dtype=np.int16)
    for h, gw in enumerate(gws):
        sl = _gw_slots(projections[projections["gw"] == gw], fixtures[fixtures["event"] == gw], players, rules, params)
        if sl is None:
            continue
        rate = _fit_rates(sl, rng, rules, params)
        # A player has at most one slot per fixture; add doubles occurrence by occurrence
        occurrence = pd.Series(sl.player).groupby(sl.player).cumcount().to_numpy()
        for start in range(0, S, chunk):
            pts = _simulate_slots(sl, rate, min(chunk, S - start), rng, rules, params)
            for occ in range(occurrence.max() + 1):
                sel = occurrence == occ
                out[start : start + pts.shape[0], h, sl.player[sel]] += pts[:, sel]
    return out


def with_team_ids(projections: pd.DataFrame, teams) -> pd.DataFrame:
    """Add `team_id` to projections whose `team` is a team name or short name (`teams`: FPL teams list or frame).

    Names are matched without City / Town / United / FC, since sources differ ("Leeds United" vs "Leeds").
    """
    teams = pd.DataFrame(teams)

    def norm(name):
        name = str(name).lower().strip()
        for suffix in (" city", " town", " united", " fc"):
            name = name.removesuffix(suffix)
        return name

    keys = [norm(n) for n in teams["name"]]
    if len(set(keys)) != len(keys):
        raise ValueError(f"Team names collide once normalised: {sorted(teams['name'])}")
    lookup = {**dict(zip(keys, teams["id"], strict=True)), **{s.lower(): i for s, i in zip(teams["short_name"], teams["id"], strict=True)}}
    out = projections.copy()
    out["team_id"] = out["team"].map(norm).map(lookup)
    if out["team_id"].isna().any():
        raise ValueError(f"Unknown teams: {sorted(out.loc[out['team_id'].isna(), 'team'].unique())}")
    return out.astype({"team_id": int})


def match_report(projections: pd.DataFrame, points: np.ndarray, H: int) -> pd.DataFrame:  # noqa: N803 (S, H as in the design doc)
    """Simulated vs projected mean per player and GW, with the Monte Carlo standard error and `top10` (top 10 xP that GW)."""
    players = player_index(projections)
    gws = gws_of(projections, H)
    rows = []
    for h, gw in enumerate(gws):
        p = projections[projections["gw"] == gw].set_index("fpl_id")
        sim = points[:, h, :].astype(float)
        frame = pd.DataFrame({"gw": gw, "fpl_id": players, "sim_mean": sim.mean(axis=0), "se": sim.std(axis=0) / np.sqrt(len(sim))})
        frame["xpts"] = p["xpts"].reindex(players).to_numpy()
        frame["top10"] = frame["xpts"].rank(ascending=False, method="first") <= 10
        rows.append(frame)
    return pd.concat(rows, ignore_index=True)


def match_summary(report: pd.DataFrame, tolerance: float = 0.2) -> dict:
    """Share of player-GWs whose simulated mean misses the projection by more than `tolerance`, overall and top 10 by xP."""
    live = report[report["xpts"] > 0]
    miss = (live["sim_mean"] - live["xpts"]).abs() > tolerance
    top = live[live["top10"]]
    return {
        "share_off": float(miss.mean()),
        "share_off_top10": float(miss[live["top10"]].mean()) if len(top) else float("nan"),
        "top10_mean_gap": float((top["sim_mean"] - top["xpts"]).mean()) if len(top) else float("nan"),
    }
