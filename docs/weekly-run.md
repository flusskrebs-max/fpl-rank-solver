# Weekly run (before each deadline)

What to do on your PC each GW, in PowerShell from the repo folder (`cd C:\Users\Alex\Documents\fpl-rank-solver`).
About ten minutes, most of it waiting for solves. Nothing here needs git.

## 1. Get the latest code (once a week)

```powershell
git checkout main
git pull
uv sync --group dev
```

`git pull` downloads whatever has been merged on GitHub since last week.

## 2. Download and register this GW's Solio files

On Solio, export the **projections** (`projection (N).csv`) and the **effective ownership** file
(`solio_effective_ownership.csv`) to Downloads. Then:

```powershell
uv run python -m fplrank.data.projections register "$HOME\Downloads\projection (9).csv"
Copy-Item "$HOME\Downloads\solio_effective_ownership.csv" "data\projections\solio_eo\EO_GW07_$(Get-Date -Format yyyyMMdd).csv"
```

Change `(9)` and `GW07` to match. Both end up under `data\`, which git ignores, so paid data is
never uploaded. `register` prints the GWs the file covers; check it starts at the coming GW.

## 3. Run the solver

The quickest way is the weekly report, which runs everything below and writes `reports\GW{n}.md`:

```powershell
uv run python -m fplrank.weekly --team <your team id> --target 10000
```

It uses `--eo AE64` (last GW's collected EO) unless you add `--eo-forecast` (the model's guess at the deadline EO)
or `--eo solio`. Your points and rank come from the FPL API; `--points`/`--rank` override them. The report gives the recommended
moves, captain and XI, P(top 10,000) against the EV plan, the EV cost, two alternatives and the full
sweep. If it starts with a WARNING about `ep_next`, step 2 was missed: don't use that plan.

To run the steps by hand instead:

```powershell
uv run python -m fplrank.opt.ownership --team <your team id> --eo AE64 --sweep
```

- `--eo` picks whose ownership to weigh against: `AE64`, `E64`, `top1000`, `top10k` (collector, last
  GW's EO repeated) or `solio` (Solio's forecast, a different EO each GW).
- `--sweep` tries λ from −0.3 to 0.3; use `--lam 0 0.1` for just a few values. λ > 0 covers what the
  field owns, λ < 0 chases differentials.
- `--horizon` (default 5) and `--secs` (default 600 per solve) as in the upstream solver.

Output: one row per distinct plan, with the λ values that give it, captain, transfers, chip, EV over
the horizon, EV this GW, EV cost against λ = 0, EO held and exposure (how far the XI is from the field).

To have it choose λ for a rank goal, add `--target-rank 10000` (your points are read from FPL, or
give `--points`). It prints P(finishing at or above the line) for each λ and the best one. Early in
the season the differences are small, because one week's plan matters little over 30+ GWs.

## 4. Read the plan and decide

Start from the λ = 0 row (pure EV). A row with a small EV cost and a big drop in exposure is cheap
cover; a large EV cost needs a reason (a big lead to protect, or a big gap to close). Until S2 lands,
choosing λ is your call.

## 5. Afterwards

Tell Claude in the project which λ you used and anything odd in the output; it goes in
`docs/tasks/log.md` and feeds the next fix. The collector runs itself on Tuesday and Friday at 20:00
(`docs/collect-schedule.md`).

## If something goes wrong

- "No Solio file registered for this GW": step 2 was missed, or the file starts at an earlier GW. The
  solver falls back to FPL's `ep_next`, which is a form measure, not a projection, so don't use that plan.
- "No EO for group": the collector hasn't run since the group was added; use `--eo AE64` or `--eo solio`.
- A solve takes much longer than a minute or two: lower `--horizon`.
