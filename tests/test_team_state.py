from unittest.mock import MagicMock

import pytest

from fplrank.data import team_state as ts
from fplrank.data.fpl_api import FplApi, latest_snapshot

BOOTSTRAP = {"elements": [{"id": 1, "element_type": 1}, {"id": 2, "element_type": 3}]}
MY_TEAM = {
    "picks": [{"element": 1, "selling_price": 45, "purchase_price": 45}, {"element": 2, "selling_price": 101, "purchase_price": 100}],
    "chips": [{"name": "wildcard", "status_for_entry": "available"}],
    "transfers": {"bank": 12, "limit": 2, "made": 0},
}
ESTIMATE = {"picks": [{"element": 1, "selling_price": 45}], "chips": [], "transfers": {"bank": 10, "limit": 1, "made": 0}}


def request(url):
    assert url.endswith("bootstrap-static/")
    return BOOTSTRAP


def api_returning(tmp_path, status=200, payload=MY_TEAM):
    session = MagicMock()
    session.headers = {}
    session.get.return_value.status_code = status
    session.get.return_value.json.return_value = payload
    return FplApi(snapshot_dir=tmp_path, session=session)


@pytest.fixture
def estimate(monkeypatch):
    monkeypatch.setattr(ts, "public_team_state", lambda team_id, request: {**ESTIMATE, "team_id": team_id})


def test_env_file_parsing(tmp_path):
    f = tmp_path / ".env"
    f.write_text('# comment\nFPL_EMAIL="a@b.c"\nexport FPL_PASSWORD=p=w\n\nOTHER=1\n')
    assert ts.credentials(env={}, env_file=f) == {"FPL_EMAIL": "a@b.c", "FPL_PASSWORD": "p=w"}
    assert ts.credentials(env={"FPL_EMAIL": "env@x"}, env_file=f)["FPL_EMAIL"] == "env@x"
    assert ts.credentials(env={}, env_file=tmp_path / "missing") == {}


def test_no_credentials_falls_back_with_warning(tmp_path, estimate):
    with pytest.warns(UserWarning, match="public data for team 7"):
        state = ts.load_team_state(7, request, api_returning(tmp_path), creds={})
    assert state["source"] == "public-estimate"
    assert state["transfers"]["limit"] == 1


def test_token_reads_my_team_and_snapshots_it(tmp_path, estimate):
    api = api_returning(tmp_path)
    state = ts.load_team_state(7, request, api, creds={"FPL_ACCESS_TOKEN": "tok"})

    url = api.session.get.call_args.args[0]
    assert url == "https://fantasy.premierleague.com/api/my-team/7/"
    assert api.session.get.call_args.kwargs["headers"] == {"X-API-Authorization": "Bearer tok"}
    assert state["source"] == "my-team"
    assert state["transfers"] == {"bank": 12, "limit": 2, "made": 0}
    assert [p["element_type"] for p in state["picks"]] == [1, 3]
    assert "tok" not in str(latest_snapshot("my-team/7/", snapshot_dir=tmp_path))


def test_email_login_is_preferred(tmp_path, estimate):
    calls = []

    def fake_login(email, password):
        calls.append(email)
        return "fresh"

    api = api_returning(tmp_path)
    creds = {"FPL_EMAIL": "a@b.c", "FPL_PASSWORD": "pw", "FPL_ACCESS_TOKEN": "old"}
    ts.load_team_state(7, request, api, creds=creds, login_fn=fake_login)
    assert calls == ["a@b.c"]
    assert api.session.get.call_args.kwargs["headers"]["X-API-Authorization"] == "Bearer fresh"


def test_failed_login_falls_back_without_leaking_secrets(tmp_path, estimate):
    def bad_login(email, password):
        raise ts.LoginError("sign-on was rejected (check FPL_EMAIL / FPL_PASSWORD)")

    with pytest.warns(UserWarning) as record:
        creds = {"FPL_EMAIL": "me@x", "FPL_PASSWORD": "hunter2"}
        state = ts.load_team_state(7, request, api_returning(tmp_path), creds=creds, login_fn=bad_login)
    assert state["source"] == "public-estimate"
    message = str(record[0].message)
    assert "rejected" in message and "hunter2" not in message and "me@x" not in message


def test_refused_token_falls_back(tmp_path, estimate):
    with pytest.warns(UserWarning, match="HTTP 403"):
        state = ts.load_team_state(7, request, api_returning(tmp_path, status=403), creds={"FPL_ACCESS_TOKEN": "expired"})
    assert state["source"] == "public-estimate"
