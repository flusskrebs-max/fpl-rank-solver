"""The page's form as `fplrank solve` flags, and the two lines of its output the page draws (no modelling here)."""

import re
import shlex
from dataclasses import dataclass

EO_GROUPS = ("AE64", "E64", "elite", "top1000", "top10k", "solio")
MODES = {
    "target": "Choose λ for a target rank",
    "lam": "Fix λ",
    "plain": "Sertalp's solver only (no EO)",
}


@dataclass
class Choices:
    team_id: str = ""
    team_json: bool = False  # his --team_data json (team.json from his bookmarklet)
    mode: str = "target"
    eo: str = "AE64"
    target: int = 10000
    lam: float = 0.0
    points: int | None = None  # None: from the FPL API
    kappa: float | None = None  # None: cli default
    eo_decay: float = 0.7
    eo_drift: bool = True
    horizon: int | None = None  # None: his settings file
    sims: int = 0
    extra: str = ""  # any of his flags, as typed on the command line


def solve_args(c: Choices) -> list[str]:
    """`fplrank solve` arguments for these choices (without the `solve`)."""
    args = []
    if c.team_id.strip():
        if not c.team_id.strip().isdigit():
            raise ValueError("team id must be a number")
        args += ["--team_id", c.team_id.strip()]
    if c.team_json:
        args += ["--team_data", "json"]
    if c.horizon:
        args += ["--horizon", str(c.horizon)]
    if c.mode != "plain":
        if c.eo not in EO_GROUPS:
            raise ValueError(f"unknown EO group {c.eo}")
        args += ["--eo", c.eo]
        if c.mode == "target":
            args += ["--target", str(c.target)]
            if c.points is not None:
                args += ["--points", str(c.points)]
            if c.kappa is not None:
                args += ["--kappa", f"{c.kappa:g}"]
        else:
            args += ["--lam", f"{c.lam:g}"]
        args += ["--eo_decay", f"{c.eo_decay:g}", "--eo_drift", "true" if c.eo_drift else "false"]
    if c.sims:
        args += ["--sims", str(c.sims)]
    return args + shlex.split(c.extra)


def command_line(args: list[str]) -> str:
    """What to type in PowerShell for the same run."""
    return " ".join(["uv run fplrank solve", *(shlex.quote(a) for a in args)])


P_BY_LAM = re.compile(r"^P by λ: (.+)$", re.MULTILINE)
CHOSEN = re.compile(r"^--- Sertalp's solver, plan for λ = (\S+) ---$", re.MULTILINE)


def p_by_lam(output: str) -> dict[float, float]:
    """λ -> P(target) from the `P by λ:` line, or {} when the run had no target."""
    m = P_BY_LAM.search(output)
    if not m:
        return {}
    pairs = (item.strip().rsplit(" ", 1) for item in m.group(1).split(","))
    return {float(lam): float(p.rstrip("%")) / 100 for lam, p in pairs}


def chosen_lam(output: str) -> float | None:
    m = CHOSEN.search(output)
    return float(m.group(1)) if m else None
