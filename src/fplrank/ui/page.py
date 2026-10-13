"""The solver page: `uv run fplrank page` opens it at http://localhost:8501.

Fills in the flags for `fplrank solve`, runs it as a separate process and shows what it prints. The last
choices are kept in data/ui_settings.json (git-ignored) so the team id is there next week.
"""

import contextlib
import dataclasses
import json
import os
import re
import signal
import subprocess
import sys

import pandas as pd
import streamlit as st

from fplrank.paths import DATA_DIR, PROJECT_ROOT
from fplrank.ui import setup
from fplrank.ui.command import (
    EO_GROUPS,
    HIS_SETTINGS,
    MIX_GROUPS,
    MODES,
    Choices,
    chosen_lam,
    command_line,
    his_defaults,
    p_by_lam,
    parse_ids,
    progress,
    solve_args,
)

SETTINGS = DATA_DIR / "ui_settings.json"


def load_choices() -> Choices:
    try:
        saved = json.loads(SETTINGS.read_text(encoding="utf-8"))
        names = {f.name for f in dataclasses.fields(Choices)}
        return Choices(**{k: v for k, v in saved.items() if k in names})
    except (OSError, ValueError, TypeError):
        return Choices()


def save_choices(c: Choices) -> None:
    SETTINGS.parent.mkdir(exist_ok=True)
    SETTINGS.write_text(json.dumps(dataclasses.asdict(c), indent=2), encoding="utf-8")


def form(saved: Choices) -> Choices:
    """The sidebar. Raises ValueError for an entry that can't be read (shown above the command)."""
    st.sidebar.header("Team")
    team_id = st.sidebar.text_input("FPL team id", saved.team_id)
    team_json = st.sidebar.checkbox(
        "Use team.json from the bookmarklet", saved.team_json, help="His --team_data json: for after transfers or price changes"
    )
    if team_json and not setup.TEAM_JSON.exists():
        st.sidebar.warning("No team.json yet: paste it under Weekly setup, or untick this box.")

    st.sidebar.header("Rank goal")
    mode = st.sidebar.radio("Mode", list(MODES), list(MODES).index(saved.mode), format_func=MODES.get)
    eo, mix, target, lam, points, kappa = saved.eo, saved.mix, saved.target, saved.lam, saved.points, saved.kappa
    eo_decay, eo_drift = saved.eo_decay, saved.eo_drift
    if mode != "plain":
        eo = st.sidebar.selectbox(
            "Ownership (EO) from", EO_GROUPS, EO_GROUPS.index(saved.eo), format_func=lambda g: "Custom mix" if g == "mix" else g
        )
        if eo == "mix":
            cols = st.sidebar.columns(2)
            mix = {
                g: cols[i % 2].number_input(f"{g} weight", 0.0, 1.0, float(saved.mix.get(g, 0.0)), step=0.05, key=f"mix_{g}")
                for i, g in enumerate(MIX_GROUPS)
            }
            st.sidebar.caption("Weights are scaled to add up to 1. The line's drift uses the AE64/E64 part only.")
        if mode == "lam":
            lam = st.sidebar.number_input("λ", -1.0, 1.0, saved.lam, step=0.05, format="%.2f")
        target = st.sidebar.number_input("Target rank", 1, 10_000_000, saved.target, step=1000)

    with st.sidebar.expander("More options"):
        if mode != "plain":
            p = st.number_input("Our points now (0 = from the FPL API)", 0, 5000, saved.points or 0)
            points = p or None
            k = st.number_input("κ, share of our edge that counts (0 = default 0.75)", 0.0, 1.0, saved.kappa or 0.0, step=0.05)
            kappa = k or None
        if mode != "plain":
            eo_decay = st.number_input("λ decay a GW (--eo_decay; 0 = next GW only)", 0.0, 1.0, saved.eo_decay, step=0.1)
            eo_drift = st.checkbox("EO drifts towards wildcard templates (--eo_drift)", saved.eo_drift)
        sims = st.number_input("Simulations (0 = off)", 0, 500, saved.sims, step=10)

    st.sidebar.header("Sertalp's settings")
    st.sidebar.caption("Filled in from his settings files; only what you change is passed on.")
    if mode == "target":
        st.sidebar.caption(
            "With a target the solver runs once per λ (9 solves), plus 3 wildcard solves for the EO drift, so the time limit"
            " applies to each."
        )
    his, errors = his_settings(saved.his)
    extra = st.sidebar.text_input("Any other flags of his", saved.extra, placeholder='--booked_transfers "[...]"')
    if errors:
        raise ValueError("; ".join(errors))

    return Choices(
        team_id=team_id,
        team_json=team_json,
        mode=mode,
        eo=eo,
        mix=mix,
        target=int(target),
        lam=float(lam),
        points=points,
        kappa=kappa,
        eo_decay=float(eo_decay),
        eo_drift=eo_drift,
        sims=int(sims),
        his=his,
        extra=extra,
    )


