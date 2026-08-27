#!/usr/bin/env python3
"""Correctness tests for backtest.py's season-scoring machinery (stage 2).

    python test_backtest.py

Two things are checked, both by hand-computed numbers, not by asserting the
code agrees with itself:

1. The week-level leak guard actually catches a leak (belief_for_week raises
   when weeks_revealed disagrees with week), and a player's belief the week
   before he breaks out reflects only what happened before -- not the
   breakout itself.
2. score_season's full-season total matches a total computed by hand, in a
   roster small enough to check on paper.
"""
from __future__ import annotations

import numpy as np

import backtest as bt
from ffsim.config import League

FAILURES = 0


def check(label: str, condition: bool) -> None:
    global FAILURES
    status = "PASS" if condition else "FAIL"
    if not condition:
        FAILURES += 1
    print(f"  [{status}] {label}")


# ---------------------------------------------------------------------------
# the exact scenario from the review: zero for six weeks, then 40 in week 7
# ---------------------------------------------------------------------------

def test_belief_guard_raises_on_a_real_off_by_one():
    print("\nbelief_for_week: the assert must actually fire, not just pass")
    cum_pts = np.array([0.0, 0.0])
    cum_games = np.array([0.0, 0.0])
    # correct call: 0 weeks folded in, deciding week 0 -- must not raise
    try:
        bt.belief_for_week(cum_pts, cum_games, weeks_revealed=0, week=0,
                           preseason_prior=np.array([5.0, 3.0]))
        check("correct call (weeks_revealed == week) does not raise", True)
    except AssertionError:
        check("correct call (weeks_revealed == week) does not raise", False)

    # the leak this whole mechanism exists to catch: deciding week 6 using
    # stats that already include week 6 itself (weeks_revealed=7, week=6)
    try:
        bt.belief_for_week(cum_pts, cum_games, weeks_revealed=7, week=6,
                           preseason_prior=np.array([5.0, 3.0]))
        check("off-by-one leak (weeks_revealed=7 for week=6) raises", False)
    except AssertionError:
        check("off-by-one leak (weeks_revealed=7 for week=6) raises", True)


def test_week7_decision_does_not_know_about_the_breakout():
    print("\nweek-7 lineup decision must not know about the week-7 breakout")
    # player A: steady 6 ppg every week. player B: 0 for six weeks, then 40.
    # cum stats reflect weeks 1-6 ONLY (index 0..5) -- week 7 (index 6) has
    # not happened yet at decision time.
    cum_pts = np.array([6.0 * 6, 0.0])       # [A, B]
    cum_games = np.array([6.0, 6.0])
    belief = bt.belief_for_week(cum_pts, cum_games, weeks_revealed=6, week=6,
                                preseason_prior=np.array([6.0, 4.0]))
    check("B's week-7 belief is 0.0 (his weeks 1-6), not influenced by the 40",
          belief[1] == 0.0)
    check("A's belief (6.0) still exceeds B's (0.0) going into week 7",
          belief[0] > belief[1])


# ---------------------------------------------------------------------------
# full-season hand-checked total
# ---------------------------------------------------------------------------
# 7-player roster, one player per required starter slot (QB, RB x2, WR x2,
# TE) so those six are never in competition and start every week they play --
# plus TWO flex-eligible candidates (A and B) contesting the one FLEX slot,
# using the exact 0x6-then-40 shape from the review. positions array index:
#   0 QB   1 RB   2 RB   3 WR   4 WR   5 TE   6 FLEX-A (RB)   7 FLEX-B (WR)

