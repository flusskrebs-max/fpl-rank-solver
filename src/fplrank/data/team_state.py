"""Current team state for a solve: selling prices, bank, free transfers and chips.

The exact numbers only come from the logged-in endpoint /api/my-team/{id}/, which since
2025-26 needs a bearer token from the Premier League account login (it returns 403
otherwise). With credentials we log in and use it; without, we fall back to upstream's
reconstruction from public endpoints (transfer history + price rules), which is right for
most teams but can be off on selling prices and free transfers, and say so with a warning.

Credentials are read from environment variables, or from the git-ignored `.env` file in the
repo root, and are never printed, logged or saved:

    FPL_EMAIL=...          # Premier League account login (preferred: works every week)
    FPL_PASSWORD=...
    FPL_ACCESS_TOKEN=...   # or: a bearer token copied from the browser (expires within hours)

The login follows the PKCE flow in the Google Doc Alex shared (2026-10-06); the
account.premierleague.com ids below come from there. If the PL changes its login page,
`login()` raises and `load_team_state` falls back to public data with a warning.

CLI (Alex's PC): `uv run python -m fplrank.data.team_state 157924`
"""

import base64
import hashlib
import os
import re
import secrets
import sys
import uuid
import warnings
from collections.abc import Callable
from pathlib import Path

import requests

from fplrank.data.fpl_api import BASE_URL, FplApi
from fplrank.paths import PROJECT_ROOT

ENV_FILE = PROJECT_ROOT / ".env"

CLIENT_ID = "bfcbaf69-aade-4c1b-8f00-c1cb8a193030"
REDIRECT_URI = "https://fantasy.premierleague.com/"
ACCOUNT = "https://account.premierleague.com"
AUTHORIZE_URL = f"{ACCOUNT}/as/authorize"
START_URL = f"{ACCOUNT}/davinci/policy/262ce4b01d19dd9d385d26bddb4297b6/start"
LOGIN_URL = ACCOUNT + "/davinci/connections/{}/capabilities/customHTMLTemplate"
RESUME_URL = f"{ACCOUNT}/as/resume"
TOKEN_URL = f"{ACCOUNT}/as/token"
CONNECTION_ID = "867ed4363b2bc21c860085ad2baa817d"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


class LoginError(RuntimeError):
    """The Premier League login did not complete. Messages never include credentials."""


# ---------------------------------------------------------------------------------------------
# Credentials


def read_env_file(path: Path = ENV_FILE) -> dict[str, str]:
    """KEY=VALUE pairs from a .env file (blank lines, # comments and optional quotes allowed)."""
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip().removeprefix("export ").strip()] = value.strip().strip("'\"")
    return values


def credentials(env: dict[str, str] | None = None, env_file: Path = ENV_FILE) -> dict[str, str]:
    """FPL_EMAIL / FPL_PASSWORD / FPL_ACCESS_TOKEN from the environment, else from `.env`."""
    env = os.environ if env is None else env
    file_values = read_env_file(env_file)
    keys = ("FPL_EMAIL", "FPL_PASSWORD", "FPL_ACCESS_TOKEN")
    return {k: v for k in keys if (v := env.get(k) or file_values.get(k))}


# ---------------------------------------------------------------------------------------------
# Login (PKCE against account.premierleague.com)


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return verifier, challenge


