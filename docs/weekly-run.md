# Weekly run (before each deadline)

What to do on your PC each GW, in PowerShell from the repo folder (`cd C:\Users\Alex\Documents\fpl-rank-solver`).
There is one command, `uv run fplrank solve`. It is Sertalp's `solve.py` (his settings files and every
one of his flags work unchanged) plus our two extras: the field's EO and the choice of λ.

## Shortcut: one double-click

`scripts\fplrank_page.cmd` does step 1 and opens the page (step 4) in one go: it pulls the latest code if
you are on `main` (on any other branch it switches back to `main` first, setting aside any uncommitted changes with
`git stash`), installs any new packages, then opens
http://localhost:8501. Close its window to stop the page.

The box at the top of the page does steps 1 to 3 with buttons, plus the field's squads,, so no PowerShell is needed once a week:

- **Code**: "Get the latest code" pulls from GitHub (switching back to `main` first if needed). If anything came down, close the window and open the
  shortcut again (that also installs any new packages).
- **Team**: click the bookmarklet on the FPL site, paste into the box (Ctrl+V) and press "Save team". It is saved as
  `team.json` and "Use team.json" is ticked for you. Without it, your team is read from FPL by team id at each solve.
- **Solio files**: export both files from Solio to Downloads, then "Use the newest from Downloads". The page tells the
  projections and the EO forecast apart by their columns (not their names), so `projection (9).csv` is fine, and
  names the EO file by its first GW. Files older than a week are ignored. Or drag them onto the drop box.
