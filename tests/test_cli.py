"""`fplrank solve`: his flags pass through; --eo/--target/--lam add the λ choice. Offline, on the saved GW6 payloads."""

import gzip
import json
from pathlib import Path

import pandas as pd
import pytest

from fplrank import cli
from fplrank.data.projections import from_ep_next
from fplrank.paths import UPSTREAM_DIR

FIXTURE = Path(__file__).parent / "fixtures" / "gw6_live"
# preseason: empty squad and a wildcard, so no team data is needed; horizon 1 keeps it quick
HIS_FLAGS = ["--datasource", "fplrank", "--preseason", "true", "--use_wc", "[6]", "--horizon", "1", "--secs", "60", "--xmin_lb", "0"]


@pytest.fixture(scope="module")
def request_fn():
    with gzip.open(FIXTURE / "bootstrap-static.json.gz", "rt", encoding="utf-8") as f:
        bootstrap = json.load(f)
    with gzip.open(FIXTURE / "fixtures.json.gz", "rt", encoding="utf-8") as f:
        fixtures = json.load(f)
    from_ep_next(bootstrap, fixtures, horizon=1).to_csv(UPSTREAM_DIR / "data" / "fplrank.csv", index=False, encoding="utf-8")
    payloads = {cli.BOOTSTRAP: bootstrap, "https://fantasy.premierleague.com/api/fixtures/": fixtures}
    return lambda url: payloads[url]


def test_eo_alone_is_refused():
    with pytest.raises(SystemExit):
        cli.solve(["--eo", "AE64"], request=lambda url: {})


@pytest.mark.slow
def test_no_extras_is_just_his_solver(request_fn, capsys):
    assert cli.solve(HIS_FLAGS, request=request_fn) == 0
    out = capsys.readouterr().out
    assert "Result" in out and "λ" not in out


@pytest.mark.slow
def test_target_picks_a_lambda_and_prints_his_plan(request_fn, capsys, monkeypatch):
    from fplrank.rank import target

    # the line comes from collected data on Alex's PC; CI has none
    monkeypatch.setattr(target, "target_line", lambda rank: target.TargetLine(rank, 5, 398, 55, 398 + 33 * 55, 40, ("test",)))
    monkeypatch.setattr(target, "season_drift", lambda rank, group: target.SeasonDrift(rank, group, 2.5, 0.5, ("a", "b")))
    ids = [e["id"] for e in request_fn(cli.BOOTSTRAP)["elements"]]
    eo = pd.Series(1.5, index=ids[:40])
    load_eo = lambda group, bootstrap, gw, projections: (eo, f"{group} test")  # noqa: E731
    assert cli.solve([*HIS_FLAGS, "--eo", "AE64", "--target", "10000", "--points", "300"], request_fn, load_eo) == 0
    out = capsys.readouterr().out
    assert "EO AE64 test; λ on GW6 only" in out
    assert "P by λ:" in out and "P(top 10,000)" in out
    assert "--- Sertalp's solver, plan for λ = " in out
    assert out.count("Result") == 1  # only the chosen plan's output is shown


@pytest.mark.slow
def test_sims_run_his_simulations_at_the_fixed_lambda(request_fn, capsys):
    ids = [e["id"] for e in request_fn(cli.BOOTSTRAP)["elements"]]
    eo = pd.Series(1.5, index=ids[:40])
    load_eo = lambda group, bootstrap, gw, projections: (eo, f"{group} test")  # noqa: E731
    assert cli.solve([*HIS_FLAGS, "--eo", "AE64", "--lam", "0.1", "--sims", "2"], request_fn, load_eo) == 0
    out = capsys.readouterr().out
    assert "--- Sertalp's simulations: 2 runs ---" in out
    assert "Processing for GW 6 with wildcard." in out  # his sensitivity summary (preseason wildcard)
    assert "Number of plans: 2" in out and "Goalkeepers:" in out


@pytest.mark.slow
def test_lambda_flips_the_captain_to_the_field_pick(request_fn):
    """λ through his own solve: a captain slightly worse on xP but heavily captained by the field wins at λ = 0.1."""
    from fplrank.opt import ownership

    def captain(sol):
        rows = sol["picks"][sol["picks"]["week"] == 6]
        return int(rows.loc[rows["captain"] == 1, "id"].iloc[0])

    base = cli.run(HIS_FLAGS, request=request_fn, quiet=True).solution
    rows = base["picks"][base["picks"]["week"] == 6]
    cap = captain(base)
    other = int(rows[(rows["lineup"] == 1) & (rows["captain"] == 0)].sort_values("xP")["id"].iloc[-1])
    eo = pd.Series({cap: 0.3, other: 1.6})

    def solve(lam):
        def adjust(proj, _):
            proj = proj.copy()
            top = proj["6_Pts"].max() + 1  # make the EV captain clear, the field's pick 0.2 behind
            proj.loc[proj["ID"] == cap, "6_Pts"] = top
            proj.loc[proj["ID"] == other, "6_Pts"] = top - 0.2
            return ownership.adjust_projections(proj, eo, lam, 6)

        return cli.run(HIS_FLAGS, adjust, request_fn, quiet=True).solution

    assert captain(solve(0.0)) == cap
    assert captain(solve(0.1)) == other
