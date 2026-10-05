"""Spike: maximise P(beat a rival by `gap`) vs maximise expected points, on a toy problem.

Not part of the real solver. It exists to check that the core formulation idea runs in
HiGHS and to make the EV-vs-rank difference concrete before designing the real thing.

Setup: pick k of n players. Scores are random, represented by S sampled scenarios.
A rival owns the k highest-mean "template" players. You need to finish `gap` points ahead.

- EV objective:   maximise the sum of means.
- Rank objective: sample average approximation (SAA) of a probability. A binary z_s per
  scenario can only be 1 if your score >= rival + gap in that scenario (big-M constraint);
  maximise the share of scenarios with z_s = 1.

Takeaway the test checks: when you are level, copying the rival is optimal for both; when
you are behind, the EV pick is identical to the rival and can never overtake, while the
rank pick swaps in high-variance differentials.
"""

import time
from dataclasses import dataclass

import highspy
import numpy as np


@dataclass
class ToyProblem:
    means: np.ndarray  # (n,)
    sds: np.ndarray  # (n,)
    rival_squad: np.ndarray  # indices the rival owns
    k: int

    def sample(self, n_scenarios: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
        """Return (player scores (S, n), rival scores (S,)) for fresh scenarios."""
        rng = np.random.default_rng(seed)
        scores = rng.normal(self.means, self.sds, size=(n_scenarios, len(self.means)))
        return scores, scores[:, self.rival_squad].sum(axis=1)


def make_toy(n_template: int = 6, n_differential: int = 6, k: int = 4, seed: int = 0) -> ToyProblem:
    rng = np.random.default_rng(seed)
    means = np.concatenate([rng.uniform(5.5, 6.5, n_template), rng.uniform(4.5, 5.5, n_differential)])
    sds = np.concatenate([np.full(n_template, 2.0), np.full(n_differential, 5.0)])
    rival_squad = np.argsort(-means[:n_template])[:k]
    return ToyProblem(means=means, sds=sds, rival_squad=rival_squad, k=k)


def pick_ev(problem: ToyProblem) -> list[int]:
    return sorted(int(i) for i in np.argsort(-problem.means)[: problem.k])


def pick_rank(problem: ToyProblem, scores: np.ndarray, rival: np.ndarray, gap: float, secs: float = 60) -> list[int]:
    """Choose k players maximising the share of scenarios where score >= rival + gap."""
    n_scen, n = scores.shape
    m = highspy.Highs()
    m.setOptionValue("output_flag", False)
    m.setOptionValue("time_limit", float(secs))
    binary = highspy.HighsVarType.kInteger
    x = m.addVariables(range(n), lb=0, ub=1, type=binary, name_prefix="x")
    z = m.addVariables(range(n_scen), lb=0, ub=1, type=binary, name_prefix="z")

    m.addConstr(m.qsum(x[i] for i in range(n)) == problem.k)
    worst = np.sort(scores, axis=1)[:, : problem.k].sum(axis=1)  # lowest score any squad can get
    for s in range(n_scen):
        big_m = max(0.0, rival[s] + gap - worst[s])
        # z_s = 1  =>  sum_i scores[s, i] x_i >= rival_s + gap
        m.addConstr(m.qsum(scores[s, i] * x[i] for i in range(n)) - big_m * z[s] >= rival[s] + gap - big_m)

    m.setObjective(m.qsum(z[s] for s in range(n_scen)) * (1.0 / n_scen), sense=highspy.ObjSense.kMaximize)
    m.run()
    values = m.getSolution().col_value
    return sorted(i for i in range(n) if values[x[i].index] > 0.5)


def success_rate(choice: list[int], scores: np.ndarray, rival: np.ndarray, gap: float) -> float:
    # small tolerance: identical squads summed in a different order can differ by ~1e-15
    return float(np.mean(scores[:, choice].sum(axis=1) >= rival + gap - 1e-9))


if __name__ == "__main__":
    problem = make_toy()
    train_scores, train_rival = problem.sample(400, seed=1)
    test_scores, test_rival = problem.sample(20_000, seed=2)
    ev_choice = pick_ev(problem)
    print(f"EV pick {ev_choice}  (rival owns {sorted(problem.rival_squad.tolist())})")
    for gap in [0, 3, 6, 10]:
        start = time.perf_counter()
        rank_choice = pick_rank(problem, train_scores, train_rival, gap)
        elapsed = time.perf_counter() - start
        print(
            f"gap {gap:>2}: P(EV pick succeeds) = {success_rate(ev_choice, test_scores, test_rival, gap):.2f}   "
            f"rank pick {rank_choice} P = {success_rate(rank_choice, test_scores, test_rival, gap):.2f}   "
            f"E[pts] EV {problem.means[ev_choice].sum():.1f} vs rank {problem.means[rank_choice].sum():.1f}   "
            f"({elapsed:.1f}s)"
        )
