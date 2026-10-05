"""End-to-end offline check: historical data -> placeholder projections -> upstream HiGHS solve.

Run with:  uv run python scripts/smoke_baseline.py [--season 2026-27] [--horizon 4]

Solve 1 picks a squad from scratch (wildcard in the next GW). Solve 2 starts from that squad
with 1 free transfer and plans the following weeks. If both finish with a valid 15-man squad
the toolchain (data, upstream model, HiGHS) is working.
"""

import argparse
import time

from fplrank.baseline import solve_ev
from fplrank.data import historical, offline


def previous_season(season: str) -> str:
    start = int(season[:4]) - 1
    return f"{start}-{str(start + 1)[-2:]}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", default="2026-27")
    parser.add_argument("--horizon", type=int, default=4)
    parser.add_argument("--secs", type=int, default=120)
    args = parser.parse_args()

    players = historical.players_raw(args.season)
    teams = historical.teams(args.season)
    fixtures_df = historical.fixtures(args.season)
    prior = historical.players_raw(previous_season(args.season))

    unfinished = fixtures_df[(~fixtures_df["finished"].astype(bool)) & fixtures_df["event"].notna()]
    next_gw = int(unfinished["event"].min())
    gws = list(range(next_gw, min(38, next_gw + args.horizon - 1) + 1))
    print(f"Season {args.season}: next GW is {next_gw}; projecting GWs {gws[0]}-{gws[-1]}")

    bootstrap = offline.build_bootstrap(players, teams, next_gw)
    fixtures = offline.build_fixtures(fixtures_df)
    projections = offline.placeholder_projections(players, teams, fixtures, gws, games_played=next_gw - 1, prior_season=prior)

    common = {"secs": args.secs, "xmin_lb": 0, "ev_per_price_cutoff": 0, "keep_top_ev_percent": 100}

    t0 = time.time()
    first = solve_ev(
        offline.preseason_team(),
        projections,
        bootstrap,
        fixtures,
        {**common, "preseason": True, "horizon": 1, "use_wc": [next_gw]},
    )[0]
    print(f"\nSolve 1 (squad from scratch, GW{next_gw}) in {time.time() - t0:.1f}s\n{first['summary']}")

    squad = first["picks"][(first["picks"]["week"] == next_gw) & (first["picks"]["squad"] == 1)]
    prices = {e["id"]: e["now_cost"] for e in bootstrap["elements"]}
    spent = sum(prices[int(i)] for i in squad["id"]) / 10
    my_data = offline.team_from_picks(first["picks"], next_gw, bank=100 - spent, prices=prices)

    # pretend that squad has been owned since before the next GW and plan from there
    t0 = time.time()
    second = solve_ev(my_data, projections, bootstrap, fixtures, {**common, "horizon": args.horizon})[0]
    print(f"\nSolve 2 ({args.horizon}-GW plan from that squad, 1 FT) in {time.time() - t0:.1f}s\n{second['summary']}")
    print(f"\nObjective: {second['score']:.2f}   Total xP over horizon: {second['total_xp']:.2f}")


if __name__ == "__main__":
    main()
