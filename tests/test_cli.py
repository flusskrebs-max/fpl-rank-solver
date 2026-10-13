"""`fplrank solve`: his flags pass through; --eo/--target/--lam add the λ choice. Offline, on the saved GW6 payloads."""

import gzip
import json
import pickle
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
    load_eo = lambda group, bootstrap, gw, projections, templates=None: (eo, f"{group} test")  # noqa: E731
    assert cli.solve([*HIS_FLAGS, "--eo", "AE64", "--target", "10000", "--points", "300"], request_fn, load_eo) == 0
    out = capsys.readouterr().out
    assert "EO AE64 test; λ in full on GW6, then x0.7 a GW" in out
    assert "P by λ:" in out and "P(top 10,000)" in out
    assert "--- Sertalp's solver, plan for λ = " in out
    assert out.count("Result") == 1  # only the chosen plan's output is shown


@pytest.mark.slow
def test_sims_run_his_simulations_at_the_fixed_lambda(request_fn, capsys):
    ids = [e["id"] for e in request_fn(cli.BOOTSTRAP)["elements"]]
    eo = pd.Series(1.5, index=ids[:40])
    load_eo = lambda group, bootstrap, gw, projections, templates=None: (eo, f"{group} test")  # noqa: E731
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


def test_payloads_fetched_once_are_replayed_in_workers():
    calls = []
    rec = cli.Recorder(lambda url: calls.append(url) or {"url": url})
    assert rec("a") == rec("a") == {"url": "a"} and calls == ["a"]
    replay = pickle.loads(pickle.dumps(rec.replay()))  # what a worker process gets
    assert replay("a") == {"url": "a"}
    with pytest.raises(KeyError):
        replay("b")  # a test's request function is not sent along; the live one is (below)
    live = cli.LiveRequest(cache={"bootstrap-static/": {"x": 1}}, api=object())
    copy = pickle.loads(pickle.dumps(live))
    assert copy.api is None and copy("https://fantasy.premierleague.com/api/bootstrap-static/") == {"x": 1}
    assert cli.Recorder(live).replay().fallback is live


def test_adjust_is_lambda_on_his_projections_and_picklable():
    from fplrank.opt import ownership

    proj = pd.DataFrame({"ID": [1, 2], "6_Pts": [5.0, 4.0], "7_Pts": [5.0, 4.0]})
    eo = pd.Series({1: 1.5, 2: 0.2})
    adjust = pickle.loads(pickle.dumps(cli.Adjust(eo, 0.1, 6, 0.7)))
    pd.testing.assert_frame_equal(adjust(proj, {}), ownership.adjust_projections(proj, eo, 0.1, 6, 0.7))


def test_one_worker_runs_in_this_process():
    pool = cli.executor(1, 9)
    assert isinstance(pool, cli.InlineExecutor) and pool.submit(lambda x: x + 1, 1).result() == 2
    assert isinstance(cli.executor(4, 1), cli.InlineExecutor)  # one job: no pool to start


@pytest.mark.slow
def test_workers_give_the_same_plans_as_one_at_a_time(request_fn, monkeypatch):
    from fplrank.opt import ownership

    ids = [e["id"] for e in request_fn(cli.BOOTSTRAP)["elements"]]
    eo = pd.Series(1.5, index=ids[:40])
    load_eo = lambda group, bootstrap, gw, projections, templates=None: (eo, f"{group} test")  # noqa: E731
    plans = {}
    score = ownership.score_plan

    def keep(sol, *a, **k):
        plans.setdefault(workers, []).append(sol["picks"])
        return score(sol, *a, **k)

    monkeypatch.setattr(ownership, "score_plan", keep)
    for workers in (1, 2):
        cli.solve([*HIS_FLAGS, "--eo", "AE64", "--lam", "0.1", "--workers", str(workers)], request_fn, load_eo)
    assert len(plans[1]) == len(plans[2]) == 2
    for a, b in zip(plans[1], plans[2], strict=True):
        pd.testing.assert_frame_equal(a.reset_index(drop=True), b.reset_index(drop=True))
