# Logging the solver in to FPL (exact selling prices, bank, free transfers, chips)

Since 2025-26 `https://fantasy.premierleague.com/api/my-team/<id>/` needs you to be logged in. Without a
login the solver still works for any team id, but it estimates selling prices, bank and free transfers
from public data and prints a warning saying so. With a login it uses the exact numbers from FPL.

Your login details stay on your PC: they go in a file called `.env`, which git ignores (it is listed in
`.gitignore`), so it is never committed or uploaded. The code never prints or saves them.

## One-off setup

1. In PowerShell, from the repo folder (`cd C:\Users\Alex\Documents\fpl-rank-solver`), open a new file:

   ```powershell
   notepad .env
   ```

   Say yes when Notepad asks to create it.

2. Put these two lines in it, with your Premier League account email and password, then save and close:

   ```
   FPL_EMAIL=you@example.com
   FPL_PASSWORD=your-password
   ```

3. Check git ignores it. This should print `.env`:

   ```powershell
   git check-ignore .env
   ```

4. Check the login works:

   ```powershell
   uv run python -m fplrank.data.team_state 157924
   ```

   The first line should say `source: my-team`, followed by your bank, free transfers, chips and
   selling prices, and a last line comparing them with the public estimate. If it says
   `public-estimate` instead, the warning above it says why (e.g. wrong password).

That's it: `fplrank.opt.ownership` and the weekly report pick up the login automatically.

## If the login stops working

The Premier League sometimes changes its login page. If the warning says the login page has changed,
you can paste a token from your browser instead, as a stop-gap (it expires within a few hours):

1. Log in at fantasy.premierleague.com in Chrome, open DevTools (F12) > Network, and click "Pick Team".
2. Click the `my-team` request, find the request header `x-api-authorization: Bearer eyJ...`, and copy
   the part after `Bearer `.
3. Add it to `.env` as `FPL_ACCESS_TOKEN=eyJ...`.

The token is used if there is no email/password, or if the email/password login fails. Then ask Claude
to update `src/fplrank/data/team_state.py`.

You can also set these as environment variables instead of using `.env`; environment variables win.
