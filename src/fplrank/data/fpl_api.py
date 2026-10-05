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
STAMP_FORMAT = "%Y%m%dT%H%M%SZ"


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
        stamp = datetime.now(UTC).strftime(STAMP_FORMAT)
        path = snapshot_folder(endpoint, self.snapshot_dir) / f"{stamp}.json"
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


def snapshot_folder(endpoint: str, snapshot_dir: Path = SNAPSHOT_DIR) -> Path:
    """Folder holding `endpoint`'s snapshots. Query strings are made safe for Windows file names."""
    name = endpoint.strip("/").replace("/", "__").replace("?", "__").replace("&", "__").replace("=", "-")
    return snapshot_dir / (name or "root")


def latest_snapshot_path(endpoint: str, snapshot_dir: Path = SNAPSHOT_DIR) -> Path | None:
    """Path of the most recent snapshot for `endpoint`, or None if there is none."""
    files = sorted(snapshot_folder(endpoint, snapshot_dir).glob("*.json"))
    return files[-1] if files else None


def snapshot_time(path: Path) -> datetime:
    """UTC time a snapshot was saved, from its file name."""
    return datetime.strptime(path.stem, STAMP_FORMAT).replace(tzinfo=UTC)


def latest_snapshot(endpoint: str, snapshot_dir: Path = SNAPSHOT_DIR) -> dict | list:
    """Load the most recent saved snapshot for `endpoint`."""
    path = latest_snapshot_path(endpoint, snapshot_dir)
    if path is None:
        raise FileNotFoundError(f"No snapshots saved for {endpoint!r} in {snapshot_folder(endpoint, snapshot_dir)}")
    return json.loads(path.read_text())