def his_settings(saved: dict) -> tuple[dict, list[str]]:
    """One expander per section of HIS_SETTINGS, starting from what was last used. Returns what differs from his
    files, and any entries that can't be read."""
    defaults = his_defaults()
    changed, errors = {}, []
    for section, settings in HIS_SETTINGS.items():
        with st.sidebar.expander(section, expanded=section == "Solve"):
            for key, label, kind in settings:
                default = defaults.get(key)
                now = saved.get(key, default)
                w = f"his_{key}"
                try:
                    if kind == "int":
                        value = int(st.number_input(label, value=int(now or 0), step=1, key=w))
                    elif kind == "float":
                        value = float(st.number_input(label, value=float(now or 0), step=0.01, format="%.3f", key=w))
                    elif kind == "bool":
                        value = st.checkbox(label, bool(now), key=w)
                    elif kind == "gws":
                        value = parse_ids(st.text_input(label, ", ".join(str(x) for x in now or []), key=w))
                    elif kind == "int?":
                        text = st.text_input(label, "" if now is None else str(now), key=w).strip()
                        value = int(text) if text else None
                    else:
                        value = st.text_input(label, str(now or ""), key=w).strip()
                except ValueError as e:
                    errors.append(f"{label}: {e}")
                    continue
                if value != default:
                    changed[key] = value
    return changed, errors


def run(args: list[str], box, bar, module: tuple[str, ...] = ("fplrank.cli", "solve"), step=progress) -> tuple[int, str]:
    """`fplrank solve` (or another `module`) in its own process, its output shown in `box` as it arrives and its
    progress (`step` of a line) in `bar`. The process is stopped if the page stops first (a widget changed, Solve
    pressed again, the tab closed)."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-m", *module, *args],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        start_new_session=os.name != "nt",  # its own process group, so its solver processes can be stopped with it
    )
    lines = []
    try:
        for line in proc.stdout:
            lines.append(line)
            if done := step(line):
                bar.progress(done[0] / done[1], text=done[2])
            box.code("".join(lines[-40:]), language=None)
        return proc.wait(), "".join(lines)
    finally:
        if proc.poll() is None:
            stop(proc)


def stop(proc: subprocess.Popen) -> None:
    """Stop `fplrank solve` and the solver processes it started (`--workers`)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)


def results(output: str) -> None:
    lam = chosen_lam(output)
    ps = p_by_lam(output)
    cols = st.columns(2)
    if lam is not None:
        cols[0].metric("λ chosen", f"{lam:g}")
    if ps and lam in ps:
        cols[1].metric("P(reaching the target)", f"{ps[lam]:.0%}", f"{ps[lam] - ps.get(0.0, ps[lam]):+.0%} on λ = 0")
    if ps:
        st.subheader("P by λ")
        chart = pd.DataFrame({"λ": [f"{k:g}" for k in sorted(ps)], "P": [ps[k] for k in sorted(ps)]}).set_index("λ")
        st.bar_chart(chart, y="P")
    st.subheader("Full output")
    st.code(output, language=None)


