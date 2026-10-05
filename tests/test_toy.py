import pytest

from fplrank.opt.toy import make_toy, pick_ev, pick_rank, success_rate


@pytest.mark.slow
def test_rank_objective_beats_ev_when_chasing():
    problem = make_toy()
    train_scores, train_rival = problem.sample(150, seed=1)
    test_scores, test_rival = problem.sample(20_000, seed=2)
    ev_choice = pick_ev(problem)

    # level with the rival: copying them is optimal for both objectives
    level = pick_rank(problem, train_scores, train_rival, gap=0)
    assert success_rate(level, test_scores, test_rival, 0) == pytest.approx(1.0)

    # behind the rival: the EV pick is the rival's team and cannot overtake
    chasing = pick_rank(problem, train_scores, train_rival, gap=4)
    assert success_rate(ev_choice, test_scores, test_rival, 4) == 0.0
    assert success_rate(chasing, test_scores, test_rival, 4) > 0.15
    assert set(chasing) - set(problem.rival_squad.tolist())  # took at least one differential
