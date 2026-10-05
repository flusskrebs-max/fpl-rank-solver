# 0003: Python 3.14 + uv; snapshot all live data; vaastav for history

Date: 2026-10-05 · Status: Accepted

## Context

- Upstream requires Python ≥ 3.14 and uses uv.
- The FPL API only exposes the present. Prices, ownership and the field's teams at a past GW are
  gone unless saved, and backtests need exactly that.
- vaastav/Fantasy-Premier-League publishes per-season, per-GW player data (points, minutes, price,
  selected count) and is reachable from cloud sessions.
- Cloud sessions cannot currently reach fantasy.premierleague.com (network allowlist).

## Decision

- Python 3.14, dependencies managed by uv (`pyproject.toml` + `uv.lock`).
- Every live API response used goes through `fplrank.data.fpl_api.FplApi`, which writes a dated
  snapshot to `data/snapshots/`. Solves record which snapshots they used.
- Historical work uses vaastav data via `fplrank.data.historical`, rebuilt into API-shaped inputs by
  `fplrank.data.offline` so the same solver code runs on past and present.
- `data/` is local and git-ignored.

## Consequences

- Live collection must run somewhere with API access (Alex's computer, or a cloud session once the
  domain is allowed), ideally on a weekly schedule.
- Historical field data (EO by rank tier) is not in vaastav; we'll need to collect it ourselves going
  forward, or find an archive.