def weekly_setup() -> None:
    """Steps 1-4 of docs/weekly-run.md as buttons: latest code, team from the bookmarklet, Solio files, the
    field's squads."""
    projections_age = setup.age(setup.SOLIO_CSV)
    with st.container(border=True):
        for kind, msg in st.session_state.pop("setup_msg", []):
            getattr(st, kind)(msg)
        code, team, solio, field = st.columns(4)

        code.markdown("**1. Code**")
        code.caption(f"Running: {setup.code_version()}")
        if code.button("Get the latest code"):
            changed, out = setup.update_code()
            if changed:
                code.warning("Updated. Close the solver window and open it again (the desktop shortcut) to use the new code.")
            else:
                code.info(out or "No change.")

        team.markdown("**2. Team**")
        team_age = setup.age(setup.TEAM_JSON)
        team.caption(
            "With only a team id, your team is read from FPL at each solve. After transfers or price changes, click"
            " the bookmarklet on the FPL site and paste here." + (f" team.json saved {team_age}." if team_age else " No team.json yet.")
        )
        pasted = team.text_area(
            "Team from the bookmarklet",
            height=68,
            placeholder='{"picks": [...',
            label_visibility="collapsed",
            key=f"team_paste_{st.session_state.get('pastes', 0)}",  # a new key empties the box after a save
        )
        if team.button("Save team"):
            try:
                saved = setup.save_team(pasted)
            except ValueError as e:
                team.error(str(e))
            else:
                choices = load_choices()
                choices.team_json = True
                save_choices(choices)
                st.session_state["pastes"] = st.session_state.get("pastes", 0) + 1
                st.session_state["setup_msg"] = [("success", f"Team saved ({setup.team_summary(saved)}); the solve now uses it.")]
                st.rerun()

        solio.markdown("**3. Solio files**")
        eo_files = sorted(setup.SOLIO_EO_DIR.glob("*.csv"))
        solio.caption(
            f"Projections: {f'saved {projections_age}' if projections_age else 'none yet'}."
            f" EO forecast: {f'{eo_files[-1].name}' if eo_files else 'none yet (only needed for EO from solio)'}."
            " An EO table (last GW's EO, such as the top 10k CSV) is turned into the EO forecast."
        )
        found = setup.newest_downloads()
        if solio.button("Use the newest from Downloads", disabled=not found, help=f"Looks in {setup.DOWNLOADS}"):
            st.session_state["setup_msg"] = [install(p.read_bytes(), p.name) for p in found.values()]
            st.rerun()
        if found:
            solio.caption("Found: " + ", ".join(f"{p.name} ({setup.age(p)})" for p in found.values()))
        else:
            solio.caption(f"No Solio export from the last {setup.RECENT_DAYS} days in Downloads.")
        dropped = solio.file_uploader("Or drop the files here", type="csv", accept_multiple_files=True, key="solio_drop")
        if dropped and solio.button("Save dropped files"):
            st.session_state["setup_msg"] = [install(f.getvalue(), f.name) for f in dropped]
            st.rerun()
        table = solio.text_area(
            "Or paste an EO table",
            height=68,
            placeholder="Player,Team,EOTop10k,...",
            key=f"eo_paste_{st.session_state.get('eo_pastes', 0)}",  # a new key empties the box after a build
        )
        if solio.button("Build EO forecast", disabled=not table.strip()):
            st.session_state["setup_msg"] = [install(table.encode("utf-8"), "the pasted table")]
            st.session_state["eo_pastes"] = st.session_state.get("eo_pastes", 0) + 1
            st.rerun()

        field.markdown("**4. Field's squads**")
        behind, text = setup.squads_summary(setup.squads_gw(), setup.last_deadline())
        field.caption(
            "Every AE64 and E64 manager's squad, the top 1000 and a top-10k sample, from FPL: what the EO forecast is"
            " built from. Fetching a new GW takes about 5 minutes."
        )
        (field.warning if behind else field.caption)(text)
        if field.button("Get the field's squads", type="primary" if behind else "secondary"):
            with field.status("Getting the squads…", expanded=True) as status:
                code_, out = run([], st.empty(), st.progress(0.0, text="Starting"), module=setup.COLLECT, step=collect_progress)
                status.update(label="Done" if code_ == 0 else "Stopped with an error", state="complete" if code_ == 0 else "error")
            if code_ == 0:
                st.session_state["setup_msg"] = [
                    ("success", "Squads updated: " + setup.squads_summary(setup.squads_gw(), setup.last_deadline())[1])
                ]
            else:
                st.session_state["setup_msg"] = [
                    ("error", "Getting the squads stopped. It picks up where it left off; last lines:\n\n" + out[-800:])
                ]
            st.rerun()


def collect_progress(line: str) -> tuple[int, int, str] | None:
    """(done, total, text) from the collector's `  50/2022 managers done` lines."""
    if m := re.search(r"(\d+)/(\d+) managers done", line):
        return int(m[1]), int(m[2]), f"{m[1]} of {m[2]} managers"
    return None


def install(data: bytes, name: str) -> tuple[str, str]:
    try:
        kind, gws, dest, note = setup.install(data)
    except (ValueError, OSError) as e:  # OSError: no FPL bootstrap for an EO table (API down, no snapshot)
        return "error", f"{name}: {e}"
    span = f"GW{min(gws)}" + (f"-{max(gws)}" if max(gws) > min(gws) else "")
    if kind == "eo table":
        return (
            "warning" if note else "success"
        ), f"EO forecast for {span} built from {name} (as {dest.name}, last GW's EO carried forward)." + (f" {note}." if note else "")
    what = "Projections" if kind == "projections" else "EO forecast"
    return "success", f"{what} for {span} saved from {name} (as {dest.name})."


def main() -> None:
    st.set_page_config(page_title="Risky Solver", layout="wide")
    st.title("Risky Solver")
    st.caption("Fills in `fplrank solve` and runs it on this PC.")
    weekly_setup()
    try:
        choices = form(load_choices())
        args = solve_args(choices)
    except ValueError as e:  # a bad team id or list of GWs, or unbalanced quotes in the extra flags
        st.error(str(e))
        return
    st.markdown("**What the button runs**")
    st.code(command_line(args), language="powershell")
    if not st.sidebar.button("Solve", type="primary", use_container_width=True):
        if "output" in st.session_state:
            results(st.session_state["output"])
        return
    save_choices(choices)
    with st.status("Solving…", expanded=True) as status:
        first = "Solving λ = 0" + (" and the wildcard templates" if choices.mode != "plain" and choices.eo_drift else "")
        code, output = run(args, st.empty(), st.progress(0.0, text=first))
        status.update(
            label="Done" if code == 0 else f"Stopped with an error (exit code {code})",
            state="complete" if code == 0 else "error",
            expanded=code != 0,  # done: fold the live log away so the result sits right under it
        )
    st.session_state["output"] = output
    results(output)


main()