def test_hand_checked_season_total():
    print("\nfull-season total vs. a total computed by hand")
    league = League(teams=12)   # default lineup: QB1 RB2 WR2 TE1 FLEX1, 7 starters
    positions = np.array(["QB", "RB", "RB", "WR", "WR", "TE", "RB", "WR"])
    W = 7
    pts = np.zeros((8, W))
    pts[0, :] = 20.0   # QB, 20/wk
    pts[1, :] = 15.0   # RB1, 15/wk
    pts[2, :] = 12.0   # RB2, 12/wk
    pts[3, :] = 10.0   # WR1, 10/wk
    pts[4, :] = 9.0    # WR2, 9/wk
    pts[5, :] = 8.0    # TE,  8/wk
    pts[6, :] = 6.0    # FLEX-A, steady 6/wk
    pts[7, :6] = 0.0   # FLEX-B, 0 for six weeks...
    pts[7, 6] = 40.0   # ...then 40 in week 7 (index 6)
    played = np.ones((8, W), dtype=bool)

    preseason_prior = np.array([20.0, 15.0, 12.0, 10.0, 9.0, 8.0, 6.0, 4.0])
    rosters = {1: [0, 1, 2, 3, 4, 5, 6, 7]}

    out = bt.score_season(positions, rosters, pts, played, preseason_prior, league)
    total = out["starter_pts"][1]

    # by hand: the six single-occupant slots always start (7 weeks each);
    # the FLEX slot goes to A every week, honestly, because B's cum belief
    # never exceeds A's before week 7 reveals the 40 -- so B's 40 is
    # correctly left on the bench.
    expected = (20 + 15 + 12 + 10 + 9 + 8) * 7 + 6 * 7
    check(f"starter total == {expected} (hand-computed)", total == expected)
    check("B's week-7 breakout (40) never counted -- he was benched",
          total != expected + 40 - 6)   # +40-6 = what it'd be if B started wk7 instead of A

    weekly = out["weekly_totals"][1]
    check("week-7 (index 6) starter total is the honest 74, not the clairvoyant 108",
          weekly[6] == 20 + 15 + 12 + 10 + 9 + 8 + 6)


# ---------------------------------------------------------------------------
# regression: the 2023 board must not rank Nick Chubb top-3
# ---------------------------------------------------------------------------
# From the code review: the ECR-fit curve alone ranked Chubb (2023) the
# 2nd-most valuable player in the entire draft based on positional-rank
# history, with no way to see the ACL tear coming in week 2. Real ADP had
# him going 12th. Risk (miss_rate) and dispersion (ecr_sd-propagated
# up_spread/down_spread) were wired in specifically to give a risk-aware
# strategy a way to decline that bet. This is the concrete, known-answer
# case the review asked to keep as a permanent regression check -- it is
# expected to catch this class of failure faster than any pooled aggregate,
# and it is allowed to fail: if it does, that says the fix doesn't fully
# work yet, which is a real finding, not a reason to weaken the assertion.

def _strategy_score(board, strategy):
    """Reimplements Strategy.choose's score formula (Strategy.choose itself
    only returns the argmax index; this test needs the full ranking). Empty
    roster / pick 1, so bonus and need are both 0 for every player -- this
    is purely the value/risk/downside terms, which is what's under test."""
    vor = board["vor"].to_numpy()
    vor_p85 = board["vor_p85"].to_numpy()
    vor_p15 = board["vor_p15"].to_numpy()
    cw = strategy.ceiling_weight
    blended = (1 - cw) * vor + cw * vor_p85
    risk = board["risk_index"].to_numpy() * strategy.risk_penalty * 10.0
    downside = (vor - vor_p15) * strategy.downside_weight
    return blended - risk - downside


def test_chubb_2023_not_top3_by_risk_aware_vor():
    print("\n2023 board: Nick Chubb must not be a top-3 valued player "
          "(risk/dispersion-aware VOR)")
    board, pts, played, weeks, source, fit_info = bt.build_source_board(2023, "ecr")
    board_v = bt._with_valuation(
        board, "proj_points", bt.DEFAULT_LEAGUE,
        up_spread=board["up_spread"].to_numpy(),
        down_spread=board["down_spread"].to_numpy(),
        miss_rate=board["miss_rate"].to_numpy(),
    )
    board_v = board_v.assign(score=_strategy_score(board_v, bt.BPA_RISK_AWARE))
    ranked = board_v.sort_values("score", ascending=False).reset_index(drop=True)
    chubb_rank = int(ranked.index[ranked["name"] == "Nick Chubb"][0]) + 1
    print(f"  Nick Chubb's rank by risk-aware score: {chubb_rank} "
          f"(top 5: {ranked['name'].head(5).tolist()})")
    check("Chubb is not top-3 by risk/dispersion-aware VOR", chubb_rank > 3)


if __name__ == "__main__":
    test_belief_guard_raises_on_a_real_off_by_one()
    test_week7_decision_does_not_know_about_the_breakout()
    test_hand_checked_season_total()
    test_chubb_2023_not_top3_by_risk_aware_vor()
    print()
    if FAILURES:
        print(f"{FAILURES} check(s) FAILED")
        raise SystemExit(1)
    print("all checks passed")