def _json(response, step: str) -> dict:
    if response.status_code >= 400:
        raise LoginError(f"login step '{step}' failed with HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as e:
        raise LoginError(f"login step '{step}' did not return JSON") from e


def login(email: str, password: str, session: requests.Session | None = None) -> str:
    """Log in to the Premier League account and return an access token for the FPL API."""
    s = session or requests.Session()
    s.headers.setdefault("User-Agent", BROWSER_UA)
    verifier, challenge = _pkce()

    # 1. Authorisation page: a short-lived token for the login widget, and the OAuth state
    page = s.get(
        AUTHORIZE_URL,
        params={
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "openid profile email offline_access",
            "state": uuid.uuid4().hex,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        timeout=30,
    ).text
    widget_token = re.search(r'"accessToken":"([^"]+)"', page)
    state = re.search(r'<input[^>]+name="state"[^>]+value="([^"]+)"', page)
    if not (widget_token and state):
        raise LoginError("login page has changed (no accessToken/state found)")
    bearer = {"Authorization": f"Bearer {widget_token.group(1)}", "Content-Type": "application/json"}

    # 2. Start the sign-in flow
    start = _json(s.post(START_URL, headers=bearer, timeout=30), "start")
    interaction = {"interactionId": start["interactionId"]}

    # 3. Three posts: poll, submit email + password, confirm
    polled = _json(
        s.post(
            LOGIN_URL.format(CONNECTION_ID),
            headers=interaction,
            json={
                "id": start["id"],
                "eventName": "continue",
                "parameters": {"eventType": "polling"},
                "pollProps": {"status": "continue", "delayInMs": 10, "retriesAllowed": 1, "pollChallengeStatus": False},
            },
            timeout=30,
        ),
        "poll",
    )
    submitted = _json(
        s.post(
            LOGIN_URL.format(CONNECTION_ID),
            headers=interaction,
            json={
                "id": polled["id"],
                "nextEvent": {"constructType": "skEvent", "eventName": "continue", "params": [], "eventType": "post", "postProcess": []},
                "parameters": {"buttonType": "form-submit", "buttonValue": "SIGNON", "username": email, "password": password},
                "eventName": "continue",
            },
            timeout=30,
        ),
        "sign-on",
    )
    if "connectionId" not in submitted:
        raise LoginError("sign-on was rejected (check FPL_EMAIL / FPL_PASSWORD)")
    confirmed = _json(
        s.post(
            LOGIN_URL.format(submitted["connectionId"]),
            headers=bearer,
            json={
                "id": submitted["id"],
                "nextEvent": {"constructType": "skEvent", "eventName": "continue", "params": [], "eventType": "post", "postProcess": {}},
                "parameters": {"buttonType": "form-submit", "buttonValue": "SIGNON"},
                "eventName": "continue",
            },
            timeout=30,
        ),
        "confirm",
    )
    if "dvResponse" not in confirmed:
        raise LoginError("sign-on did not complete (no dvResponse)")

    # 4. Resume the OAuth flow; the redirect carries the authorisation code
    resumed = s.post(RESUME_URL, data={"dvResponse": confirmed["dvResponse"], "state": state.group(1)}, allow_redirects=False, timeout=30)
    code = re.search(r"[?&]code=([^&]+)", resumed.headers.get("Location", ""))
    if not code:
        raise LoginError("no authorisation code after sign-on")

    # 5. Exchange the code for the FPL access token
    token = _json(
        s.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
                "code": code.group(1),
                "code_verifier": verifier,
                "client_id": CLIENT_ID,
            },
            timeout=30,
        ),
        "token",
    )
    if "access_token" not in token:
        raise LoginError("token exchange returned no access_token")
    return token["access_token"]


def access_token(creds: dict[str, str], login_fn: Callable[[str, str], str] = login) -> str | None:
    """A bearer token from the credentials: logs in with email + password if given, else FPL_ACCESS_TOKEN."""
    if "FPL_EMAIL" in creds and "FPL_PASSWORD" in creds:
        try:
            return login_fn(creds["FPL_EMAIL"], creds["FPL_PASSWORD"])
        except (LoginError, requests.RequestException, KeyError) as e:
            if "FPL_ACCESS_TOKEN" not in creds:
                raise LoginError(str(e)) from None
            warnings.warn(f"FPL login failed ({e}); trying FPL_ACCESS_TOKEN instead", stacklevel=2)
    return creds.get("FPL_ACCESS_TOKEN")


# ---------------------------------------------------------------------------------------------
# Team state


def fetch_my_team(team_id: int, token: str, api: FplApi | None = None) -> dict:
    """/api/my-team/{id}/ with a bearer token. The payload (no token in it) is snapshotted."""
    api = api or FplApi()
    response = api.session.get(f"{BASE_URL}/my-team/{team_id}/", headers={"X-API-Authorization": f"Bearer {token}"}, timeout=30)
    if response.status_code in (401, 403):
        raise LoginError(f"my-team/{team_id}/ refused the token (HTTP {response.status_code}); is it your team and is the token current?")
    response.raise_for_status()
    payload = response.json()
    api._save(f"my-team/{team_id}/", payload)
    return payload


