"""Thin client for the public FPL API that saves every response as a dated snapshot.

Snapshots matter for two reasons: the API only ever shows the present, so anything we do
not save is gone (prices, ownership, live EO); and solves should be reproducible from the
exact inputs they saw.

Note: the cloud sandbox Claude works in cannot reach fantasy.premierleague.com unless the
domain is allowed in network settings. Run this on your own machine otherwise.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import requests

from fplrank.paths import SNAPSHOT_DIR

BASE_URL = "https://fantasy.premierleague.com/api"
USER_AGENT = "fplrank/0.0.1 (personal research project)"


class FplApi:
    def __init__(self, snapshot_dir: Path = SNAPSHOT_DIR, session: requests.Session | None = None):
        self.snapshot_dir = snapshot_dir
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", USER_AGENT)

    def get(self, endpoint: str, save: bool = True) -> dict | list:
        """GET `endpoint` (e.g. "bootstrap-static/") and optionally save a timestamped copy."""
        response = self.session.get(f"{BASE_URL}/{endpoint.lstrip('/')}", timeout=30)
        response.raise_for_status()
        payload = response.json()
        if save:
            self._save(endpoint, payload)
        return payload

    def _save(self, endpoint: str, payload: dict | list) -> Path:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        name = endpoint.strip("/").replace("/", "__") or "root"
        path = self.snapshot_dir / name / f"{stamp}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
        return path

    # Convenience wrappers for the endpoints the project relies on
    def bootstrap(self) -> dict:
        return self.get("bootstrap-static/")

    def fixtures(self) -> list:
        return self.get("fixtures/")

    def live(self, gw: int) -> dict:
        return self.get(f"event/{gw}/live/")

    def entry_history(self, team_id: int) -> dict:
        return self.get(f"entry/{team_id}/history/")

    def entry_picks(self, team_id: int, gw: int) -> dict:
        return self.get(f"entry/{team_id}/event/{gw}/picks/")

    def overall_standings(self, page: int = 1) -> dict:
        """Overall league (id 314). 50 managers per page; used to sample managers near a target rank."""
        return self.get(f"leagues-classic/314/standings/?page_standings={page}")


def latest_snapshot(endpoint: str, snapshot_dir: Path = SNAPSHOT_DIR) -> dict | list:
    """Load the most recent saved snapshot for `endpoint`."""
    folder = snapshot_dir / (endpoint.strip("/").replace("/", "__") or "root")
    files = sorted(folder.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No snapshots saved for {endpoint!r} in {folder}")
    return json.loads(files[-1].read_text())
