"""Scenario engine v0 ([A] in docs/research/solver-design.md, brief B07).

`simulate(projections, fixtures, S, H, seed)` returns integer FPL points, `array[S, H, players]`, for
the first H GWs of `projections`, correlated within teams and fixtures and matching each player's
projected mean.

Per player and fixture (a double GW is two fixtures, a blank none):

- **Minutes**: 0 / 1-59 / 60+ from projected xMins (`minutes_states`).
- **Team goals**: one Poisson draw per team per fixture. A team's goals for are its opponent's goals
  against, so attackers rise together and defenders share clean sheets and goals conceded. Expected
  goals come from the projections themselves: each team's attack index is the projected points of
  its midfielders and forwards in that fixture, relative to the average.
- **Events**: each team goal is the player's (or his assist) with probability rate x minutes share /
  expected team goals, so nobody outscores his team;
  clean sheet (60+ and nothing conceded); goals conceded (-1 per 2, GK/DEF on 60+); saves (GK);
  defensive contributions, yellow and red cards (2025-26 rates per position); bonus 3/2/1 to the
  top three of a BPS-like score per fixture. Scored with the 2025-26 rules.
- **Matching means**: each player-fixture's attacking rate is tuned (a few short simulations) so the
  simulated mean equals the projected points. Where a player's non-attacking points alone already
  exceed the projection (rate 0), the mean stays above it; `match_report` says how often.

Base rates come from 2025-26 actuals (vaastav merged_gw, 60+ minute appearances).
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

POSITIONS = ["G", "D", "M", "F"]
GOAL_PTS = np.array([10, 6, 5, 4])  # by position index (2025-26 rules)
CS_PTS = np.array([4, 4, 1, 0])
GC_APPLIES = np.array([True, True, False, False])
ASSIST_PER_GOAL = np.array([0.0, 1.7, 1.06, 0.33])  # assists per goal, 2025-26
ATTACK_GOAL_SHARE = np.array([0.0, 1.0, 1.0, 1.0])  # keepers: assists only
DC_PROB = np.array([0.0, 0.27, 0.179, 0.012])  # defensive contribution (2 pts), per 60+ appearance
YELLOW_PROB = np.array([0.073, 0.163, 0.159, 0.111])
RED_PROB = 0.003
SAVES_PER_GAME = 2.78
BPS_GOAL = np.array([12, 12, 18, 24])
BASE_TEAM_GOALS = 1.375
MINS_SUB, MINS_FULL = 22, 85  # average minutes in the 1-59 and 60+ states
LAMBDA_RANGE = (0.6, 3.0)  # expected team goals per match
MAX_GOAL_SHARE, MAX_ASSIST_SHARE = 0.5, 0.4  # of his team's goals (Haaland-level is ~0.4)
SHARED_WEIGHT = 0.7  # chance a player's goal/assist draw uses his team's goals rather than an independent draw (fitted to 2025-26)


def minutes_states(xmins) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """P(0), P(1-59), P(60+) from projected minutes for one fixture.

    P(plays) = min(1, xMins / 70); given that he plays, P(60+) rises linearly from 0 at 22 average
    minutes to 1 at 85. The expected minutes then roughly equal xMins.
    """
    x = np.clip(np.asarray(xmins, float), 0, 90)
    p_play = np.minimum(1.0, x / 70)
    cond = np.divide(x, p_play, out=np.zeros_like(x), where=p_play > 0)
    p_full = p_play * np.clip((cond - MINS_SUB) / (MINS_FULL - MINS_SUB), 0, 1)
    return 1 - p_play, p_play - p_full, p_full


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


def _gw_slots(proj_gw: pd.DataFrame, fix_gw: pd.DataFrame, players: pd.Index) -> Slots | None:
    if fix_gw.empty:
        return None
    fix_gw = fix_gw.reset_index(drop=True)
    sides = pd.concat(
        [
            pd.DataFrame(
                {"team_id": fix_gw["team_h"], "fixture": fix_gw.index, "side": 2 * fix_gw.index, "opp_side": 2 * fix_gw.index + 1}
            ),
            pd.DataFrame(
                {"team_id": fix_gw["team_a"], "fixture": fix_gw.index, "side": 2 * fix_gw.index + 1, "opp_side": 2 * fix_gw.index}
            ),
        ]
    )
    rows = proj_gw.merge(sides, on="team_id")
    if rows.empty:
        return None
    n_fix = rows.groupby("fpl_id")["fixture"].transform("size")
    rows["xpts_f"] = rows["xpts"] / n_fix
    rows["xmins_f"] = rows["xmins"] / n_fix
    rows["pos_i"] = rows["pos"].map({p: i for i, p in enumerate(POSITIONS)})
    # Expected team goals per side from the attack index of the team's midfielders and forwards
    attack = rows[rows["pos_i"] >= 2].groupby("side")["xpts_f"].sum().reindex(range(2 * len(fix_gw)), fill_value=0)
    lam = BASE_TEAM_GOALS * attack / attack.mean() if attack.mean() > 0 else pd.Series(BASE_TEAM_GOALS, index=attack.index)
    _, p1, p2 = minutes_states(rows["xmins_f"])
    return Slots(
        player=players.get_indexer(rows["fpl_id"]),
        pos=rows["pos_i"].to_numpy(),
        fixture=rows["fixture"].to_numpy(),
        side=rows["side"].to_numpy(),
        opp_side=rows["opp_side"].to_numpy(),
        xpts=rows["xpts_f"].to_numpy(float),
        p1=p1,
        p2=p2,
        lam=np.clip(lam.to_numpy(float), *LAMBDA_RANGE),
    )


def _simulate_slots(sl: Slots, rate: np.ndarray, s: int, rng: np.random.Generator, detail: bool = False):
    """Points per slot, shape (s, slots), for attacking rates `rate` (expected goals per 90 at average team scoring)."""
    n = len(sl.pos)
    goals_side = rng.poisson(sl.lam, size=(s, len(sl.lam)))
    g_for, g_against = goals_side[:, sl.side], goals_side[:, sl.opp_side]
    u = rng.random((s, n))
    full = u < sl.p2
    sub = ~full & (u < sl.p2 + sl.p1)
    played = full | sub
    share = full * (MINS_FULL / 90) + sub * (MINS_SUB / 90)
    # Each team goal is his with probability (his expected goals / team's expected goals), so he never
    # outscores his team and his mean is rate x minutes share
    # Shared with team-mates with probability SHARED_WEIGHT, otherwise an independent draw of the same
    # size: keeps each player's mean and distribution, weakens team-mate and goal-assist links to observed levels
    lam_for = sl.lam[sl.side]
    per_team_goal = share / lam_for

    def team_goals():
        return np.where(rng.random((s, n)) < SHARED_WEIGHT, g_for, rng.poisson(lam_for, size=(s, n)))

    goals = rng.binomial(team_goals(), np.clip(rate * ATTACK_GOAL_SHARE[sl.pos] * per_team_goal, 0, MAX_GOAL_SHARE))
    assist_rate = rate * np.where(sl.pos == 0, 1.0, ASSIST_PER_GOAL[sl.pos])
    assists = rng.binomial(team_goals(), np.clip(assist_rate * per_team_goal, 0, MAX_ASSIST_SHARE))
    gk_def = GC_APPLIES[sl.pos]
    clean = full & (g_against == 0)
    conceded = np.where(full & gk_def, g_against // 2, 0)
    saves = np.where(played & (sl.pos == 0), rng.poisson(SAVES_PER_GAME * share / (MINS_FULL / 90)), 0)
    dc = rng.random((s, n)) < DC_PROB[sl.pos] * share / (MINS_FULL / 90)
    yellow = played & (rng.random((s, n)) < YELLOW_PROB[sl.pos] * share / (MINS_FULL / 90))
    red = played & (rng.random((s, n)) < RED_PROB * share)

    bps = (
        6 * full
        + 3 * sub
        + BPS_GOAL[sl.pos] * goals
        + 9 * assists
        + 12 * (clean & gk_def)
        + 2 * saves
        + 5 * dc  # clearances, blocks, interceptions and tackles score BPS too
        - 4 * np.where(full & gk_def, g_against, 0)
        - 3 * yellow
        + rng.normal(0, 6, (s, n))
    )
    bps = np.where(played, bps, -np.inf)
    bonus = np.zeros((s, n), dtype=np.int16)
    for f in np.unique(sl.fixture):
        idx = np.flatnonzero(sl.fixture == f)
        top = np.argsort(-bps[:, idx], axis=1)[:, :3]
        for rank, pts in enumerate((3, 2, 1)):
            if rank < len(idx):
                cols = idx[top[:, rank]]
                ok = np.isfinite(bps[np.arange(s), cols])
                bonus[np.arange(s)[ok], cols[ok]] = pts

    points = (
        2 * full
        + 1 * sub
        + GOAL_PTS[sl.pos] * goals
        + 3 * assists
        + CS_PTS[sl.pos] * clean
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


MAX_RATE = np.array([0.15, 0.3, 0.8, 1.1])  # goals per 90 by position (keepers: assists) at average team scoring; scaled by fixture


def _fit_rates(sl: Slots, rng: np.random.Generator, s: int = 4000, iterations: int = 8) -> np.ndarray:
    """Attacking rate per slot so the simulated mean matches the projection.

    Rates stay in [0, MAX_RATE by position], and the chance of playing absorbs what the rate can't (modifies
    `sl.p1`, `sl.p2`): if a player's points without attacking returns already exceed his projection,
    he plays less (rotation risk); if even the maximum rate falls short (typically a projection with
    almost no minutes but some points), he plays more rather than scoring absurdly when he does.
    """
    points_per_goal = GOAL_PTS[sl.pos] * ATTACK_GOAL_SHARE[sl.pos] + (3 + 0.6) * np.where(sl.pos == 0, 1.0, ASSIST_PER_GOAL[sl.pos]) + 0.6
    blank = (sl.p1 + sl.p2 == 0) & (sl.xpts > 0.05)
    sl.p1[blank] = 0.01  # projected points but no minutes: give him a chance to come on
    rate = np.zeros(len(sl.pos))
    for _ in range(iterations):
        mean = _simulate_slots(sl, rate, s, rng).mean(axis=0)
        per_unit = np.maximum((sl.p2 * MINS_FULL + sl.p1 * MINS_SUB) / 90 * points_per_goal, 1e-6)
        cap = MAX_RATE[sl.pos] * sl.lam[sl.side] / BASE_TEAM_GOALS  # better fixtures allow more
        rate = np.clip(rate + (sl.xpts - mean) / per_unit, 0.0, cap)
        over = (rate == 0) & (mean > sl.xpts) & (mean > 0)
        under = (rate == cap) & (mean < sl.xpts) & (mean > 0)
        scale = np.ones(len(sl.pos))
        scale[over] = np.clip(sl.xpts[over] / mean[over], 0.2, 1.0)
        scale[under] = np.clip(sl.xpts[under] / mean[under], 1.0, 4.0)
        total = (sl.p1 + sl.p2) * scale
        scale = np.divide(scale, total, out=scale, where=total > 1)  # never above certain to play
        sl.p1 *= scale
        sl.p2 *= scale
    return rate


def player_index(projections: pd.DataFrame) -> pd.Index:
    """The players axis of `simulate`'s output: sorted fpl_ids."""
    return pd.Index(sorted(projections["fpl_id"].unique()), name="fpl_id")


