"""Component stats -> fantasy points, under any Scoring config.

This module is the reason the whole model is reusable across scoring formats.
Projections are stored as component stats (receptions, yards, TDs), never as
fantasy point totals, so re-scoring for PPR vs half-PPR is a multiply, not a
re-collection.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Scoring

COMPONENTS = [
    "pass_yds", "pass_td", "interceptions",
    "rush_yds", "rush_td",
    "receptions", "rec_yds", "rec_td",
    "fumbles_lost", "two_pt",
]

_WEIGHT_MAP = {
    "pass_yds": "pass_yd",
    "pass_td": "pass_td",
    "interceptions": "interception",
    "rush_yds": "rush_yd",
    "rush_td": "rush_td",
    "receptions": "reception",
    "rec_yds": "rec_yd",
    "rec_td": "rec_td",
    "fumbles_lost": "fumble_lost",
    "two_pt": "two_pt",
}


def score_frame(df: pd.DataFrame, scoring: Scoring,
                te_premium: float = 0.0) -> pd.Series:
    """Fantasy points for each row of a component-stat frame.

    Missing components are treated as zero, so a frame carrying only receiving
    stats scores correctly without needing passing columns.

    te_premium adds extra points per reception for tight ends only.
    """
    total = np.zeros(len(df), dtype=float)
    for comp, attr in _WEIGHT_MAP.items():
        if comp in df.columns:
            total += df[comp].fillna(0).to_numpy(dtype=float) * getattr(scoring, attr)

    if te_premium and "position" in df.columns and "receptions" in df.columns:
        is_te = (df["position"] == "TE").to_numpy()
        total += is_te * df["receptions"].fillna(0).to_numpy(dtype=float) * te_premium

    return pd.Series(total, index=df.index, name="points")


def per_game(df: pd.DataFrame, scoring: Scoring, games_col: str = "proj_games",
             te_premium: float = 0.0) -> pd.Series:
    """Points per game. Assumes component columns are season totals."""
    pts = score_frame(df, scoring, te_premium)
    games = df[games_col].replace(0, np.nan) if games_col in df.columns else 17.0
    return (pts / games).fillna(0.0)
