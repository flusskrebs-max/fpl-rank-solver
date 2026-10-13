"""The page's weekly setup: Solio files told apart by their columns and put where they are read, the team saved."""

import gzip
import json
import os
import time
from datetime import date
from pathlib import Path

import pytest

from fplrank.ui import setup

PROJ = "Pos,ID,Name,BV,SV,Team,8_xMins,9_xMins,8_Pts,9_Pts\nG,1,Keeper,4.5,4.5,Alpha FC,90,90,3.5,3.8\n"
TABLE = "Player,Team,EOTop10k\nHaaland,Man City,123.28%\nTypo,Man City,5%\n"
BOOTSTRAP = Path(__file__).parent / "fixtures" / "gw6_live" / "bootstrap-static.json.gz"
EO = "\ufeffName,Team,Price,Avg EO %,GW8 EO %,GW9 EO %\nSalah,LIV,14.5,80,90,70\n"


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(setup, "SOLIO_CSV", tmp_path / "up" / "solio.csv")
    monkeypatch.setattr(setup, "SOLIO_EO_DIR", tmp_path / "proj" / "solio_eo")
    monkeypatch.setattr(setup, "TEAM_JSON", tmp_path / "up" / "team.json")
    return tmp_path


def test_kinds():
    assert setup.csv_kind(PROJ.splitlines()[0]) == ("projections", [8, 9])
    assert setup.csv_kind(EO.splitlines()[0]) == ("eo", [8, 9])
    assert setup.csv_kind("Player,Team,EOTop10k,CTop10k") == ("eo table", [])
    assert setup.csv_kind("Player\tTeam\tEO") == ("eo table", [])
    assert setup.csv_kind("a,b,c") is None


def test_install(dirs):
    assert setup.install(PROJ.encode())[2] == setup.SOLIO_CSV
    assert setup.SOLIO_CSV.read_text() == PROJ
    kind, _, dest, _ = setup.install(EO.encode("utf-8"), today=date(2026, 10, 13))
    assert (kind, dest.name) == ("eo", "EO_GW08_20261013.csv")
    boot = json.loads(gzip.open(BOOTSTRAP).read())
    kind, gws, dest, note = setup.install(TABLE.encode("utf-8"), today=date(2026, 10, 13), bootstrap=boot)
    assert (kind, gws[0], gws[-1], dest.name) == ("eo table", 6, 38, "EO_GW06_20261013.csv")
    assert setup.file_kind(dest) == ("eo", gws)
    assert note == "not matched, left out: Typo (Man City)"
    with pytest.raises(ValueError):
        setup.install(b"x,y\n1,2\n")


def test_newest_downloads(tmp_path):
    (tmp_path / "projection (8).csv").write_text(PROJ)
    (tmp_path / "projection (9).csv").write_text(PROJ)
    (tmp_path / "solio_effective_ownership.csv").write_text(EO, encoding="utf-8")
    (tmp_path / "other.csv").write_text("a,b\n")
    (tmp_path / "top10k.csv").write_text(TABLE, encoding="utf-8")  # an EO table: the same slot as Solio's EO
    os.utime(tmp_path / "top10k.csv", (time.time() - 3600,) * 2)
    old = time.time() - 30 * 86400
    os.utime(tmp_path / "projection (8).csv", (old, old))
    found = setup.newest_downloads(tmp_path)
    assert {k: p.name for k, p in found.items()} == {"projections": "projection (9).csv", "eo": "solio_effective_ownership.csv"}
    assert setup.newest_downloads(tmp_path / "missing") == {}


def test_save_team(dirs):
    team = {"picks": [{"element": 1}] * 15, "transfers": {"bank": 12}}
    setup.save_team("\ufeff" + json.dumps(team) + "\n")
    assert not setup.TEAM_JSON.read_bytes().startswith(b"\xef\xbb\xbf")
    assert json.loads(setup.TEAM_JSON.read_text()) == team
    assert setup.team_summary(team) == "15 players, £1.2m in the bank"
    for bad in ("not json", '{"detail": "Not logged in"}'):
        with pytest.raises(ValueError):
            setup.save_team(bad)


def test_squads_status(tmp_path):
    import pandas as pd

    assert setup.squads_gw(tmp_path) == {}
    pd.DataFrame({"entry_id": [1, 1, 2, 3], "gw": [4, 5, 5, 4]}).to_parquet(tmp_path / "picks.parquet")
    pd.DataFrame({"set": ["AE64", "E64", "top10k", "other"], "entry_id": [1, 2, 3, 1]}).to_parquet(tmp_path / "members.parquet")
    gws = setup.squads_gw(tmp_path)
    assert gws == {"AE64": 5, "E64": 5, "top10k": 4}
    assert setup.squads_summary(gws, 6) == (True, "AE64 GW5, E64 GW5, top10k GW4. GW6 has started: get the squads before solving.")
    assert setup.squads_summary({"AE64": 6, "E64": 6}, 6) == (False, "All groups: GW6. Up to date.")
    assert setup.squads_summary({}, 6)[0]


def test_last_deadline(tmp_path):
    from datetime import UTC, datetime

    assert setup.last_deadline(tmp_path) is None
    folder = tmp_path / "bootstrap-static"
    folder.mkdir()
    events = [{"id": g, "deadline_time": f"2026-10-{d:02d}T10:00:00Z"} for g, d in ((6, 3), (7, 17))]
    (folder / "20261001T000000Z.json").write_text(json.dumps({"events": events}))
    assert setup.last_deadline(tmp_path, now=datetime(2026, 10, 13, tzinfo=UTC)) == 6
    assert setup.last_deadline(tmp_path, now=datetime(2026, 10, 1, tzinfo=UTC)) is None


def test_update_code_switches_back_to_main(tmp_path, monkeypatch):
    import subprocess

    def sh(*args, cwd):
        subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)

    origin, clone = tmp_path / "origin", tmp_path / "clone"
    sh("init", "-q", "--bare", "-b", "main", str(origin), cwd=tmp_path)
    sh("clone", "-q", str(origin), str(clone), cwd=tmp_path)
    sh("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "one", cwd=clone)
    (clone / "f.txt").write_text("a")
    sh("add", "f.txt", cwd=clone)
    sh("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "on main", cwd=clone)
    sh("push", "-q", "origin", "main", cwd=clone)
    sh("reset", "-q", "--hard", "HEAD~1", cwd=clone)  # main is now one commit behind origin
    sh("checkout", "-q", "-b", "claude/x", cwd=clone)
    (clone / "g.txt").write_text("untracked, kept")
    monkeypatch.setattr(setup, "PROJECT_ROOT", clone)

    changed, out = setup.update_code()
    assert changed and 'Switched from branch "claude/x" to main.' in out
    assert setup.git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip() == "main"
    assert (clone / "f.txt").read_text() == "a" and (clone / "g.txt").exists()
