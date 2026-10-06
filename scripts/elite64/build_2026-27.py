# Cowork original (handed over 2026-10-06), kept as written for the record; not maintained or linted.
# Run it from a scratch folder holding its inputs under the names it reads:
#   raw/eo.csv, raw/meta.csv = the 2026-27 GW1-5 transcriptions before ids were added
#   players_raw.csv / teams.csv: vaastav 2026-27 files (data/raw/vaastav/2026-27/ via fplrank.data.historical);
#     the hard-coded /home/claude/... paths are from the Cowork sandbox.
# Outputs committed as datasets/elite_ownership/elite64_{eo,meta}_2026-27.csv; its checks live on in tests/test_elite_data.py.
"""Validate transcribed Elite64 graphics and build tidy tables with FPL IDs."""
import pandas as pd

eo = pd.read_csv("raw/eo.csv")
meta = pd.read_csv("raw/meta.csv")
pr = pd.read_csv("/home/claude/fpl-rank-solver/data/raw/vaastav/2026-27/players_raw.csv")
teams = pd.read_csv("/home/claude/fpl-rank-solver/data/raw/vaastav/2026-27/teams.csv")
pr["team_short"] = pr.team.map(teams.set_index("id").short_name)
issues = []

# 1. group totals should be 64 for tables that partition managers
for table in ["captain", "chip_active", "fts_used", "fts_remaining_next", "hits"]:
    s = meta[meta.table == table].groupby("gw")[["ae64", "e64"]].sum()
    for gw, row in s.iterrows():
        for g in ["ae64", "e64"]:
            if row[g] != 64:
                issues.append(f"GW{gw} {table} {g} sums to {row[g]} (expected 64)")

# 2. chips remaining(t) = chips remaining(t-1) - chips used(t)
rem = meta[meta.table == "chips_remaining"].pivot_table(index="gw", columns="item", values=["ae64", "e64"])
act = meta[meta.table == "chip_active"].pivot_table(index="gw", columns="item", values=["ae64", "e64"])
for g in ["ae64", "e64"]:
    for chip in ["WC", "FH", "TC", "BB"]:
        start = 64
        for gw in sorted(rem.index):
            expected = start - act.loc[gw, (g, chip)]
            got = rem.loc[gw, (g, chip)]
            if expected != got:
                issues.append(f"GW{gw} {g} {chip} remaining {got}, expected {expected} from usage (source graphic)")
                got = expected  # trust usage counts; the GW3 AE64 'remaining' panel was not updated
                meta.loc[(meta.gw == gw) & (meta.table == "chips_remaining") & (meta["item"] == chip), g] = got
            start = got

# 3. map names to FPL ids (web_name + team)
key = pr.set_index(["web_name", "team_short"]).id
def lookup(r):
    try:
        return int(key.loc[(r.player, r.team)])
    except KeyError:
        # player moved club after the GW1 snapshot: fall back to name + position
        m = pr[(pr.web_name == r.player) & (pr.element_type == {"G": 1, "D": 2, "M": 3, "F": 4}[r.pos])]
        return int(m.id.iloc[0]) if len(m) == 1 else None
eo["fpl_id"] = eo.apply(lookup, axis=1).astype("Int64")
for r in eo[eo.fpl_id.isna()].drop_duplicates("player").itertuples():
    issues.append(f"No FPL id match for {r.player} ({r.team})")

# 4. coverage: listed EO as share of the group's total EO
total = eo.groupby("gw")[["ae64_eo", "e64_eo"]].sum()
chip = act
for gw in total.index:
    for g in ["ae64", "e64"]:
        bb = chip.loc[gw, (g, "BB")] / 64
        tc = chip.loc[gw, (g, "TC")] / 64
        full = 1100 + 100 + 100 * tc + 400 * bb  # starting XI + captain + TC extra + bench on BB
        total.loc[gw, f"{g}_coverage"] = round(total.loc[gw, f"{g}_eo"] / full, 2)

eo.to_csv("elite64_eo_2026-27.csv", index=False)
meta.to_csv("elite64_meta_2026-27.csv", index=False)
print("Coverage of total EO by the listed players:\n", total)
print("\nIssues:" if issues else "\nNo issues", *issues, sep="\n- ")
