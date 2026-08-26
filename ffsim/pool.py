"""The player pool: schema, loading, validation, and derived columns.

The pool is stored as component stats plus market and risk metadata. Fantasy
points are never stored — they are computed on demand from a Scoring config,
which is what lets one pool serve a half-PPR and a full-PPR league.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import League
from .scoring import score_frame

IDENTITY = ["player_id", "name", "position", "team", "bye_week"]

# season-total component stats
STATS = [
    "pass_yds", "pass_td", "interceptions",
    "rush_yds", "rush_td",
    "receptions", "rec_yds", "rec_td",
    "fumbles_lost",
]

MARKET = ["adp", "adp_sd", "adp_min", "adp_max"]

RISK = [
    "proj_games",      # expected games played
    "miss_rate",       # 3-yr games-missed rate, 0-1
    "weekly_cv",       # coefficient of variation of weekly points
    "proj_spread",     # cross-source projection disagreement, as a fraction
]

REQUIRED = IDENTITY + STATS + MARKET + RISK


def validate(df: pd.DataFrame) -> pd.DataFrame:
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"pool is missing required columns: {missing}")
    if df["player_id"].duplicated().any():
        dupes = df.loc[df["player_id"].duplicated(), "player_id"].tolist()
        raise ValueError(f"duplicate player_id: {dupes[:5]}")
    bad = df.loc[~df["position"].isin(["QB", "RB", "WR", "TE", "K", "DST"]), "position"]
    if len(bad):
        raise ValueError(f"unexpected positions: {sorted(set(bad))}")
    return df


def load_csv(path: str) -> pd.DataFrame:
    return validate(pd.read_csv(path))


def prepare(df: pd.DataFrame, league: League, te_premium: float = 0.0) -> pd.DataFrame:
    """Attach scoring-dependent columns for a specific league."""
    out = df.copy().reset_index(drop=True)
    out["proj_points"] = score_frame(out, league.scoring, te_premium)
    out["proj_ppg"] = out["proj_points"] / out["proj_games"].clip(lower=1)

    # Ceiling proxy: how good the good outcome is. Built from the two sources
    # of upside we can measure -- week-to-week volatility and how far apart the
    # projection sources are.
    z_cv = _z(out["weekly_cv"])
    z_spread = _z(out["proj_spread"])
    z_upside = _z((out["adp"] - out["adp_min"]).clip(lower=0))
    out["ceiling_index"] = (z_cv + z_spread + z_upside) / 3.0

    # 85th-percentile season, as a multiple of the median projection
    out["p85_points"] = out["proj_points"] * (1 + 1.036 * out["proj_spread"])
    out["p15_points"] = out["proj_points"] * (1 - 1.036 * out["proj_spread"])

    out["risk_index"] = _z(out["miss_rate"])
    return out


def _z(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - s.mean()) / sd