- **EO forecast from an EO table** (in place of Solio's EO export): download or copy last GW's EO table (e.g. the
  top 10k CSV, `Player,Team,EOTop10k,...`) and use it the same way: from Downloads, the drop box, or paste it into
  "Or paste an EO table" and press "Build EO forecast". The page carries that EO forward to every GW from next GW
  (triple captains counted once; players not listed 0.1%) and saves it where `--eo solio` reads it. It names any row
  it couldn't match to a player. Needs the FPL API (or a saved bootstrap) to match names. Only needed for `--eo solio`:
  `--eo AE64`, `top10k` and the rest come from the collector and need no file.

- **Field's squads**: what the EO forecast is built from (every AE64 and E64 manager, the top 1000 and a top-10k
  sample, from FPL). The box shows which GW they are from and turns yellow when a newer GW has started; then press
  "Get the field's squads" before solving (about 5-10 minutes: only the latest GW's squads; it carries on where it stopped if interrupted). The
  solve also prints a WARNING if the squads are older than last GW. The scheduled runs (`docs/collect-schedule.md`)
  usually keep them up to date, but only when the PC is on at 20:00.

To put it on your desktop, run this once in PowerShell from the repo folder:

```powershell
$s = (New-Object -ComObject WScript.Shell).CreateShortcut("$([Environment]::GetFolderPath('Desktop'))\FPL solver.lnk")
$s.TargetPath = "$PWD\scripts\fplrank_page.cmd"; $s.WorkingDirectory = "$PWD"; $s.Save()
```

Right-click the shortcut, Properties, Change Icon to give it an icon of your choice. If you move the repo
folder, run it again.

## 1. Get the latest code (once a week)

```powershell
git checkout main
git pull
uv sync --group dev
```

`git pull` downloads whatever has been merged on GitHub since last week.

## 2. Put this GW's Solio files in place

On Solio, export the **projections** and the **effective ownership** file to Downloads. Then:

```powershell
Copy-Item "$HOME\Downloads\projection (9).csv" "vendor\open-fpl-solver\data\solio.csv"
Copy-Item "$HOME\Downloads\solio_effective_ownership.csv" "data\projections\solio_eo\EO_GW07_$(Get-Date -Format yyyyMMdd).csv"
```

Change `(9)` and `GW07` to match. `solio.csv` is the file his solver reads (his `datasource` is
`solio`). Both locations are git-ignored, so paid data is never uploaded. The EO file is only needed
for `--eo solio`. To build it from an EO table instead:

```powershell
uv run python -m fplrank.data.eo_paste "$HOME\Downloads\top10k_eo.csv"
```

## 3. Load your team

Before you have made any transfers this GW, his solver reads your team from the FPL API: pass
`--team_id <your team id>`.

If you have already made transfers, or prices have moved since, use his bookmarklet instead. Set it
up once by following `vendor\open-fpl-solver\data\getting_team_json.md`: a bookmark whose address is a
short `javascript:` snippet. Then each week:

1. Log in to fantasy.premierleague.com and click the bookmark. Your team is copied to the clipboard.
2. Save it as his team file:

   ```powershell
   [IO.File]::WriteAllText("$PWD\vendor\open-fpl-solver\data\team.json", (Get-Clipboard -Raw))
   ```

   This writes the file without a byte-order mark, which his solver needs. `team.json` is git-ignored.

3. Add `--team_data json` to the command below (keep `--team_id` so your points can be looked up).

## 4. Run the solver

```powershell
uv run fplrank solve --team_id <your team id> --eo AE64 --target 10000 --sims 50
```

Type your real team id in place of `<your team id>` (PowerShell rejects the `<`).

- `--eo` picks whose ownership to weigh against: `AE64`, `E64`, `elite` (the average of the two, with the
  line's drift measured against the same average), `top1000`, `top10k` (collector, last GW's EO with that
  GW's chips taken out) or `solio` (Solio's forecast). Or your own mix of the collector groups, such as
  `--eo AE64:0.4+E64:0.4+top10k:0.2` (weights scaled to add up to 1; the line's drift uses the AE64/E64 part).
- `--target 10000` solves once per λ from −0.3 to 0.3 and picks the λ with the best P(finishing in the
  top 10,000). Your points come from the FPL API, or give `--points`. Use `--lam 0.1` instead to fix λ.
  `--kappa 0.5` changes how much of your projected edge over the field counts (default 0.75;
  `docs/research/rank-goal-inputs.md`).
- `--eo_decay 0.7` (the default) applies λ in full to next GW and λ x 0.7^k to the GW k weeks later, on top of
  his `decay_base`. `--eo_decay 0` weighs EO on next GW only; `1` keeps λ at full strength through the horizon
  (`docs/research/eo-horizon.md`).
- `--sims 50` then runs his simulations 50 times at the chosen λ (his noise on the projections) and
  prints his summary of how often each move comes up. Leave it out for a quick run.
- `--workers 4` sets how many solves run at once (the λs, the three wildcard templates and the simulations each
  use about one CPU core). The default is half your logical CPUs, at most 8; each running solve needs roughly
  300-500 MB of memory. `--workers 1` runs them one at a time as before. The plans are the same either way.
- Any of his flags work as usual: `--horizon 5`, `--use_wc "[8]"`, `--banned "[...]"`, and so on.
  With no `--eo`, `--target` or `--lam` it is exactly his solver.

It prints one line per λ as each solve finishes (in the order they finish, with the time since the start), then the EO used, the gap to the target line, P by λ,
and his normal output for the chosen plan.

### Or use the page

```powershell
uv run fplrank page
```

This opens a page in your browser (http://localhost:8501) with the same options as boxes and a Solve button. It
shows the command it runs, the output as it comes, and P by λ as a chart. Under "Sertalp's settings" are his usual
settings (time limit, horizon, chips, banned/locked players, hits and so on), filled in from his settings files;
only the ones you change are passed on. It remembers your choices. Steps 1 to 3 still apply. Close the PowerShell window (or press Ctrl+C in it) to stop the page.

## 5. Read the plan and decide

P by λ shows how much the choice matters: early in the season the differences are small, because one
week's plan matters little over 30+ GWs. The simulations summary shows which moves are robust to
noise. Tell Claude in the project which plan you used and anything odd; it goes in
`docs/tasks/log.md`. The collector runs itself on Tuesday and Friday at 20:00 when the PC is on (`docs/collect-schedule.md`);
the setup box shows whether it has kept up.

## If something goes wrong

- "No EO for group": the collector hasn't run since the group was added; use `--eo AE64` or `--eo solio`.
- His solver can't find `solio.csv`: step 2 was missed or the file was saved under another name.
- A solve takes much longer than a minute or two: lower `--horizon`, or leave out `--sims`. If the PC runs short of
  memory, lower `--workers`.
