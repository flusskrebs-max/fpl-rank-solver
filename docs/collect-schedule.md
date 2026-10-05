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
`data/collected/logs/collect.log`.

**Status (2026-10-05):** both tasks are set up on Alex's PC ("fplrank collect (Fri)" and
"fplrank collect (Tue)", 20:00), with catch-up after a missed start. A test run from Task Scheduler
succeeded.

To recreate them (e.g. after moving the repo), run this in PowerShell:

```powershell
$repo = "C:\Users\Alex\Documents\fpl-rank-solver"
$action = New-ScheduledTaskAction -Execute "$repo\scripts\collect_elite.cmd" -WorkingDirectory $repo
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3) -MultipleInstances IgnoreNew
foreach ($day in "Friday", "Tuesday") {
  $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $day -At "20:00"
  Register-ScheduledTask -TaskName "fplrank collect ($($day.Substring(0,3)))" -Action $action -Trigger $trigger -Settings $settings -Force
}
```

Notes:

- `-StartWhenAvailable` means a run missed because the PC was off or asleep happens as soon as
  it's back. Tasks run only while you're logged in.
- Check them: `Get-ScheduledTask -TaskName "fplrank collect*" | Get-ScheduledTaskInfo`.
- Test one straight away: `Start-ScheduledTask -TaskName "fplrank collect (Tue)"`, then check the log.
- Remove them: `Unregister-ScheduledTask -TaskName "fplrank collect*" -Confirm:$false`.
