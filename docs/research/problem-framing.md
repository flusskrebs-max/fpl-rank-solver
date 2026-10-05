# Problem framing: optimising for rank, not points

Starter notes for the Phase 1 brainstorm. Nothing here is decided.

## Why points and rank differ

Your rank is set by how many managers score more than you. Over a GW, what moves you against
the managers around rank X is your points *minus theirs*, and much of their squad is the same as
yours. Two consequences:

- Owning a player everyone owns barely changes your rank whatever he scores. Not owning him is
  a bet against him.
- The *spread* of your relative score matters as much as its mean. If you are ahead of the target,
  you want low spread (cover the template). If you are behind, you need spread (differentials,
  captaincy punts) because a safe, average week cannot close the gap.

An EV solver ignores both. It will happily copy the template when you are 200 points off the target.

## The key identity

For one GW, let `m_p` be your multiplier on player p (0 benched or not owned, 1 starting, 2 captain,
3 triple captain), and `EO_p` the effective ownership among managers near rank X (the average
multiplier, so a heavily captained player can have EO above 100%). Then

```
your points − typical rank-X manager's points  =  Σ_p (m_p − EO_p) · points_p  −  (your hits − their hits)
```

Players with `m_p = EO_p` drop out entirely. Everything else is a bet. This relative score is linear in
the decisions, which is good news for a MILP.

## The objective

Target: maximise `P(final rank ≤ X)`. A first approximation is `P(your final total ≥ T_X)`, where
`T_X` is the total that rank X will need, itself uncertain. With a current gap `G` (points behind rank X)
and future relative score `Δ` over the remaining GWs:

```
P(success) ≈ P(Δ ≥ G)  ≈  Φ((μ_Δ − G) / σ_Δ)      under a normal approximation
```

- `G > μ_Δ` (behind): raising `σ_Δ` raises the probability.
- `G < μ_Δ` (ahead): lowering `σ_Δ` raises it.

The normal approximation is too crude for FPL's lumpy, fat-tailed scores, but it shows the shape.

## Formulation options (to discuss)

1. **Sample average approximation (SAA).** Draw S scenarios; a binary per scenario is 1 only when
   you beat the threshold in that scenario; maximise their share. Exact in the limit, but big-M
   formulations relax badly. Spike (`src/fplrank/opt/toy.py`): 12 players, choose 4, 400 scenarios
   took 20 to 40 s in HiGHS. The real problem is ~600 players over several GWs, so this will not
   scale as is.
2. **LP-friendly risk surrogates.** Optimise mean relative score plus or minus λ × a linear risk
   measure (mean absolute deviation, CVaR, downside deviation) computed over scenarios. λ's sign and
   size come from the rank situation. Solves like the current model with extra continuous variables.
3. **Generate, then simulate.** Use the MILP to produce many diverse candidate plans (different λ,
   forced differentials, captain options, upstream's iteration feature), then score each with a full
   Monte Carlo estimate of P(rank ≤ X) and pick the best. Probably the most practical v1.
4. **Decomposition.** The week's decision space is small (a few transfers, captain, bench order) even
   though the plan space is huge. Enumerate this-week moves, optimise the rest by EV or surrogate.
5. **Dynamic risk appetite.** A season-long target makes this a sequential problem. A value function
   over (gap, GWs left) could set λ each week rather than solving the full stochastic programme.

HiGHS handles LP and MILP well; it does not solve mixed-integer QP, so any variance term must be
linearised or handled outside the MILP.

## Relevant prior work

- Hunter, Vielma & Zaman, *Picking Winners Using Integer Programming* (2016), arXiv:1604.01455.
  Daily fantasy: pick a portfolio of lineups to maximise the chance one of them wins a large
  contest, using means, variances and covariances in sequential integer programmes.
- Haugh & Singal, *How to Play Fantasy Sports Strategically (and Win)*, Management Science (2021),
  SSRN 3393127. Models opponents' picks explicitly and optimises against them, very close to the EO idea.
- Luedtke & Ahmed (2008), sample approximation for chance-constrained programmes (SIAM J. Optim.).
- Rockafellar & Uryasev (2000), CVaR optimisation as a linear programme.
- Sertalp Bilal's YouTube series on building the original solver (linked in the upstream README).

## Glossary

- **xPts / xMins**: projected points / minutes for a player in a GW.
- **EO (effective ownership)**: average multiplier on a player across a group of managers (captaincy counts double).
- **Template**: the set of players most of the field owns. **Differential**: a low-EO pick.
- **FT / hit**: free transfer / −4 points for each transfer beyond your FTs.
- **WC, FH, BB, TC**: Wildcard, Free Hit, Bench Boost, Triple Captain chips.
- **SAA**: sample average approximation, optimising an expectation or probability over sampled scenarios.
- **Big-M**: linking a binary to a constraint with a large constant; easy to write, weak to solve.
- **CVaR**: conditional value at risk, the average of the worst α% of outcomes; LP-representable.
