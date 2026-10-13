# Scheduling the elite picks collector (Windows)

`fplrank.collect.elite_picks` downloads picks, chips, transfers and ranks for the manager sets in
`config/manager_sets.toml` (top 1000, a top-10k sample, AE64, E64) and rebuilds `data/collected/*.parquet`.
It needs the FPL API, so it runs on Alex's PC, not in cloud sessions.

## What each run fetches (`--scope`)

| scope | per manager | used by | requests (2,024 managers, one new GW) |
|---|---|---|---|
| `picks` | the deadline squad for each GW not yet saved | every EO option (`--eo AE64/E64/top1000/top10k/mix`) | about 2,300: 5 min |
| `history` | + season history (points, hits, overall rank per GW) | the `--target` line drift, the spread check | about 4,500 or more |
| `full` (default) | + transfers | research only (naive-field backtests, EO-blend fits) | about 6,500 or more |

A manager new to the sets (the top 1000 and the top-10k sample are re-read from the standings each run, and
change from week to week) gets only the latest squad in a `picks` run, and the whole season in a `history` or
`full` run. Measured 13 Oct (GW6, before that shortcut, with ~900 new managers): `picks` took 11.6 min for
5,263 requests, against about 85 min for the old full run at 2 requests per second.

The weekly solve needs only `picks`; the drift is a season average, so history once a week is plenty.
Requests run 4 managers side by side, at most 8 per second in total (`--workers`, `--rate`); a refused
request (429) is retried with back-off. Each run also re-reads the ~220 standings pages that say who is in
the top sets (once they are 12 hours old).

The picks scope works out which GWs to try from each manager's saved history (fetched only if there is
none), so a GW a manager missed is a 404 and skipped, not a failure.

## Schedule

- **Friday 20:00, `--scope picks`**, after most GW deadlines: the new GW's squads, captains and chips.
- **Tuesday 20:00, `--scope history`**, after the GW has finished: points, hits and ranks too.
- **`full`** only when refitting a research model: run it by hand.

The page's "Get the field's squads" button runs `--scope picks`.

## One-off run

```bash
uv run python -m fplrank.collect.elite_picks collect --scope picks   # squads only
uv run python -m fplrank.collect.elite_picks collect                 # everything
uv run python -m fplrank.collect.elite_picks collect --top 20        # quick test
uv run python -m fplrank.collect.elite_picks report                  # top-1000 vs Elite 64 report
```

If a run is interrupted, run it again: it picks up from the saved snapshots.

## Set up the schedule

`scripts/collect_elite.cmd` runs the collector from the repo folder (passing on any arguments) and appends to
`data/collected/logs/collect.log`. The tasks start it through `conhost.exe --headless`, so no console window
opens.

**Status (2026-10-13):** both tasks are set up on Alex's PC ("fplrank collect (Fri)" with `--scope picks`,
"fplrank collect (Tue)" with `--scope history`, 20:00), headless, with catch-up after a missed start. On
9 Oct the Friday run's console window was closed 8 s in (result 0xC000013A, `^C` in the log), so the squads
stalled at GW5; hence headless. If the PC is off or a run fails, the page's setup box shows the squads are
behind, and `fplrank solve` prints a warning.

To recreate them (e.g. after moving the repo), run this in PowerShell:

```powershell
$repo = "C:\Users\Alex\Documents\fpl-rank-solver"
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 3) -MultipleInstances IgnoreNew
foreach ($run in @(@("Friday", "picks"), @("Tuesday", "history"))) {
  $action = New-ScheduledTaskAction -Execute "conhost.exe" -Argument "--headless `"$repo\scripts\collect_elite.cmd`" --scope $($run[1])" -WorkingDirectory $repo
  $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $run[0] -At "20:00"
  Register-ScheduledTask -TaskName "fplrank collect ($($run[0].Substring(0,3)))" -Action $action -Trigger $trigger -Settings $settings -Force
}
```

Notes:

- `-StartWhenAvailable` means a run missed because the PC was off or asleep happens as soon as
  it's back. Tasks run only while you're logged in.
- Check them: `Get-ScheduledTask -TaskName "fplrank collect*" | Get-ScheduledTaskInfo`.
- Test one straight away: `Start-ScheduledTask -TaskName "fplrank collect (Fri)"`, then check the log.
- Remove them: `Unregister-ScheduledTask -TaskName "fplrank collect*" -Confirm:$false`.
