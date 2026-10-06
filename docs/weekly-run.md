# Weekly run (before each deadline)

What to do on your PC each GW, in PowerShell from the repo folder (`cd C:\Users\Alex\Documents\fpl-rank-solver`).
There is one command, `uv run fplrank solve`. It is Sertalp's `solve.py` (his settings files and every
one of his flags work unchanged) plus our two extras: the field's EO and the choice of λ.

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
for `--eo solio`.

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
  GW's chips taken out) or `solio` (Solio's forecast).
- `--target 10000` solves once per λ from −0.3 to 0.3 and picks the λ with the best P(finishing in the
  top 10,000). Your points come from the FPL API, or give `--points`. Use `--lam 0.1` instead to fix λ.
  `--kappa 0.5` changes how much of your projected edge over the field counts (default 0.75;
  `docs/research/rank-goal-inputs.md`).
- `--eo_decay 0.7` (the default) applies λ in full to next GW and λ x 0.7^k to the GW k weeks later, on top of
  his `decay_base`. `--eo_decay 0` weighs EO on next GW only; `1` keeps λ at full strength through the horizon
  (`docs/research/eo-horizon.md`).
- `--sims 50` then runs his simulations 50 times at the chosen λ (his noise on the projections) and
  prints his summary of how often each move comes up. Leave it out for a quick run.
- Any of his flags work as usual: `--horizon 5`, `--use_wc "[8]"`, `--banned "[...]"`, and so on.
  With no `--eo`, `--target` or `--lam` it is exactly his solver.

It prints one line per λ as each solve finishes, then the EO used, the gap to the target line, P by λ,
and his normal output for the chosen plan.

## 5. Read the plan and decide

P by λ shows how much the choice matters: early in the season the differences are small, because one
week's plan matters little over 30+ GWs. The simulations summary shows which moves are robust to
noise. Tell Claude in the project which plan you used and anything odd; it goes in
`docs/tasks/log.md`. The collector runs itself on Tuesday and Friday at 20:00 (`docs/collect-schedule.md`).

## If something goes wrong

- "No EO for group": the collector hasn't run since the group was added; use `--eo AE64` or `--eo solio`.
- His solver can't find `solio.csv`: step 2 was missed or the file was saved under another name.
- A solve takes much longer than a minute or two: lower `--horizon`, or leave out `--sims`.
