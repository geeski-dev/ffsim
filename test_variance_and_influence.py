#!/usr/bin/env python3
"""Acceptance tests for the Variance and Model Influence knobs (stage 3).

    python test_variance_and_influence.py

Mirrors test_model_influence.py's style: an independent reimplementation of
the scoring math, not a call into Strategy.value_components, so the test can
actually catch a divergence rather than confirm the implementation against
itself.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ffsim.draft import MODEL_INFLUENCE_LEVELS, VARIANCE_LEVELS, VARIANCE_SWING_ENABLED

FAILURES = 0


def check(label: str, condition: bool) -> None:
    global FAILURES
    status = "PASS" if condition else "FAIL"
    if not condition:
        FAILURES += 1
    print(f"  [{status}] {label}")


def _independent_score(board: pd.DataFrame, ceiling_weight: float, risk_penalty: float,
                       downside_weight: float, model_influence: float) -> np.ndarray:
    """Recomputed from the spec, not from ffsim.draft, on purpose."""
    vor = board["vor"].to_numpy()
    vor_p85 = board["vor_p85"].to_numpy()
    vor_p15 = board["vor_p15"].to_numpy()
    mi = model_influence
    if mi == 1.0 or "market_implied_vor" not in board.columns:
        eff_vor, eff_p85, eff_p15 = vor, vor_p85, vor_p15
    else:
        market = board["market_implied_vor"].to_numpy()
        priced = np.isfinite(market)
        eff_vor = np.where(priced, market + mi * (vor - market), vor)
        # anchor to eff_vor, keep the model's own raw upside/downside gap --
        # NOT blended independently toward the flat market scalar (see
        # value_components's own comment: that collapses ceiling/downside to
        # a no-op at mi=0.0, contradicting "Variance stays active at Off")
        eff_p85 = np.where(priced, eff_vor + (vor_p85 - vor), vor_p85)
        eff_p15 = np.where(priced, eff_vor - (vor - vor_p15), vor_p15)
    blended = (1 - ceiling_weight) * eff_vor + ceiling_weight * eff_p85
    risk = board["risk_index"].to_numpy() * risk_penalty * 10.0
    downside = (eff_vor - eff_p15) * downside_weight
    return blended - risk - downside


def test_variance_levels_match_spec_table():
    print("\nVARIANCE_LEVELS matches the stage-3 table")
    expected = {
        "Low":     dict(ceiling_weight=0.0, downside_weight=0.35, ev_cap=0.05),
        "Medium":  dict(ceiling_weight=0.3, downside_weight=0.20, ev_cap=0.10),
        "High":    dict(ceiling_weight=0.7, downside_weight=0.10, ev_cap=0.20),
        "Extreme": dict(ceiling_weight=1.0, downside_weight=0.00, ev_cap=0.35),
    }
    check("exactly the four named levels", set(VARIANCE_LEVELS) == set(expected))
    for name, vals in expected.items():
        s = VARIANCE_LEVELS[name]
        check(f"{name}.ceiling_weight == {vals['ceiling_weight']}", s.ceiling_weight == vals["ceiling_weight"])
        check(f"{name}.downside_weight == {vals['downside_weight']}", s.downside_weight == vals["downside_weight"])
        check(f"{name}.ev_cap == {vals['ev_cap']}", s.ev_cap == vals["ev_cap"])


def test_risk_penalty_is_not_on_the_variance_knob():
    print("\nrisk_penalty stays constant at 0.25 across every variance level")
    for name, s in VARIANCE_LEVELS.items():
        check(f"{name}.risk_penalty == 0.25", s.risk_penalty == 0.25)


def test_swing_picks_enabled_only_at_extreme():
    print("\nswing_picks flag is Extreme-only (actual pick numbers are league-specific, set by the API)")
    check("Low disabled", VARIANCE_SWING_ENABLED["Low"] is False)
    check("Medium disabled", VARIANCE_SWING_ENABLED["Medium"] is False)
    check("High disabled", VARIANCE_SWING_ENABLED["High"] is False)
    check("Extreme enabled", VARIANCE_SWING_ENABLED["Extreme"] is True)
    for name, s in VARIANCE_LEVELS.items():
        check(f"{name} preset itself carries no baked-in pick numbers (league-specific)", s.swing_picks == ())


def test_model_influence_levels_match_spec():
    print("\nMODEL_INFLUENCE_LEVELS matches Off/Low/Medium/High/Extreme = 0/.25/.5/.75/1")
    expected = {"Off": 0.0, "Low": 0.25, "Medium": 0.5, "High": 0.75, "Extreme": 1.0}
    check("exactly the five named levels", set(MODEL_INFLUENCE_LEVELS) == set(expected))
    for name, val in expected.items():
        check(f"{name} == {val}", MODEL_INFLUENCE_LEVELS[name] == val)


def _sample_board() -> pd.DataFrame:
    return pd.DataFrame({
        "position": ["RB", "WR", "TE", "QB"],
        "adp": [3.0, 1.0, 2.0, 20.0],
        "vor": [100.0, 90.0, 80.0, 40.0],
        "vor_p85": [125.0, 130.0, 118.0, 55.0],
        "vor_p15": [70.0, 85.0, 50.0, 20.0],
        "risk_index": [0.0, 1.0, -1.0, 0.5],
        "market_implied_vor": [60.0, 100.0, np.nan, 45.0],
        "adp_is_estimated": [False, False, True, False],
    })


def test_value_components_matches_independent_recompute_at_full_model_influence():
    print("\nvalue_components(mi=1.0) matches an independently recomputed raw-VOR score")
    board = _sample_board()
    strategy = VARIANCE_LEVELS["High"]
    from dataclasses import replace
    strategy = replace(strategy, model_influence=1.0)
    got = strategy.value_components(board)["score"]
    want = _independent_score(board, strategy.ceiling_weight, strategy.risk_penalty,
                              strategy.downside_weight, 1.0)
    check("score vectors match", np.allclose(got, want))


def test_value_components_matches_independent_recompute_blended():
    print("\nvalue_components blends variance and model_influence together correctly")
    board = _sample_board()
    from dataclasses import replace
    strategy = replace(VARIANCE_LEVELS["Medium"], model_influence=MODEL_INFLUENCE_LEVELS["Medium"])
    got = strategy.value_components(board)["score"]
    want = _independent_score(board, strategy.ceiling_weight, strategy.risk_penalty,
                              strategy.downside_weight, strategy.model_influence)
    check("score vectors match", np.allclose(got, want))
    check("no NaN reaches the score (unpriced TE row survives)", np.isfinite(got).all())


def test_value_components_exposes_effective_range_for_display():
    print("\nvalue_components exposes effective_vor_p15/p85 for the API's 'Our Range' column")
    board = _sample_board()
    from dataclasses import replace
    strategy = replace(VARIANCE_LEVELS["Low"], model_influence=0.0)
    comp = strategy.value_components(board)
    # priced rows follow the market at mi=0.0
    check("priced row 0 effective_vor == market_implied_vor", comp["effective_vor"][0] == 60.0)
    check("unpriced row 2 (TE) keeps raw vor_p15/p85",
          comp["effective_vor_p15"][2] == 50.0 and comp["effective_vor_p85"][2] == 118.0)


def test_variance_stays_active_at_model_influence_off():
    print("\nVariance (ceiling_weight/downside_weight) still moves 'Our Value' at "
          "model_influence=Off -- explicit requirement: 'The Variance knob stays "
          "fully active at model_influence = Off ... it is the corner most likely "
          "to work, since the market board is the only thing that has beaten NULL "
          "so far.' Blending vor_p85/vor_p15 independently toward the same flat "
          "market_implied_vor scalar (as vor itself is blended) would collapse "
          "all three onto one number at mi=0, making ceiling_weight/downside_weight "
          "no-ops -- this guards against that regression.")
    board = pd.DataFrame({
        "position": ["RB", "WR"],
        "adp": [1.0, 2.0],
        "vor": [100.0, 95.0],
        "vor_p85": [140.0, 100.0],   # RB has real upside beyond its median
        "vor_p15": [60.0, 90.0],     # RB has real downside beyond its median
        "risk_index": [0.0, 0.0],
        "market_implied_vor": [90.0, 90.0],   # market sees them as equal
        "adp_is_estimated": [False, False],
    })
    from dataclasses import replace
    low = replace(VARIANCE_LEVELS["Low"], model_influence=0.0)       # ceiling_weight 0.0
    extreme = replace(VARIANCE_LEVELS["Extreme"], model_influence=0.0)  # ceiling_weight 1.0
    score_low = low.value_components(board)["score"]
    score_extreme = extreme.value_components(board)["score"]
    check("Extreme (chase ceiling) and Low (ignore it) disagree on the RB at mi=Off",
          not np.isclose(score_low[0], score_extreme[0]))
    check("Extreme ranks the RB (real upside) above the WR despite equal market price",
          score_extreme[0] > score_extreme[1])
    check("center estimate (mi=Off) still equals the market price, unaffected by variance",
          low.value_components(board)["effective_vor"][0] == 90.0 and
          extreme.value_components(board)["effective_vor"][0] == 90.0)


if __name__ == "__main__":
    test_variance_levels_match_spec_table()
    test_risk_penalty_is_not_on_the_variance_knob()
    test_swing_picks_enabled_only_at_extreme()
    test_model_influence_levels_match_spec()
    test_value_components_matches_independent_recompute_at_full_model_influence()
    test_value_components_matches_independent_recompute_blended()
    test_value_components_exposes_effective_range_for_display()
    test_variance_stays_active_at_model_influence_off()
    print()
    if FAILURES:
        print(f"{FAILURES} check(s) FAILED")
        raise SystemExit(1)
    print("all checks passed")
