#!/usr/bin/env python3
"""Regression checks against the pool files the API actually reads.

    python test_pool_columns.py

Per the review note this guards against: a check that passes on a temp
output and not on data/players_half_ppr.csv is not a check. Everything here
loads the real files build_pool.py already wrote, never a fresh build.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

import ffsim as ff
from ffsim.config import League

FAILURES = 0

REPO_ROOT = Path(__file__).resolve().parent
POOL_FILES = {
    "half_ppr": REPO_ROOT / "data" / "players_half_ppr.csv",
    "ppr": REPO_ROOT / "data" / "players_ppr.csv",
}


def check(label: str, condition: bool) -> None:
    global FAILURES
    status = "PASS" if condition else "FAIL"
    if not condition:
        FAILURES += 1
    print(f"  [{status}] {label}")


def test_real_pool_files_have_expert_columns():
    for name, path in POOL_FILES.items():
        print(f"\n{name}: {path.relative_to(REPO_ROOT)}")
        df = ff.load_csv(str(path))
        for col in ["expert_rank", "expert_rank_lo", "expert_rank_hi", "adp_is_estimated"]:
            check(f"has column '{col}'", col in df.columns)

        n = len(df)
        n_covered = int(df["expert_rank"].notna().sum())
        check("at least some players clear the ranker floor", n_covered > 0)
        check("not every player clears it (floor is real, not a no-op)", n_covered < n)

        # all-or-nothing: a player has all three or none -- never a lo/hi
        # without a median, or a median without a range
        triple_notna = df[["expert_rank", "expert_rank_lo", "expert_rank_hi"]].notna()
        check("expert_rank/lo/hi are null together, never partially",
              (triple_notna.nunique(axis=1) == 1).all())

        covered = df[df["expert_rank"].notna()]
        check("expert_rank_lo <= expert_rank <= expert_rank_hi for every covered player",
              bool((covered["expert_rank_lo"] <= covered["expert_rank"]).all() and
                   (covered["expert_rank"] <= covered["expert_rank_hi"]).all()))

        check("adp_is_estimated is boolean", df["adp_is_estimated"].dtype == bool)


def test_expert_columns_survive_build_board():
    print("\nexpert_rank/lo/hi and market_implied_vor survive prepare()+add_valuation() "
          "(the pipeline the API actually calls) -- guards the historical "
          "'computed then dropped by a column whitelist' bug class")
    pool = ff.load_csv(str(POOL_FILES["half_ppr"]))
    league = League(teams=10, slot=6, lineup={"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1},
                    bench=6, reserved_slots=2, playoff_teams=4)
    board = ff.build_board(pool, league)
    for col in ["expert_rank", "expert_rank_lo", "expert_rank_hi",
                "adp_is_estimated", "market_implied_vor", "vor", "vor_p85", "vor_p15",
                "risk_index"]:
        check(f"board has column '{col}' after build_board", col in board.columns)
    check("row count unchanged by the pipeline", len(board) == len(pool))
    check("expert_rank coverage unchanged by the pipeline",
          int(board["expert_rank"].notna().sum()) == int(pool["expert_rank"].notna().sum()))


if __name__ == "__main__":
    test_real_pool_files_have_expert_columns()
    test_expert_columns_survive_build_board()
    print()
    if FAILURES:
        print(f"{FAILURES} check(s) FAILED")
        raise SystemExit(1)
    print("all checks passed")
