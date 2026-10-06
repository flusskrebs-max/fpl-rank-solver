"""R1/R2 weekly report: rendering from S1/S2c results and noisy re-solves, and offline runs on a saved real team."""

from datetime import UTC, datetime

import pandas as pd
import pytest

from fplrank import weekly


def _sol(captain_id, ev, buy="-", sell="-"):
    rows = [
        {
            "id": pid,
            "week": 6,
            "name": f"p{pid}",
            "lineup": int(pid != 3),
            "bench": 0 if pid == 3 else -1,
            "captain": int(pid == captain_id),
            "multiplier": (1 + int(pid == captain_id)) * int(pid != 3),
        }
        for pid in (1, 2, 3)
    ]
    picks = pd.DataFrame(rows)
    return {"picks": picks, "buy": buy, "sell": sell, "chip": "-", "captain": f"p{captain_id}", "ev": ev, "ev_next": ev / 5}


def _solutions():
    return {-0.1: _sol(2, 98.0, "p9", "p2"), 0.0: _sol(1, 100.0), 0.1: _sol(1, 100.0), 0.2: _sol(2, 99.0)}


NOW = datetime(2026, 10, 6, 12, tzinfo=UTC)


def test_render_without_target_recommends_the_ev_plan():
    text = weekly.render(6, 123, "Projections: x.", pd.DataFrame({"lams": ["0, 0.1"], "ev": [100.0]}), _solutions(), now=NOW)
    assert text.startswith("# GW6 weekly report, team 123")
    assert "Recommended: λ = 0 (EV plan)" in text
    assert "no transfers · captain p1 · no chip" in text
    assert "XI: p1 (C), p2. Bench: p3." in text
    assert "| lams | ev |" in text


def test_render_with_target_shows_choice_ev_plan_and_distinct_alternatives():
    sols = _solutions()
    rank = pd.DataFrame({"lam": [0.2, 0.1, 0.0, -0.1], "p": [0.30, 0.25, 0.25, 0.20], "ev": [99.0, 100.0, 100.0, 98.0]})
    text = weekly.render(6, 123, "", pd.DataFrame({"lams": ["0"]}), sols, (rank, "Top 10,000 line 400", 10000, 0.3), now=NOW)
    assert "## Recommended: λ = 0.2" in text
    assert "P(top 10,000) 30% vs 25% for the EV plan; EV cost 1.0" in text
    assert "## EV plan (λ = 0)" in text
    # λ = 0.1 and 0 are the same plan, so the alternatives are that plan and λ = -0.1
    alts = text.split("## Nearest alternatives")[1].split("## All plans")[0]
    assert "| 0.1 | 25% |" in alts and "| -0.1 | 20% | 2.0 | p2 | p9 | p2 |" in alts
    assert "| 0 |" not in alts


def _inputs(**kw):
    return weekly.Inputs(gw=6, team_id=1, my_data={}, bootstrap={}, fixtures=[], projections=pd.DataFrame(), eo=pd.Series(), **kw)


def test_run_checks_mode_and_goal_before_solving():
    with pytest.raises(ValueError, match="runs"):
        weekly.run(_inputs(), mode="simulate", runs=0)
    with pytest.raises(ValueError, match="mode"):
        weekly.run(_inputs(), mode="best")
    with pytest.raises(ValueError, match="points"):
        weekly.run(_inputs(target=10000))


def test_render_stability_counts_moves_captain_and_chip_against_the_recommendation():
    sims = pd.DataFrame(
        {
            "seed": [1, 2, 3, 4],
            "moves": ["no transfers", "in p9; out p2", "no transfers", "no transfers"],
            "captain": ["p1", "p1", "p2", "p1"],
            "chip": ["no chip"] * 4,
            "ev": [100.0, 98.0, 99.0, 100.0],
        }
    )
    text = weekly.render_stability(sims, 0.1, _sol(1, 100.0))
    assert text.startswith("## Stability: 4 noisy solves at λ = 0.1")
    assert "recommended moves came out on top in 3 of 4 runs, its captain in 3, its chip choice in 4." in text
    moves = text.split("### Moves")[1].split("### Captain")[0]
    assert "| no transfers (recommended) | 3 | 75% | 99.7 |" in moves and "| in p9; out p2 | 1 | 25% | 98.0 |" in moves
    assert "| p2 | 1 | 25% | 99.0 |" in text.split("### Captain")[1]


def test_simulate_passes_seeded_noise_to_each_solve(monkeypatch):
    calls = []

    def fake_solve(my_data, projections, eo, lam, bootstrap, fixtures, options, lam_gw):
        calls.append((lam, lam_gw, options))
        return _sol(1 + options["randomization_seed"] % 2, 100.0)

    monkeypatch.setattr(weekly.ow, "solve_with_ownership", fake_solve)
    sims = weekly.simulate(_inputs(), 0.2, 3, {"horizon": 3, "secs": 5}, 6, noise=0.5)
    assert list(sims["seed"]) == [1, 2, 3] and list(sims["captain"]) == ["p2", "p1", "p2"]
    assert all(c[0] == 0.2 and c[1] == 6 for c in calls)
    assert [c[2]["randomization_seed"] for c in calls] == [1, 2, 3]
    assert all(c[2]["randomized"] and c[2]["randomization_strength"] == 0.5 and c[2]["secs"] == 5 for c in calls)


@pytest.mark.slow
def test_weekly_report_offline_on_a_real_team():
    from test_opt_ownership import _gw6

    from fplrank.data.projections import from_ep_next

    my_data, bootstrap, fixtures = _gw6()
    proj = from_ep_next(bootstrap, fixtures, horizon=3)
    eo = pd.Series({e["id"]: 1.5 for e in bootstrap["elements"][:40]})
    inputs = weekly.Inputs(6, 1, my_data, bootstrap, fixtures, proj, eo, points=400, rank=12345, sources="EO: test.", ep_next=True)
    text = weekly.run(inputs, horizon=3, secs=120, lams=(0.0, 0.2), options={"gap": 0})
    assert text.count("XI:") == 1 and "## Recommended: λ = 0 (EV plan)" in text
    assert "Now: 400 points, overall rank 12,345; no rank goal. EO: test. Horizon 3 GWs, λ on GW6 only." in text
    assert text.splitlines()[2].startswith("Made") and "> **WARNING: no Solio file" in text


@pytest.mark.slow
def test_weekly_simulate_offline_on_a_real_team():
    from test_opt_ownership import _gw6

    from fplrank.data.projections import from_ep_next

    my_data, bootstrap, fixtures = _gw6()
    proj = from_ep_next(bootstrap, fixtures, horizon=2)
    eo = pd.Series({e["id"]: 1.5 for e in bootstrap["elements"][:40]})
    inputs = weekly.Inputs(6, 1, my_data, bootstrap, fixtures, proj, eo, points=400)
    text = weekly.run(inputs, "simulate", horizon=2, secs=60, lams=(0.0,), options={"gap": 0}, runs=2, sim_secs=60)
    assert "## Recommended: λ = 0 (EV plan)" in text and "## Stability: 2 noisy solves at λ = 0" in text
    assert "### Moves" in text and "### Captain" in text and "### Chip" in text
