"""The solver page's form -> `fplrank solve` flags, and the output lines it draws."""

import pytest

from fplrank import cli
from fplrank.opt import ownership
from fplrank.ui.command import HIS_SETTINGS, Choices, chosen_lam, command_line, his_defaults, p_by_lam, parse_ids, progress, solve_args


def test_target_run():
    args = solve_args(Choices(team_id="123", target=10000, sims=50))
    assert args == ["--team_id", "123", "--eo", "AE64", "--target", "10000", "--eo_decay", "0.7", "--eo_drift", "true", "--sims", "50"]


def test_fixed_lam_and_his_flags():
    his = {"horizon": 5, "secs": 120, "use_wc": [8], "decay_base": 0.85, "preseason": True, "hit_limit": None}
    c = Choices(team_id="1", team_json=True, mode="lam", lam=0.1, eo="solio", eo_drift=False, his=his, extra='--banned "[12, 34]"')
    assert solve_args(c) == [
        "--team_id", "1", "--team_data", "json", "--horizon", "5", "--secs", "120", "--use_wc", "[8]", "--decay_base", "0.85",
        "--preseason", "true", "--eo", "solio", "--lam", "0.1", "--target", "10000",
        "--eo_decay", "0.7", "--eo_drift", "false", "--banned", "[12, 34]",
    ]  # fmt: skip


def test_plain_is_his_solver_only():
    assert solve_args(Choices(team_id="7", mode="plain", sims=10)) == ["--team_id", "7", "--sims", "10"]


def test_flags_parse_as_the_cli_reads_them():
    c = Choices(team_id="9", points=300, kappa=0.5, eo_decay=0, extra="--horizon 3")
    ours, theirs = cli.parser().parse_known_args(solve_args(c))
    assert (ours.eo, ours.target, ours.points, ours.kappa, ours.eo_decay, ours.eo_drift) == ("AE64", 10000, 300, 0.5, 0.0, True)
    assert theirs == ["--team_id", "9", "--horizon", "3"]
    assert Choices().eo_decay == ownership.EO_DECAY


def test_bad_team_id():
    with pytest.raises(ValueError):
        solve_args(Choices(team_id="12a"))


def test_command_line_quotes():
    assert command_line(["--banned", "[1, 2]"]) == "uv run fplrank solve --banned '[1, 2]'"


def test_output_lines():
    out = "EO x\nP by λ: -0.1 12%, 0 14%, 0.1 21%\n...\n--- Sertalp's solver, plan for λ = 0.1 ---\nplan"
    assert p_by_lam(out) == {-0.1: 0.12, 0.0: 0.14, 0.1: 0.21}
    assert chosen_lam(out) == 0.1
    assert p_by_lam("no target") == {} and chosen_lam("") is None


def test_custom_mix():
    c = Choices(eo="mix", mix={"AE64": 0.4, "E64": 0.4, "top1000": 0.0, "top10k": 0.2})
    args = solve_args(c)
    assert args[args.index("--eo") + 1] == "AE64:0.4+E64:0.4+top10k:0.2"
    assert ownership.group_weights(args[args.index("--eo") + 1]) == pytest.approx({"AE64": 0.4, "E64": 0.4, "top10k": 0.2})
    with pytest.raises(ValueError):
        solve_args(Choices(eo="mix", mix={"AE64": 0.0}))


def test_his_settings_exist_in_his_files():
    defaults = his_defaults()
    assert all(key in defaults for settings in HIS_SETTINGS.values() for key, _, _ in settings)
    assert parse_ids("8, 10 12") == [8, 10, 12] and parse_ids(" ") == []
    with pytest.raises(ValueError):
        parse_ids("8, Salah")


def test_progress_lines():
    assert progress("  3/9: λ = -0.1 solved in 12s\n") == (3, 9, "λ 3/9 solved (last: λ = -0.1)")
    assert progress("  4/50 done (30s)") == (4, 50, "simulation 4/50 done")
    assert progress("Running HiGHS 1.15.1") is None


def test_fixed_lam_reports_p_only_when_points_can_be_found():
    assert "--target" not in solve_args(Choices(mode="lam", lam=-0.2))
    assert solve_args(Choices(mode="lam", lam=-0.2, points=358))[2:8] == ["--lam", "-0.2", "--target", "10000", "--points", "358"]
