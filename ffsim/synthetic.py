"""Synthetic player pool.

Stands in for the real workbook so the engine can be built, tested, and tuned
before any data arrives. Shapes are calibrated to produce plausible half-PPR
points per game at each positional rank; the point is realistic *structure*
(scarcity curves, ADP noise, volatility by position), not real players.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# per-game production at the top of the position, and at the bottom of the
# draftable pool, interpolated with a convex decay
ARCHETYPES = {
    # QB decay < 1 keeps the top of the position bunched, which is why QB VOR
    # is low in a 1QB league: QB11 is nearly as good as QB4.
    "QB": dict(
        n=32, decay=0.55,
        top=dict(pass_yds=272, pass_td=1.92, interceptions=0.60,
                 rush_yds=30, rush_td=0.35),
        low=dict(pass_yds=208, pass_td=1.24, interceptions=0.78,
                 rush_yds=9, rush_td=0.09),
        cv=0.42, miss=0.07, spread=0.14,
    ),
    "RB": dict(
        n=72, decay=1.95,
        top=dict(rush_yds=85, rush_td=0.55, receptions=3.5,
                 rec_yds=28, rec_td=0.15),
        low=dict(rush_yds=13, rush_td=0.06, receptions=0.7,
                 rec_yds=5, rec_td=0.02),
        cv=0.62, miss=0.14, spread=0.22,
    ),
    "WR": dict(
        n=92, decay=1.80,
        top=dict(receptions=6.2, rec_yds=85, rec_td=0.50,
                 rush_yds=2, rush_td=0.01),
        low=dict(receptions=1.6, rec_yds=20, rec_td=0.09,
                 rush_yds=0, rush_td=0.0),
        cv=0.66, miss=0.10, spread=0.24,
    ),
    "TE": dict(
        n=34, decay=1.95,
        top=dict(receptions=5.0, rec_yds=58, rec_td=0.45),
        low=dict(receptions=1.2, rec_yds=12, rec_td=0.07),
        cv=0.71, miss=0.10, spread=0.26,
    ),
}


def _curve(top: float, low: float, n: int, decay: float) -> np.ndarray:
    ranks = np.arange(n)
    frac = ((n - 1 - ranks) / max(n - 1, 1)) ** decay
    return low + (top - low) * frac


def make_pool(seed: int = 7, teams: int = 10) -> pd.DataFrame:
    """Build a synthetic pool with realistic scarcity and market structure."""
    rng = np.random.default_rng(seed)
    rows = []

    for pos, spec in ARCHETYPES.items():
        n = spec["n"]
        curves = {}
        keys = set(spec["top"]) | set(spec["low"])
        for k in keys:
            curves[k] = _curve(spec["top"].get(k, 0.0), spec["low"].get(k, 0.0),
                               n, spec["decay"])

        for i in range(n):
            # player-level talent noise so ADP order is not a perfect ranking
            shock = rng.normal(1.0, 0.11)
            games = float(np.clip(rng.normal(15.6 - spec["miss"] * 12, 1.5), 7, 17))

            row = {
                "player_id": f"{pos.lower()}-{i + 1:03d}",
                "name": f"{pos}{i + 1:02d} Synthetic",
                "position": pos,
                "team": f"T{(i % 32) + 1:02d}",
                "bye_week": int(rng.integers(5, 15)),
                "proj_games": round(games, 1),
                "miss_rate": float(np.clip(rng.normal(spec["miss"], 0.05), 0.0, 0.55)),
                "weekly_cv": float(np.clip(rng.normal(spec["cv"], 0.09), 0.20, 1.15)),
                "proj_spread": float(np.clip(rng.normal(spec["spread"], 0.06), 0.04, 0.55)),
            }

            for stat in ["pass_yds", "pass_td", "interceptions", "rush_yds",
                         "rush_td", "receptions", "rec_yds", "rec_td"]:
                per_g = curves.get(stat, np.zeros(n))[i] * (shock if stat != "interceptions" else 1.0)
                row[stat] = round(max(per_g, 0.0) * games, 2)
            row["fumbles_lost"] = round(rng.uniform(0.0, 2.2), 2)

            rows.append(row)

    df = pd.DataFrame(rows)
    df = _attach_market(df, rng, teams)
    return df


def _attach_market(df: pd.DataFrame, rng, teams: int) -> pd.DataFrame:
    """Assign ADP that tracks value imperfectly, with right-skewed fall risk."""
    from .config import League, Scoring
    from .scoring import score_frame
    from .valuation import replacement_levels

    league = League(teams=teams)
    pts = score_frame(df, Scoring.half_ppr())
    tmp = df.assign(proj_points=pts)

    repl = replacement_levels(tmp, league)
    vor = pts - tmp["position"].map(repl).fillna(0.0)

    # positional market bias: the market systematically over-drafts QB and TE
    # early relative to VOR, which is what creates exploitable mispricing
    bias = tmp["position"].map({"QB": -14.0, "TE": -6.0, "RB": 4.0, "WR": 0.0}).fillna(0.0)
    perceived = vor + bias + rng.normal(0, 11.0, len(tmp))

    order = np.argsort(-perceived.to_numpy())
    adp = np.empty(len(tmp))
    adp[order] = np.arange(1, len(tmp) + 1)

    # uncertainty in the market's own opinion, wider for volatile players
    sd = 6.0 + 34.0 * tmp["proj_spread"].to_numpy() + adp * 0.045
    df = df.copy()
    df["adp"] = np.round(adp, 1)
    df["adp_sd"] = np.round(sd, 1)
    # falls are longer than rises: floor is nearer than the ceiling
    df["adp_min"] = np.round(np.maximum(adp - 1.05 * sd, 1.0), 1)
    df["adp_max"] = np.round(adp + 2.15 * sd, 1)
    return df
