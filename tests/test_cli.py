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
    monkeypatch.setattr(target, "line_drift", lambda rank, group: (2.5, None))
    ids = [e["id"] for e in request_fn(cli.BOOTSTRAP)["elements"]]
    eo = pd.Series(1.5, index=ids[:40])
    load_eo = lambda group, bootstrap, gw: (eo, f"{group} test")  # noqa: E731
    assert cli.solve([*HIS_FLAGS, "--eo", "AE64", "--target", "10000", "--points", "300"], request_fn, load_eo) == 0
    out = capsys.readouterr().out
    assert "EO AE64 test; λ on GW6 only" in out
    assert "P by λ:" in out and "P(top 10,000)" in out
    assert "--- Sertalp's solver, plan for λ = " in out
    assert out.count("Result") == 1  # only the chosen plan's output is shown
