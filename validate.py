"""Validation suite. Run before trusting anything the model says."""
import sys
from collections import Counter

import numpy as np
import pandas as pd

sys.path.insert(0, "/home/claude/ffsim")
import ffsim as ff
from ffsim.draft import ARCHETYPES, run_draft

pd.set_option("display.width", 160)


def hr(t):
    print("\n" + "=" * 74)
    print(t)
    print("=" * 74)


# ---------------------------------------------------------------- pick maps
hr("1. PICK MAPS  (hand-computed from the snake, must match exactly)")
lg2 = ff.League(teams=10, slot=2)
lg6 = ff.League(teams=10, slot=6)
exp2 = [2, 19, 22, 39, 42, 59, 62, 79, 82, 99, 102]
exp6 = [6, 15, 26, 35, 46, 55, 66, 75, 86, 95, 106]
got2, got6 = lg2.pick_numbers()[:11], lg6.pick_numbers()[:11]
print(f"slot 2 : {got2}   {'OK' if got2 == exp2 else 'MISMATCH ' + str(exp2)}")
print(f"slot 6 : {got6}   {'OK' if got6 == exp6 else 'MISMATCH ' + str(exp6)}")
print("\nhedge window by slot (expect symmetric 1,3,5,7,9,9,7,5,3,1):")
print("  ", [ff.League(teams=10, slot=s).hedge_window() for s in range(1, 11)])

# ------------------------------------------------------------------- knobs
hr("2. CONFIG KNOBS  (top VOR by position must respond correctly)")
pool = ff.make_pool()
for teams, sc, label in [(10, "half_ppr", "10-team half"),
                         (12, "half_ppr", "12-team half"),
                         (10, "ppr", "10-team PPR"),
                         (10, "standard", "10-team std")]:
    lg = ff.League(teams=teams, slot=6, scoring=getattr(ff.Scoring, sc)())
    b = ff.build_board(pool, lg)
    vals = {p: round(b.loc[b.position == p, "vor"].max()) for p in ["QB", "RB", "WR", "TE"]}
    print(f"  {label:<15} {vals}")
print("\n  expect: 12-team > 10-team everywhere; PPR lifts WR/TE/RB, leaves QB flat")

# ----------------------------------------------------------- positional runs
hr("3. POSITIONAL RUNS  (a sim without cascades says 'you can always wait')")
board = ff.build_board(pool, lg6)
rng = np.random.default_rng(3)
field_ = ff.default_field(lg6, rng)
runs, total = 0, 0
for t in range(40):
    r = run_draft(board, lg6, ff.PRESETS["balanced"], field_, np.random.default_rng([3, t]))
    order = [None] * (lg6.total_picks)
    for slot, idxs in r.items():
        for k, idx in enumerate(idxs):
            order[lg6.pick_numbers(slot)[k] - 1] = board["position"].iloc[idx]
    for i in range(len(order) - 4):
        window = order[i:i + 5]
        total += 1
        if max(Counter(window).values()) >= 4:
            runs += 1
print(f"  windows of 5 picks containing 4+ of one position: {runs / total:.1%}")
print("  (0% would mean the opponent model has no contagion at all)")

# --------------------------------------------------------- ADP calibration
hr("4. AVAILABILITY CALIBRATION  (predicted vs actual survival to a pick)")
checks = [15, 26, 46, 75]
sims = 60
actual = {p: [] for p in checks}
for t in range(sims):
    r = run_draft(board, lg6, ff.PRESETS["balanced"], field_, np.random.default_rng([9, t]))
    taken_order = np.zeros(len(board), dtype=int)
    for slot, idxs in r.items():
        for k, idx in enumerate(idxs):
            taken_order[idx] = lg6.pick_numbers(slot)[k]
    for p in checks:
        actual[p].append(taken_order >= p)
print(f"  {'pick':>6}{'predicted':>12}{'actual':>10}   (mean survival prob, top 60 ADP)")
top = board.nsmallest(60, "adp").index
for p in checks:
    pred = ff.availability(board, p).loc[top].mean()
    act = np.mean([a[top].mean() for a in actual[p]])
    print(f"  {p:>6}{pred:>12.1%}{act:>10.1%}")

# ------------------------------------------------------ strategy comparison
hr("5. STRATEGY COMPARISON  -- slot 6, 10-team half PPR, default field")
N = 300
summary, _ = ff.evaluate(pool, lg6, ["bpa", "balanced", "ceiling", "safe", "zero_rb"],
                         n_sims=N, seed=11)
print(summary.to_string(index=False))
print(f"\n  n = {N} seasons per strategy, common random numbers")