def public_team_state(team_id: int, request: Callable[[str], dict | list]) -> dict:
    """Upstream's reconstruction from public endpoints. `request(url)` returns the API payload."""
    from fplrank.baseline import _patched, _upstream

    solver = _upstream()
    with _patched(solver, cached_request=request):
        return solver.generate_team_json(team_id, {})


def _with_element_types(my_data: dict, bootstrap: dict) -> dict:
    types = {e["id"]: e["element_type"] for e in bootstrap["elements"]}
    for pick in my_data.get("picks", []):
        pick.setdefault("element_type", types.get(pick["element"]))
    return my_data


def load_team_state(
    team_id: int,
    request: Callable[[str], dict | list] | None = None,
    api: FplApi | None = None,
    creds: dict[str, str] | None = None,
    login_fn: Callable[[str, str], str] = login,
) -> dict:
    """Team state (`my_data`) for `solve_ev`: exact from my-team when logged in, else estimated.

    request: cached fetcher for public URLs (as in `opt.ownership._live_inputs`); default uses `api`.
    creds:   defaults to `credentials()` (environment, then `.env`).
    The result carries `"source"`: "my-team" (exact) or "public-estimate" (fallback, warned).
    """
    api = api or FplApi()
    if request is None:

        def request(url):
            return api.get(url.split("/api/", 1)[1])

    creds = credentials() if creds is None else creds
    reason = "no FPL credentials set (see docs/team-login.md)"
    if creds:
        try:
            token = access_token(creds, login_fn)
            if token:
                my_data = fetch_my_team(team_id, token, api)
                my_data["team_id"] = team_id
                my_data["source"] = "my-team"
                return _with_element_types(my_data, request(f"{BASE_URL}/bootstrap-static/"))
        except (LoginError, requests.RequestException) as e:
            reason = str(e)

    warnings.warn(
        f"Using public data for team {team_id}: {reason}. Selling prices and free transfers are estimates.",
        stacklevel=2,
    )
    my_data = public_team_state(team_id, request)
    my_data["source"] = "public-estimate"
    return my_data


# ---------------------------------------------------------------------------------------------
# CLI: show the team state and how far the public estimate is off


def _summary(my_data: dict, names: dict[int, str]) -> str:
    t = my_data["transfers"]
    chips = [c["name"] for c in my_data.get("chips", []) if c.get("status_for_entry") in (None, "available")]
    lines = [f"source: {my_data['source']}", f"bank: {t['bank'] / 10:.1f}  free transfers: {t.get('limit')}  made: {t.get('made', 0)}"]
    if my_data["source"] == "my-team":
        lines.append(f"chips available: {', '.join(chips) or 'none'}")
    lines += [f"  {names.get(p['element'], p['element']):<20} sell {p['selling_price'] / 10:.1f}" for p in my_data["picks"]]
    return "\n".join(lines)


def _main(argv=None):
    import argparse

    p = argparse.ArgumentParser(description="Show the team state the solver will use")
    p.add_argument("team", type=int, help="FPL team (entry) id")
    args = p.parse_args(argv)

    api = FplApi()
    cache = {}

    def request(url):
        endpoint = url.split("/api/", 1)[1]
        if endpoint not in cache:
            cache[endpoint] = api.get(endpoint)
        return cache[endpoint]

    names = {e["id"]: e["web_name"] for e in request(f"{BASE_URL}/bootstrap-static/")["elements"]}
    state = load_team_state(args.team, request, api)
    print(_summary(state, names))
    if state["source"] == "my-team":
        estimate = public_team_state(args.team, request)
        sell = {p["element"]: p["selling_price"] for p in estimate["picks"]}
        diffs = [p for p in state["picks"] if sell.get(p["element"]) != p["selling_price"]]
        print(
            f"public estimate: bank {estimate['transfers']['bank'] / 10:.1f}, FTs {estimate['transfers']['limit']}, "
            f"{len(diffs)} selling price(s) differ"
        )


if __name__ == "__main__":
    sys.exit(_main())
