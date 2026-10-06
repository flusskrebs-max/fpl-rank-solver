"""The page's form as `fplrank solve` flags, and the two lines of its output the page draws (no modelling here)."""

import json
import re
import shlex
from dataclasses import dataclass, field

from fplrank.paths import UPSTREAM_DIR

EO_GROUPS = ("AE64", "E64", "elite", "top1000", "top10k", "solio", "mix")
MIX_GROUPS = ("AE64", "E64", "top1000", "top10k")  # what a custom EO mix can weigh (opt.ownership.COLLECTOR_GROUPS)
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
    mix: dict[str, float] = field(default_factory=lambda: {"AE64": 0.5, "E64": 0.5})  # weights when eo is "mix"
    target: int = 10000
    lam: float = 0.0
    points: int | None = None  # None: from the FPL API
    kappa: float | None = None  # None: cli default
    eo_decay: float = 0.7
    eo_drift: bool = True
    sims: int = 0
    his: dict = field(default_factory=dict)  # his settings that differ from his settings files (HIS_SETTINGS)
    extra: str = ""  # any of his flags, as typed on the command line


# His usual settings on the page, by section: (key, label, kind). Kinds: int, float, bool, text, gws (a list of
# GWs or player ids), "int?" (blank = his null). Everything else goes in the extra flags box.
HIS_SETTINGS = {
    "Solve": [
        ("secs", "Time limit per solve (s)", "int"),
        ("gap", "MIP gap (0 = solve to optimal)", "float"),
        ("horizon", "Weeks to plan", "int"),
        ("datasource", "Projections source", "text"),
        ("override_next_gw", "Plan from GW (blank = next GW)", "int?"),
        ("preseason", "Preseason (empty squad)", "bool"),
    ],
    "Transfers": [
        ("decay_base", "Decay base", "float"),
        ("ft_value", "Free transfer value", "float"),
        ("hit_cost", "Hit cost", "int"),
        ("weekly_hit_limit", "Hits allowed a GW", "int"),
        ("hit_limit", "Hits allowed in total (blank = no limit)", "int?"),
        ("itb_value", "Value of £0.1m in the bank", "float"),
        ("no_transfer_last_gws", "No transfers in the last N GWs", "int"),
        ("no_future_transfer", "No transfers after this GW", "bool"),
    ],
    "Chips": [
        ("use_wc", "Wildcard in GW", "gws"),
        ("use_fh", "Free hit in GW", "gws"),
        ("use_bb", "Bench boost in GW", "gws"),
        ("use_tc", "Triple captain in GW", "gws"),
    ],
    "Players (FPL ids)": [
        ("banned", "Banned", "gws"),
        ("locked", "Locked", "gws"),
        ("banned_next_gw", "Banned next GW", "gws"),
        ("locked_next_gw", "Locked next GW", "gws"),
    ],
    "Player pool and output": [
        ("xmin_lb", "Min expected minutes over the horizon", "int"),
        ("ev_per_price_cutoff", "Keep top % by EV per price", "int"),
        ("keep_top_ev_percent", "Keep top % by EV", "int"),
        ("vcap_weight", "Vice-captain weight", "float"),
        ("num_iterations", "Plans to show (iterations)", "int"),
        ("iteration_criteria", "Iteration criteria", "text"),
    ],
}


def his_defaults(data_dir=UPSTREAM_DIR / "data") -> dict:
    """His settings as his solver reads them: comprehensive_settings.json, then user_settings.json on top."""
    with open(data_dir / "comprehensive_settings.json", encoding="utf-8") as f:
        options = json.load(f)
    with open(data_dir / "user_settings.json", encoding="utf-8") as f:
        return {**options, **json.load(f)}


def parse_ids(text: str) -> list[int]:
    """'8, 10' -> [8, 10]."""
    try:
        return [int(x) for x in re.split(r"[,\s]+", text.strip()) if x]
    except ValueError:
        raise ValueError(f"expected numbers separated by commas, got {text!r}") from None


def his_flag(value) -> str:
    """One of his settings as he parses it on the command line."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list | dict):
        return json.dumps(value)
    return f"{value:g}" if isinstance(value, float) else str(value)


def mix_spec(weights: dict[str, float]) -> str:
    """{AE64: 0.4, top10k: 0.2} -> 'AE64:0.4+top10k:0.2' (`--eo`; zero weights left out)."""
    spec = "+".join(f"{g}:{w:g}" for g, w in weights.items() if w > 0)
    if not spec:
        raise ValueError("the EO mix needs at least one weight above 0")
    return spec


def solve_args(c: Choices) -> list[str]:
    """`fplrank solve` arguments for these choices (without the `solve`)."""
    args = []
    if c.team_id.strip():
        if not c.team_id.strip().isdigit():
            raise ValueError("team id must be a number")
        args += ["--team_id", c.team_id.strip()]
    if c.team_json:
        args += ["--team_data", "json"]
    for key, value in c.his.items():
        if value is not None:
            args += [f"--{key}", his_flag(value)]
    if c.mode != "plain":
        if c.eo not in EO_GROUPS:
            raise ValueError(f"unknown EO group {c.eo}")
        args += ["--eo", mix_spec(c.mix) if c.eo == "mix" else c.eo]
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