# ------------------------------------------- favourite vs underdog dynamics
hr("6. DOES VARIANCE HELP THE UNDERDOG AND HURT THE FAVOURITE?")
print("  Same strategies, but every opponent is now a sharp drafter, so you")
print("  are no longer the strongest team in the league by default.\n")
sharp_field = {s: ARCHETYPES["sharp"] for s in range(1, 11) if s != lg6.slot}
summary_sharp, _ = ff.evaluate(pool, lg6, ["bpa", "balanced", "ceiling"],
                               n_sims=N, seed=11, field_=sharp_field)
print(summary_sharp.to_string(index=False))

soft = summary.set_index("strategy")
sharp = summary_sharp.set_index("strategy")
print("\n  championship % , soft field -> sharp field:")
for s in ["bpa", "balanced", "ceiling"]:
    print(f"    {s:<10} {soft.loc[s,'champ_%']:>6.1f}  ->  {sharp.loc[s,'champ_%']:>6.1f}"
          f"   ({sharp.loc[s,'champ_%'] - soft.loc[s,'champ_%']:+.1f})")

# ---------------------------------------------------------------- objective
hr("7. THE TWO-PART OBJECTIVE")
print(ff.objective(summary, floor=1050).to_string(index=False))
print("\n  maximise ceiling_CVaR subject to P10_pts >= floor")

# ------------------------------------------- up/down spread bit-identical
hr("8. UP/DOWN SPREAD SPLIT -- BIT-IDENTICAL WHEN up_spread == down_spread == proj_spread")
pool_split = ff.make_pool()  # no up_spread/down_spread column -- both derive from proj_spread
prepared = ff.prepare(pool_split, lg6)

# recompute the pre-refactor (symmetric) formulas independently, without
# reusing any of the new up_spread/down_spread machinery
old_p85 = prepared["proj_points"] * (1 + 1.036 * prepared["proj_spread"])
old_p15 = prepared["proj_points"] * (1 - 1.036 * prepared["proj_spread"])
z_spread = (prepared["proj_spread"] - prepared["proj_spread"].mean()) / prepared["proj_spread"].std(ddof=0)
z_cv = (prepared["weekly_cv"] - prepared["weekly_cv"].mean()) / prepared["weekly_cv"].std(ddof=0)
up = (prepared["adp"] - prepared["adp_min"]).clip(lower=0)
z_up = (up - up.mean()) / up.std(ddof=0)
old_ceiling = (z_cv + z_spread + z_up) / 3.0

p85_ok = np.allclose(prepared["p85_points"], old_p85)
p15_ok = np.allclose(prepared["p15_points"], old_p15)
ceil_ok = np.allclose(prepared["ceiling_index"], old_ceiling)
print(f"  p85_points matches pre-refactor formula   : {'OK' if p85_ok else 'MISMATCH'}")
print(f"  p15_points matches pre-refactor formula   : {'OK' if p15_ok else 'MISMATCH'}")
print(f"  ceiling_index matches pre-refactor formula: {'OK' if ceil_ok else 'MISMATCH'}")

board_split = ff.build_board(pool_split, lg6)
print("  vor/alpha untouched by this refactor (no code path reads up/down_spread):")
print(f"    vor   sample: {board_split['vor'].iloc[:3].round(2).tolist()}")
print(f"    alpha sample: {board_split['alpha'].iloc[:3].round(2).tolist()}")

# ------------------------------------------------ downside-weight inversion
hr("9. DOWNSIDE-WEIGHT INVERSION  (the bug this whole change fixes)")
print("  Two otherwise-comparable players; player B's raw ceiling (vor_p85) is")
print("  a hair better than player A's, but B's floor (vor_p15) is much worse.")
print("  Before this fix, no policy could tell them apart on the downside.\n")

sample = pd.DataFrame({
    "position":   ["RB", "RB"],
    "vor":        [100.0, 101.0],
    "vor_p85":    [140.0, 141.0],   # B nominally better on pure upside
    "vor_p15":    [95.0, 50.0],     # B has a much steeper floor collapse
    "risk_index": [0.0, 0.0],       # isolate from availability risk_penalty
})
avail = np.array([True, True])
choose_kwargs = dict(counts={}, league=lg6, picks_left=lg6.rounds, recent=[],
                     rng=np.random.default_rng(0), overall=1, rnd=1)

pick_max = ff.PRESETS["max_ceiling"].choose(sample, avail, **choose_kwargs)
pick_guarded = ff.PRESETS["ceiling_guarded"].choose(sample, avail, **choose_kwargs)

max_ok = pick_max == 1
guarded_ok = pick_guarded == 0
print(f"  max_ceiling     (downside_weight=0.00) picks player {'AB'[pick_max]}"
      f"   {'OK -- unchanged, still chases raw ceiling' if max_ok else 'MISMATCH'}")
print(f"  ceiling_guarded (downside_weight=0.35) picks player {'AB'[pick_guarded]}"
      f"   {'OK -- refuses the cliff' if guarded_ok else 'MISMATCH'}")
