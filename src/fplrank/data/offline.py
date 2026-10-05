"""Build FPL-API-shaped inputs from historical files so solves can run without network access.

Used for the offline smoke test and, later, for backtesting: given a season's data we can
reconstruct "what the API looked like" before a gameweek and run the solver against it.

`placeholder_projections` is NOT a projection model. It is a crude per-90 rate x expected
minutes x fixture difficulty heuristic that exists only so the pipeline has numbers to
chew on. Real work should use proper projections (Solio, FPL Review, Mikkel, or our own).
"""

import math

import numpy as np
import pandas as pd

ELEMENT_TYPES = [
    {"id": 1, "singular_name_short": "GKP", "squad_select": 2, "squad_min_play": 1, "squad_max_play": 1},
    {"id": 2, "singular_name_short": "DEF", "squad_select": 5, "squad_min_play": 3, "squad_max_play": 5},
    {"id": 3, "singular_name_short": "MID", "squad_select": 5, "squad_min_play": 2, "squad_max_play": 5},
    {"id": 4, "singular_name_short": "FWD", "squad_select": 3, "squad_min_play": 1, "squad_max_play": 3},
]
POS_LETTER = {1: "G", 2: "D", 3: "M", 4: "F"}
POS_MEAN_PER90 = {1: 3.6, 2: 3.6, 3: 4.3, 4: 4.3}
UNAVAILABLE_STATUSES = {"i", "s", "u", "n"}


def _clean(value):
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def build_bootstrap(players: pd.DataFrame, teams: pd.DataFrame, next_gw: int) -> dict:
    """Return a dict shaped like /api/bootstrap-static/ with `next_gw` marked as the next event."""
    events = [{"id": i, "is_next": i == next_gw, "is_current": i == next_gw - 1, "finished": i < next_gw} for i in range(1, 39)]
    return {
        "elements": [{k: _clean(v) for k, v in row.items()} for row in players.to_dict("records")],
        "teams": [{k: _clean(v) for k, v in row.items()} for row in teams.to_dict("records")],
        "element_types": ELEMENT_TYPES,
        "events": events,
    }


def build_fixtures(fixtures: pd.DataFrame) -> list[dict]:
    """Return a list shaped like /api/fixtures/."""
    cols = ["id", "event", "team_h", "team_a", "team_h_difficulty", "team_a_difficulty", "finished"]
    out = []
    for row in fixtures[cols].to_dict("records"):
        row = {k: _clean(v) for k, v in row.items()}
        if row["event"] is not None:
            row["event"] = int(row["event"])
        out.append(row)
    return out


def placeholder_projections(
    players: pd.DataFrame,
    teams: pd.DataFrame,
    fixtures: list[dict],
    gws: list[int],
    games_played: int,
    prior_season: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Crude projections in the upstream CSV format (ID, Name, Pos, Value, Team, {gw}_Pts, {gw}_xMins)."""
    team_name = teams.set_index("id")["name"].to_dict()
    prior = prior_season.set_index("code")[["total_points", "minutes"]] if prior_season is not None else None

    # fixture multipliers per (team, gw): easier opponent and home advantage push expected points up
    fixture_factor: dict[tuple[int, int], float] = {}
    for f in fixtures:
        if f["event"] not in gws:
            continue
        for team, difficulty, home_adv in ((f["team_h"], f["team_h_difficulty"], 1.05), (f["team_a"], f["team_a_difficulty"], 0.95)):
            key = (team, f["event"])
            fixture_factor[key] = fixture_factor.get(key, 0.0) + (1 + 0.08 * (3 - (difficulty or 3))) * home_adv

    rows = []
    for p in players.itertuples():
        current_share = min(1.0, p.minutes / (90 * max(games_played, 1)))
        prior_pts, prior_mins = (0.0, 0.0)
        if prior is not None and p.code in prior.index:
            prior_pts, prior_mins = (float(x) for x in prior.loc[p.code])
        share = 0.5 * current_share + 0.5 * min(1.0, prior_mins / (38 * 90)) if prior_mins > 0 else current_share

        if isinstance(p.chance_of_playing_next_round, float) and not math.isnan(p.chance_of_playing_next_round):
            availability = p.chance_of_playing_next_round / 100
        else:
            availability = 0.0 if p.status in UNAVAILABLE_STATUSES else 1.0

        # shrink last season's per-90 rate towards a positional mean
        per90 = (prior_pts + 5 * POS_MEAN_PER90[p.element_type]) / (prior_mins / 90 + 5)
        xmins = 90 * share * availability

        row = {"ID": p.id, "Name": p.web_name, "Pos": POS_LETTER[p.element_type], "Value": p.now_cost / 10, "Team": team_name[p.team]}
        for gw in gws:
            factor = fixture_factor.get((p.team, gw), 0.0)
            n_fixtures = sum(1 for f in fixtures if f["event"] == gw and p.team in (f["team_h"], f["team_a"]))
            row[f"{gw}_Pts"] = round(per90 * xmins / 90 * factor, 3)
            row[f"{gw}_xMins"] = round(xmins * n_fixtures, 1)
        rows.append(row)
    return pd.DataFrame(rows)


def preseason_team() -> dict:
    """my_data for a solve with no existing squad (upstream's `preseason` mode)."""
    return {"picks": [], "chips": [], "transfers": {"limit": None, "cost": 4, "bank": 1000, "value": 0}}


def team_from_picks(picks: pd.DataFrame, gw: int, bank: float, prices: dict[int, int], free_transfers: int = 1) -> dict:
    """Turn a solver result (picks DataFrame) for `gw` into my_data for the following solve.

    `prices` maps element id -> now_cost (in tenths, as the API reports it). Purchase and
    selling prices are both set to the current price, i.e. no price changes since buying.
    """
    squad = picks[(picks["week"] == gw) & (picks["squad"] == 1)]
    team_picks = []
    for row in squad.itertuples():
        price = int(prices[int(row.id)])
        team_picks.append({"element": int(row.id), "purchase_price": price, "selling_price": price, "element_type": int(row.type)})
    return {"picks": team_picks, "chips": [], "transfers": {"bank": round(bank * 10), "limit": free_transfers, "made": 0}}