def gws_of(projections: pd.DataFrame, H: int) -> list[int]:  # noqa: N803 (S, H as in the design doc)
    return sorted(projections["gw"].unique())[:H]


def simulate(projections: pd.DataFrame, fixtures: pd.DataFrame, S: int, H: int, seed: int = 0, chunk: int = 2500) -> np.ndarray:  # noqa: N803 (S, H as in the design doc)
    """Simulated FPL points, int16 `array[S, H, players]`.

    `projections`: long table with `gw, fpl_id, pos (G/D/M/F), team_id, xmins, xpts` (e.g. `load_solio`
    plus `with_team_ids`). `fixtures`: `event, team_h, team_a` (FPL fixtures). The GW axis is the first H
    GWs in `projections`; the players axis is `player_index(projections)`.
    """
    rng = np.random.default_rng(seed)
    players = player_index(projections)
    gws = gws_of(projections, H)
    out = np.zeros((S, len(gws), len(players)), dtype=np.int16)
    for h, gw in enumerate(gws):
        sl = _gw_slots(projections[projections["gw"] == gw], fixtures[fixtures["event"] == gw], players)
        if sl is None:
            continue
        rate = _fit_rates(sl, rng)
        # A player has at most one slot per fixture; add doubles occurrence by occurrence
        occurrence = pd.Series(sl.player).groupby(sl.player).cumcount().to_numpy()
        for start in range(0, S, chunk):
            pts = _simulate_slots(sl, rate, min(chunk, S - start), rng)
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
    """Simulated vs projected mean per player and GW, with the Monte Carlo standard error."""
    players = player_index(projections)
    gws = gws_of(projections, H)
    rows = []
    for h, gw in enumerate(gws):
        p = projections[projections["gw"] == gw].set_index("fpl_id")
        sim = points[:, h, :].astype(float)
        frame = pd.DataFrame({"gw": gw, "fpl_id": players, "sim_mean": sim.mean(axis=0), "se": sim.std(axis=0) / np.sqrt(len(sim))})
        frame["xpts"] = p["xpts"].reindex(players).to_numpy()
        rows.append(frame)
    return pd.concat(rows, ignore_index=True)
