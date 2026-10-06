"""The solver page's form -> `fplrank solve` flags, and the output lines it draws."""

import pytest

from fplrank import cli
from fplrank.opt import ownership
from fplrank.ui.command import Choices, chosen_lam, command_line, p_by_lam, solve_args


def test_target_run():
    args = solve_args(Choices(team_id="123", target=10000, sims=50))
    assert args == ["--team_id", "123", "--eo", "AE64", "--target", "10000", "--eo_decay", "0.7", "--eo_drift", "true", "--sims", "50"]


def test_fixed_lam_and_his_flags():
    c = Choices(team_id="1", team_json=True, mode="lam", lam=0.1, eo="solio", eo_drift=False, horizon=5, extra='--banned "[12, 34]"')
    assert solve_args(c) == [
        "--team_id", "1", "--team_data", "json", "--horizon", "5", "--eo", "solio", "--lam", "0.1",
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
