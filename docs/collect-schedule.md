# Scheduling the elite picks collector (Windows)

`fplrank.collect.elite_picks` downloads picks, chips, transfers and ranks for the manager sets in
`config/manager_sets.toml` (default: overall top 1000) and rebuilds `data/collected/*.parquet`.
It needs the FPL API, so it runs on Alex's PC, not in cloud sessions.

Run it twice a week:

- **Friday evening**, after most GW deadlines: the new GW's picks, captains and chips.
- **Tuesday evening**, after the GW has finished: final ranks, points, transfers and hits.

A full top-1000 run is about 7,000 requests at 2 per second (about an hour) the first time. Later
runs are quicker: picks for past GWs are never downloaded again, only the new GW plus each
manager's history and transfers.

## One-off run

```bash
uv run python -m fplrank.collect.elite_picks collect            # all sets in the config
uv run python -m fplrank.collect.elite_picks collect --top 20   # quick test
uv run python -m fplrank.collect.elite_picks report             # top-1000 vs Elite 64 report
```

If a run is interrupted, run it again: it picks up from the saved snapshots.

## Set up the schedule

`scripts/collect_elite.cmd` runs the collector from the repo folder and appends to
`data/collected/logs/collect.log`. Create the two tasks once, in PowerShell or Command Prompt:

```bash
schtasks /Create /TN "fplrank collect (Fri)" /SC WEEKLY /D FRI /ST 20:00 /TR "\"C:\Users\Alex\Documents\fpl-rank-solver\scripts\collect_elite.cmd\""
```

```bash
schtasks /Create /TN "fplrank collect (Tue)" /SC WEEKLY /D TUE /ST 20:00 /TR "\"C:\Users\Alex\Documents\fpl-rank-solver\scripts\collect_elite.cmd\""
```

Notes:

- The tasks run only while you're logged in and the PC is awake. To catch up after the PC was off,
  open Task Scheduler, find each task, and under **Settings** tick *Run task as soon as possible
  after a scheduled start is missed*.
- Test a task straight away: `schtasks /Run /TN "fplrank collect (Fri)"`, then check the log.
- Remove them: `schtasks /Delete /TN "fplrank collect (Fri)" /F` (and the same for Tue).
- If the repo moves, recreate the tasks with the new path.
