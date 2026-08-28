#!/usr/bin/env python3
"""Acceptance tests for Strategy.model_influence.

    python test_model_influence.py
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

from ffsim.config import League
from ffsim.draft import PRESETS

FAILURES = 0


def check(label: str, condition: bool) -> None:
    global FAILURES
    status = "PASS" if condition else "FAIL"
    if not condition:
        FAILURES += 1
    print(f"  [{status}] {label}")


def _strategy_score(board: pd.DataFrame, strategy) -> np.ndarray:
    """Mirror Strategy.choose for a no-need, all-legal first pick."""
    vor = board["vor"].to_numpy()
    vor_p85 = board["vor_p85"].to_numpy()
    vor_p15 = board["vor_p15"].to_numpy()
    mi = strategy.model_influence
    if mi == 1.0 or "market_implied_vor" not in board.columns:
        effective_vor = vor
        effective_vor_p85 = vor_p85
        effective_vor_p15 = vor_p15
    else:
        market = board["market_implied_vor"].to_numpy()
        priced = np.isfinite(market)
        effective_vor = np.where(priced, market + mi * (vor - market), vor)
        effective_vor_p85 = np.where(priced, market + mi * (vor_p85 - market), vor_p85)
        effective_vor_p15 = np.where(priced, market + mi * (vor_p15 - market), vor_p15)

    cw = strategy.ceiling_weight
    blended = (1 - cw) * effective_vor + cw * effective_vor_p85
    risk = board["risk_index"].to_numpy() * strategy.risk_penalty * 10.0
    downside = (effective_vor - effective_vor_p15) * strategy.downside_weight
    return blended - risk - downside


def test_model_influence_one_is_bit_identical():
    print("\nmodel_influence=1.0 preserves today's score path")
    board = pd.DataFrame({
        "position": ["RB", "WR", "TE"],
        "adp": [3.0, 1.0, 2.0],
        "vor": [100.0, 90.0, 80.0],
        "vor_p85": [125.0, 130.0, 118.0],
        "vor_p15": [70.0, 85.0, 50.0],
        "risk_index": [0.0, 1.0, -1.0],
        "market_implied_vor": [20.0, 200.0, np.nan],
        "adp_is_estimated": [False, False, True],
    })
    old = dataclasses.replace(PRESETS["ceiling_guarded"], model_influence=1.0)
    same = dataclasses.replace(old)
    scores_old = _strategy_score(board.drop(columns=["market_implied_vor"]), old)
    scores_new = _strategy_score(board, same)
    check("score vector is bit-identical with market column present",
          np.array_equal(scores_old, scores_new))

    league = League(teams=1, slot=1, lineup={}, bench=1, reserved_slots=0,
                    playoff_teams=1)
    avail = np.ones(len(board), dtype=bool)
    kwargs = dict(counts={}, league=league, picks_left=1, recent=[],
                  rng=np.random.default_rng(0), overall=1, rnd=1)
    check("chosen player is unchanged",
          old.choose(board.drop(columns=["market_implied_vor"]), avail, **kwargs)
          == same.choose(board, avail, **kwargs))


def test_model_influence_zero_follows_market_adp_order_for_priced_players():
    print("\nmodel_influence=0.0 follows market-implied VOR for priced players")
    board = pd.DataFrame({
        "position": ["RB", "RB", "RB", "RB"],
        "adp": [4.0, 1.0, 3.0, 2.0],
        "vor": [400.0, 10.0, 300.0, 20.0],
        "vor_p85": [450.0, 15.0, 350.0, 25.0],
        "vor_p15": [350.0, 5.0, 250.0, 15.0],
        "risk_index": [0.0, 0.0, 0.0, 0.0],
        "market_implied_vor": [70.0, 100.0, 80.0, 90.0],
        "adp_is_estimated": [False, False, False, False],
    })
    strategy = dataclasses.replace(PRESETS["bpa"], model_influence=0.0,
                                   early_rounds=0)
    scores = _strategy_score(board, strategy)
    market_order = board.sort_values("market_implied_vor", ascending=False).index.tolist()
    adp_order = board.sort_values("adp").index.tolist()
    score_order = list(np.argsort(-scores))
    check("market-implied order is ADP order in this priced board",
          market_order == adp_order)
    check("score order matches ADP order for priced players",
          score_order == adp_order)
    check("no NaN reaches the score", np.isfinite(scores).all())


def test_unpriced_players_use_raw_vor_when_market_is_nan():
    print("\nunpriced players keep raw VOR")
    board = pd.DataFrame({
        "position": ["RB", "RB"],
        "adp": [1.0, 2.0],
        "vor": [10.0, 50.0],
        "vor_p85": [10.0, 50.0],
        "vor_p15": [10.0, 50.0],
        "risk_index": [0.0, 0.0],
        "market_implied_vor": [100.0, np.nan],
        "adp_is_estimated": [False, True],
    })
    strategy = dataclasses.replace(PRESETS["bpa"], model_influence=0.0,
                                   early_rounds=0)
    scores = _strategy_score(board, strategy)
    check("priced player uses market-implied VOR", scores[0] == 100.0)
    check("unpriced player uses raw VOR", scores[1] == 50.0)
    check("score stays finite", np.isfinite(scores).all())


if __name__ == "__main__":
    test_model_influence_one_is_bit_identical()
    test_model_influence_zero_follows_market_adp_order_for_priced_players()
    test_unpriced_players_use_raw_vor_when_market_is_nan()
    print()
    if FAILURES:
        print(f"{FAILURES} check(s) FAILED")
        raise SystemExit(1)
    print("all checks passed")
