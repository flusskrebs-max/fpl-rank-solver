# EO1b: re-picked, herded EO for `--eo` (2026-10-06)

**Why.** `eo-blend.md` (#40) found that re-picking each manager's XI and captain on their chip-free squad from
next-GW xP cuts EO error by about a third against persistence, as well as the per-manager solve. `--eo` still
repeated last GW's EO. Check 6 there also showed the elite concentrate the armband harder than the re-pick does.

**What.** `opt.ownership.pick_eo` uses `repick_eo` (B1 + B2 from `model/eo_blend.py`, no new solver) on his
projections' next-GW column; `elite` keeps the `group_weights` mix and `LIVE_WEIGHT`. For AE64/E64 the armband is
herded (`herd_captains`): the observed 2025-26 concentration (0.97 / 0.91), split between the top two only when
their xP is close, with non-owners buying the captain. Falls back to the repeated chip-free EO.

**Checks.** Tests on synthetic data only; `uv run pytest`, `uv run ruff check .`. Pass criterion for herding,
before scoring: GW2-5 EO error not worse than the plain re-pick in either group, better in one.

**Done when.** `fplrank solve --eo elite` prints "squads re-picked on GW*n* xP"; the herded GW2-5 numbers are in
`eo-blend.md`.
