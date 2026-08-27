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
    "up_spread",       # upside dispersion; defaults to proj_spread if absent
    "down_spread",     # downside dispersion; defaults to proj_spread if absent
]

REQUIRED = IDENTITY + STATS + MARKET + RISK


def _derive_spreads(df: pd.DataFrame) -> pd.DataFrame:
    """Fill up_spread/down_spread from proj_spread where a pool doesn't have them.

    up_spread and down_spread are new and not yet present in every built pool
    or CSV on disk (and not produced by the synthetic pool at all), so they
    are not hard-required -- every existing pool keeps loading, symmetric.
    """
    if "proj_spread" not in df.columns:
        return df
    if "up_spread" not in df.columns:
        df = df.assign(up_spread=df["proj_spread"])
    if "down_spread" not in df.columns:
        df = df.assign(down_spread=df["proj_spread"])
    return df


def validate(df: pd.DataFrame) -> pd.DataFrame:
    df = _derive_spreads(df)
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
    out = _derive_spreads(df.copy().reset_index(drop=True))
    out["proj_points"] = score_frame(out, league.scoring, te_premium)
    out["proj_ppg"] = out["proj_points"] / out["proj_games"].clip(lower=1)

    # Ceiling proxy: how good the good outcome is. Built from the two sources
    # of upside we can measure -- week-to-week volatility and how far apart the
    # projection sources are. Upside only -- down_spread has no business
    # making a player look like a better bet.
    z_cv = _z(out["weekly_cv"])
    z_up = _z(out["up_spread"])
    z_upside = _z((out["adp"] - out["adp_min"]).clip(lower=0))
    out["ceiling_index"] = (z_cv + z_up + z_upside) / 3.0

    # 85th/15th-percentile season, driven by the matching tail's own spread --
    # these are no longer mirror images of each other.
    out["p85_points"] = out["proj_points"] * (1 + 1.036 * out["up_spread"])
    out["p15_points"] = out["proj_points"] * (1 - 1.036 * out["down_spread"])

    out["risk_index"] = _z(out["miss_rate"])
    return out


def _z(s: pd.Series) -> pd.Series:
    sd = s.std(ddof=0)
    if not np.isfinite(sd) or sd == 0:
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - s.mean()) / sd
