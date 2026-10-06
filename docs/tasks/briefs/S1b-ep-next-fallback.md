# S1b: Free fallback projections from FPL `ep_next`

Status: Ready · Size: small · Release: v0.1 · Depends on: S1 (PR #14)

## Why

S1 needs a Solio file, which is paid, local only and sometimes out of date. FPL's own one-GW
projection (`ep_next` in `bootstrap-static`) is free and tracks vaastav `xP` closely (correlation
0.92-0.97; `docs/research/data-sources.md`). A fallback lets the CLI run when no Solio file is
registered and lets tests and cloud sessions run S1 end to end.

## Do

1. `fplrank.data.projections`: `from_ep_next(bootstrap, horizon)` returning the same long shape as the
   Solio loader. One GW of `ep_next`; later GWs repeat it scaled by fixture count (0 for a blank, ×2 for
   a double), with `xmins` from the player's recent minutes share. Say in the docstring it is crude.
2. S1 CLI: `--projections solio|ep_next` (default: latest Solio if registered for this GW, else
   `ep_next` with a printed warning).
3. A test that runs S1 on a saved `bootstrap-static` fixture with `ep_next` projections, offline.
4. Save one real mid-season `my_data` + `bootstrap-static` (+ fixtures) as a test fixture; run S1 offline
   with `ep_next`, horizon 4, and assert the λ = 0 plan equals `solve_ev`'s.

## Done when

`uv run python -m fplrank.opt.ownership --team <id> --eo AE64 --sweep --projections ep_next` runs on a
machine with no Solio file, and CI covers it offline.
