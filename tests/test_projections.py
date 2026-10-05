import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from fplrank.data import projections

FIXTURE = Path(__file__).parent / "fixtures" / "solio_tiny.csv"  # fake players, not real Solio data


def _write(path: Path, text: str, mtime: datetime | None = None) -> Path:
    path.write_text(text, encoding="utf-8")
    if mtime:
        os.utime(path, (mtime.timestamp(), mtime.timestamp()))
    return path


def _shifted(tmp_path, name, first_gw, mtime=None, tweak="") -> Path:
    """The fixture with its GW columns renumbered to start at `first_gw`."""
    header, *rows = FIXTURE.read_text(encoding="utf-8").splitlines()
    for old, new in zip((6, 7, 8), range(first_gw, first_gw + 3), strict=True):
        header = header.replace(f"{old}_", f"{new}_")
    return _write(tmp_path / name, "\n".join([header, *rows]) + "\n" + tweak, mtime)


def test_load_solio_long_shape():
    proj = projections.load_solio(FIXTURE)
    assert list(proj.columns) == projections.LONG_COLS
    assert len(proj) == 4 * 3
    assert (proj["vintage_gw"] == 6).all()
    row = proj[(proj["fpl_id"] == 4) & (proj["gw"] == 8)].iloc[0]
    assert (row["name"], row["team"], row["pos"], row["price"], row["xmins"], row["xpts"]) == ("Striker", "Beta United", "F", 10.0, 60, 4.0)


def test_load_solio_handles_byte_order_mark(tmp_path):
    bom = tmp_path / "bom.csv"
    bom.write_bytes(b"\xef\xbb\xbf" + FIXTURE.read_bytes())
    pd.testing.assert_frame_equal(projections.load_solio(bom), projections.load_solio(FIXTURE))


@pytest.mark.parametrize(
    "header",
    ["ID,Name,BV,SV,Team,6_xMins,6_Pts", "Pos,ID,Name,BV,SV,Team,6_xMins,7_xMins,6_Pts", "Pos,ID,Name,BV,SV,Team"],
)
def test_load_solio_rejects_malformed_files(tmp_path, header):
    with pytest.raises(ValueError):
        projections.load_solio(_write(tmp_path / "bad.csv", header + "\n"))


def test_register_copies_and_records(tmp_path):
    store = tmp_path / "projections"
    src = _shifted(tmp_path, "projection (8).csv", 6, datetime(2026, 10, 5, 13, 16))
    row = projections.register(src, projections_dir=store)
    assert row["file"] == "solio/GW06_20261005.csv"
    assert (store / row["file"]).read_bytes() == src.read_bytes()
    registry = projections.read_registry(store)
    assert list(registry.columns) == projections.REGISTRY_COLS
    rec = registry.iloc[0]
    assert (rec["original"], rec["vintage_gw"], rec["first_gw"], rec["last_gw"], rec["n_players"]) == ("projection (8).csv", 6, 6, 8, 4)
    assert rec["downloaded"] == "2026-10-05T13:16"


def test_register_skips_duplicates_and_separates_same_day_files(tmp_path):
    store = tmp_path / "projections"
    day = datetime(2026, 8, 20, 18, 0)
    a = _shifted(tmp_path, "a.csv", 1, day)
    b = _shifted(tmp_path, "b.csv", 1, day, tweak="G,5,Spare,4.0,4.0,Alpha FC,0,0,0,0,0,0\n")
    projections.register(a, projections_dir=store)
    projections.register(a, projections_dir=store)  # same content: no second copy
    row_b = projections.register(b, projections_dir=store)
    assert row_b["file"] == "solio/GW01_20260820_2.csv"
    assert len(projections.read_registry(store)) == 2


def test_latest_picks_newest_vintage_at_or_before_gw(tmp_path):
    store = tmp_path / "projections"
    projections.register(_shifted(tmp_path, "pre1.csv", 1, datetime(2026, 8, 3)), projections_dir=store)
    projections.register(
        _shifted(tmp_path, "pre2.csv", 1, datetime(2026, 8, 10), tweak="F,9,X,4.0,4.0,Beta United,0,0,0,0,0,0\n"), projections_dir=store
    )
    projections.register(_shifted(tmp_path, "gw6.csv", 6, datetime(2026, 10, 5)), projections_dir=store)
    assert projections.latest(1, store).name == "GW01_20260810.csv"  # later download of the same vintage
    assert projections.latest(5, store).name == "GW01_20260810.csv"
    assert projections.latest(6, store).name == "GW06_20261005.csv"
    assert projections.latest(30, store).name == "GW06_20261005.csv"
    with pytest.raises(LookupError):
        projections.latest(1, tmp_path / "empty")


def test_id_report_flags_missing_renamed_and_moved_players():
    bootstrap = {
        "teams": [{"id": 1, "name": "Alpha FC"}, {"id": 2, "name": "Beta United"}],
        "elements": [
            {"id": 1, "web_name": "K.Keeper", "team": 1, "element_type": 1},  # initial added: fine
            {"id": 2, "web_name": "Defenseur", "team": 2, "element_type": 2},  # accents differ, moved club: fine
            {"id": 3, "web_name": "Someone Else", "team": 2, "element_type": 3},
        ],
    }
    report = projections.id_report(projections.load_solio(FIXTURE), bootstrap)
    assert dict(zip(report["fpl_id"], report["issue"], strict=True)) == {3: "name", 4: "missing"}


def test_cli_register(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(projections, "PROJECTIONS_DIR", tmp_path / "projections")
    projections._main(["register", str(_shifted(tmp_path, "projection (1).csv", 1, datetime(2026, 8, 3)))])
    assert "GW01_20260803.csv (vintage GW1, GW1-3, 4 players)" in capsys.readouterr().out
