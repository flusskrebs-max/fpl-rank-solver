"""The solver page: `uv run fplrank page` opens it at http://localhost:8501.

Fills in the flags for `fplrank solve`, runs it as a separate process and shows what it prints. The last
choices are kept in data/ui_settings.json (git-ignored) so the team id is there next week.
"""

import dataclasses
import json
import os
import subprocess
import sys

import pandas as pd
import streamlit as st

from fplrank.paths import DATA_DIR, PROJECT_ROOT, UPSTREAM_DIR
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
TEAM_JSON = UPSTREAM_DIR / "data" / "team.json"  # where his bookmarklet's team goes (docs/weekly-run.md)


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
    if team_json and not TEAM_JSON.exists():
        st.sidebar.warning("No team.json yet: save it from the bookmarklet (docs/weekly-run.md, step 3) or untick this box.")

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
        if mode == "target":
            target = st.sidebar.number_input("Target rank", 1, 10_000_000, saved.target, step=1000)
        else:
            lam = st.sidebar.number_input("λ", -1.0, 1.0, saved.lam, step=0.05, format="%.2f")

    with st.sidebar.expander("More options"):
        if mode == "target":
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


def run(args: list[str], box, bar) -> tuple[int, str]:
    """`fplrank solve` in its own process, its output shown in `box` as it arrives and its λ (or simulation) count in
    `bar`. The process is stopped if the page stops first (a widget changed, Solve pressed again, the tab closed)."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "fplrank.cli", "solve", *args],
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    lines = []
    try:
        for line in proc.stdout:
            lines.append(line)
            if step := progress(line):
                bar.progress(step[0] / step[1], text=step[2])
            box.code("".join(lines[-40:]), language=None)
        return proc.wait(), "".join(lines)
    finally:
        if proc.poll() is None:
            proc.kill()


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
        st.caption("λ below 0 leans towards differentials (more risk against the field); above 0 towards players the field owns.")
    st.subheader("Full output")
    st.code(output, language=None)


def main() -> None:
    st.set_page_config(page_title="Risky Solver", layout="wide")
    st.title("Risky Solver")
    st.caption("Fills in `fplrank solve` and runs it on this PC. Solio files and team.json go where docs/weekly-run.md says.")
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
