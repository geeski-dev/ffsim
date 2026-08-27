"""Value over replacement, market-implied points, alpha, and tiers.

Replacement level is *derived* from the league config by actually filling the
league's starting lineups, including flex, rather than assuming a positional
split. Change the team count or the lineup and every number here moves.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import League


def replacement_levels(df: pd.DataFrame, league: League,
                       points_col: str = "proj_points",
                       smooth: int = 3) -> dict[str, float]:
    """Points of the replacement-level player at each position.

    Fills base starters top-down, then fills flex with the best remaining
    flex-eligible players regardless of position, then takes replacement as the
    average of the next `smooth` players at that position.
    """
    if points_col not in df.columns:
        raise KeyError(f"{points_col} not in frame; call pool.prepare first")

    ranked = {
        pos: g.sort_values(points_col, ascending=False)[points_col].to_numpy()
        for pos, g in df.groupby("position")
    }

    used = {pos: 0 for pos in ranked}
    for pos in league.positions:
        used[pos] = min(league.base_starters(pos), len(ranked.get(pos, [])))

    # flex: best remaining across eligible positions
    for _ in range(league.flex_slots):
        best_pos, best_val = None, -np.inf
        for pos in league.flex_eligible:
            arr = ranked.get(pos)
            if arr is None or used[pos] >= len(arr):
                continue
            if arr[used[pos]] > best_val:
                best_pos, best_val = pos, arr[used[pos]]
        if best_pos is None:
            break
        used[best_pos] += 1

    levels = {}
    for pos, arr in ranked.items():
        start = used.get(pos, 0)
        window = arr[start:start + smooth]
        levels[pos] = float(window.mean()) if len(window) else float(arr[-1])
    return levels


def effective_starters(df: pd.DataFrame, league: League,
                       points_col: str = "proj_points") -> dict[str, int]:
    """How many of each position actually start league-wide, flex included."""
    ranked = {
        pos: g.sort_values(points_col, ascending=False)[points_col].to_numpy()
        for pos, g in df.groupby("position")
    }
    used = {pos: 0 for pos in ranked}
    for pos in league.positions:
        used[pos] = min(league.base_starters(pos), len(ranked.get(pos, [])))
    for _ in range(league.flex_slots):
        best_pos, best_val = None, -np.inf
        for pos in league.flex_eligible:
            arr = ranked.get(pos)
            if arr is None or used[pos] >= len(arr):
                continue
            if arr[used[pos]] > best_val:
                best_pos, best_val = pos, arr[used[pos]]
        if best_pos is None:
            break
        used[best_pos] += 1
    return used


def _pava_decreasing(y: np.ndarray) -> np.ndarray:
    """Pool-adjacent-violators fit of a non-increasing sequence."""
    stack: list[list[float]] = []          # [sum, count]
    for val in y:
        s, c = float(val), 1.0
        while stack and stack[-1][0] / stack[-1][1] < s / c:
            ps, pc = stack.pop()
            s += ps
            c += pc
        stack.append([s, c])
    out = np.empty(len(y))
    i = 0
    for s, c in stack:
        n = int(round(c))
        out[i:i + n] = s / c
        i += n
    return out


def market_curve(df: pd.DataFrame, points_col: str = "vor") -> pd.Series:
    """Market-implied points at each player's ADP.

    An isotonic (monotone decreasing) fit of consensus points on ADP. The gap
    between a player's own projection and this curve is the only number worth
    drafting on: it is what you believe minus what the price says.
    """
    order = df["adp"].to_numpy().argsort()
    fitted = np.empty(len(df))
    fitted[order] = _pava_decreasing(df[points_col].to_numpy()[order])
    return pd.Series(fitted, index=df.index, name="market_implied_points")


def add_valuation(df: pd.DataFrame, league: League) -> pd.DataFrame:
    """Attach replacement, VOR, market-implied points, alpha, and tiers."""
    out = df.copy()
    repl = replacement_levels(out, league)
    out["replacement"] = out["position"].map(repl).astype(float)
    out["vor"] = out["proj_points"] - out["replacement"]
    out["vor_p85"] = out["p85_points"] - out["replacement"]

    if "adp_is_estimated" in out.columns:
        priced = ~out["adp_is_estimated"].fillna(False).astype(bool)
    else:
        priced = pd.Series(True, index=out.index)
    out["market_implied_vor"] = np.nan
    if priced.any():
        out.loc[priced, "market_implied_vor"] = market_curve(out.loc[priced], "vor")
    out["alpha"] = out["vor"] - out["market_implied_vor"]
    out["market_implied_points"] = out["market_implied_vor"] + out["replacement"]

    out["tier"] = 0
    for pos, g in out.groupby("position"):
        g = g.sort_values("vor", ascending=False)
        gaps = -g["vor"].diff().fillna(0.0).to_numpy()
        thresh = gaps.mean() + gaps.std(ddof=0)
        tier, tiers = 1, []
        for i, gap in enumerate(gaps):
            if i > 0 and gap > thresh:
                tier += 1
            tiers.append(tier)
        out.loc[g.index, "tier"] = tiers
    return out


def availability(df: pd.DataFrame, pick: int) -> pd.Series:
    """P(player is still on the board at a given overall pick).

    Uses a two-piece normal around ADP: the upper tail is wider because a
    player can fall much further than he can rise. A symmetric model badly
    understates how often good players reach you.
    """
    adp = df["adp"].to_numpy()
    sd_up = np.maximum((df["adp_max"].to_numpy() - adp) / 2.15, 1e-6)
    z = (pick - adp) / sd_up
    from math import erf, sqrt
    cdf = np.array([0.5 * (1 + erf(v / sqrt(2))) for v in z])
    return pd.Series(np.clip(1 - cdf, 0.0, 1.0), index=df.index)
