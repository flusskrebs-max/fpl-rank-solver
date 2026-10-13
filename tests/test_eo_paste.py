"""Building the EO file `--eo solio` reads from a pasted EO table (fplrank.data.eo_paste)."""

import gzip
import json
from datetime import date
from pathlib import Path

import pytest

from fplrank.data import eo_paste
from fplrank.opt import ownership as ow

FIXTURE = Path(__file__).parent / "fixtures" / "gw6_live" / "bootstrap-static.json.gz"
# LiveFPL's top-10k layout as Alex downloaded it (GW6 2026-27): duplicate and blank headers, % signs, a count at the end
TABLE = """Player,Team,EOTop10k,CTop10k,TcTop10k,EO_overall,CTop10k,TCTop10k,
Haaland,Man City,123.28%,30.26%,0%,0%,0%,0%,6
Groß,Brighton,89.02%,4.61%,0.01%,0%,0%,0%,6
João Pedro,Chelsea,86.39%,8.09%,0.01%,0%,0%,0%,12
Nobody,Chelsea,5.00%,0%,0%,0%,0%,0%,0
"""


@pytest.fixture(scope="module")
def bootstrap():
    return json.loads(gzip.open(FIXTURE).read())


def test_read_table_finds_columns():
    t = eo_paste.read_table("﻿" + TABLE)
    assert t["name"].tolist() == ["Haaland", "Groß", "João Pedro", "Nobody"]
    assert t["eo"].tolist() == [123.28, 89.02, 86.39, 5.0]
    assert t["tc"].tolist() == [0.0, 0.01, 0.01, 0.0]
    tabbed = eo_paste.read_table("Name\tEO\nHaaland\t120\n")
    assert (tabbed["eo"].tolist(), tabbed["team"].tolist()) == ([120.0], [None])
    with pytest.raises(ValueError, match="EO column"):
        eo_paste.read_table("Player,Team,Price\nHaaland,Man City,15\n")


def test_build_carries_eo_forward(bootstrap, tmp_path):
    table, missing = eo_paste.build(TABLE, bootstrap)
    assert missing == ["Nobody (Chelsea)"]
    assert len(table) == len(bootstrap["elements"])
    gws = [c for c in table.columns if c.startswith("GW")]
    assert (gws[0], gws[-1]) == ("GW6 EO %", "GW38 EO %")  # the fixture is from before the GW6 deadline
    top = table.iloc[0]
    assert (top["Name"], top["Team"], top["GW6 EO %"], top["GW38 EO %"]) == ("Haaland", "MCI", 123.28, 123.28)
    assert table.loc[table["Name"] == "Groß", "GW6 EO %"].item() == 89.01  # triple captains count once
    assert table["Avg EO %"].min() == eo_paste.FLOOR  # anyone not listed

    path = eo_paste.save(table, tmp_path, today=date(2026, 10, 13))
    assert path.name == "EO_GW06_20261013.csv"
    eo = ow.load_solio_eo(bootstrap, path)  # read by ID, as --eo solio does
    assert eo.loc[411, 6] == pytest.approx(1.2328)
    assert list(eo.columns) == list(range(6, 39))


def test_build_by_name_only_and_set_gw(bootstrap):
    table, missing = eo_paste.build("Player,EO\nHaaland,120\n", bootstrap, next_gw=7, floor=0)
    assert missing == []
    assert table.columns[5] == "GW7 EO %"
    assert table.iloc[0]["GW7 EO %"] == 120
    assert table["Avg EO %"].iloc[1:].eq(0).all()
