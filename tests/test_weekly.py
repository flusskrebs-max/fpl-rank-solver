"""R1 weekly report: rendering from S1/S2c results, and an offline run on a saved real team."""

from datetime import UTC, datetime

import pandas as pd
import pytest

from fplrank import weekly
from fplrank.opt import ownership as ow


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


@pytest.mark.slow
def test_weekly_report_offline_on_a_real_team():
    from test_opt_ownership import _gw6

    from fplrank.data.projections import from_ep_next

    my_data, bootstrap, fixtures = _gw6()
    proj = from_ep_next(bootstrap, fixtures, horizon=3)
    eo = pd.Series({e["id"]: 1.5 for e in bootstrap["elements"][:40]})
    table, sols = ow.sweep(my_data, proj, eo, bootstrap, fixtures, (0.0, 0.2), {"horizon": 3, "secs": 120, "gap": 0})
    text = weekly.render(6, 1, "Projections: ep_next.", table, sols)
    assert "## Recommended: λ = 0 (EV plan)" in text and text.count("XI:") == 1
