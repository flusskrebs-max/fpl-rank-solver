from unittest.mock import MagicMock

from fplrank.data.fpl_api import FplApi, latest_snapshot


def test_get_saves_snapshot_and_latest_loads_it(tmp_path):
    session = MagicMock()
    session.headers = {}
    session.get.return_value.json.return_value = {"events": [{"id": 7, "is_next": True}]}
    api = FplApi(snapshot_dir=tmp_path, session=session)

    payload = api.bootstrap()

    session.get.assert_called_once_with("https://fantasy.premierleague.com/api/bootstrap-static/", timeout=30)
    assert payload["events"][0]["id"] == 7
    assert latest_snapshot("bootstrap-static/", snapshot_dir=tmp_path) == payload
