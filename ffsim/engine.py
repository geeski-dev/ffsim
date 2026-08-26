"""Orchestration: run many simulated seasons and compare drafting policies.

Strategies are compared under *common random numbers* -- within a simulation
every strategy faces the same opponent behaviour and the same season outcomes.
Without that, differences between strategies drown in noise and you need an
order of magnitude more runs to see anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable

import numpy as np
import pandas as pd

from .config import League
from .draft import PRESETS, Personality, Strategy, default_field, run_draft
from .pool import prepare
from .season import play_league, simulate_season
from .valuation import add_valuation, effective_starters, replacement_levels

CEILING_TAIL = 0.15    # "the best 15% of seasons"


def build_board(pool: pd.DataFrame, league: League,
                te_premium: float = 0.0) -> pd.DataFrame:
    """Score, value, and tier a raw pool for one specific league."""
    return add_valuation(prepare(pool, league, te_premium), league)


@dataclass
class Result:
    name: str
    champ_pct: float
    playoff_pct: float
    mean_points: float
    p10_points: float
    p85_points: float
    ceiling_cvar: float      # mean of the best CEILING_TAIL of seasons
    mean_wins: float
    n: int

    def as_row(self) -> dict:
        return {
            "strategy": self.name,
            "champ_%": round(self.champ_pct * 100, 2),
            "playoff_%": round(self.playoff_pct * 100, 1),
            "mean_pts": round(self.mean_points, 1),
            "P10_pts": round(self.p10_points, 1),
            "P85_pts": round(self.p85_points, 1),
            "ceiling_CVaR": round(self.ceiling_cvar, 1),
            "mean_wins": round(self.mean_wins, 2),
        }


def evaluate(pool: pd.DataFrame, league: League,
             strategies: Iterable[str] | Dict[str, Strategy] = ("bpa", "balanced", "ceiling"),
             n_sims: int = 400, seed: int = 0,
             field_: Dict[int, Personality] | None = None,
             te_premium: float = 0.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the model. Returns (summary table, per-simulation detail)."""
    board = build_board(pool, league, te_premium)

    if isinstance(strategies, dict):
        strat_map = strategies
    else:
        strat_map = {name: PRESETS[name] for name in strategies}

    if field_ is None:
        field_ = default_field(league, np.random.default_rng(seed))

    records = []
    for sim in range(n_sims):
        for name, strat in strat_map.items():
            rng_d = np.random.default_rng([seed, sim, 0])
            rosters = run_draft(board, league, strat, field_, rng_d)

            rng_s = np.random.default_rng([seed, sim, 1])
            out = simulate_season(board, league, rosters, rng_s)
            table = play_league(league, out["weekly"])
            mine = table[league.slot]

            records.append({
                "sim": sim,
                "strategy": name,
                "points": mine["points"],
                "wins": mine["wins"],
                "seed_rank": mine["seed"],
                "playoffs": mine["made_playoffs"],
                "champion": mine["champion"],
            })

    detail = pd.DataFrame(records)
    rows = []
    for name, g in detail.groupby("strategy", sort=False):
        pts = g["points"].to_numpy()
        cut = np.quantile(pts, 1 - CEILING_TAIL)
        rows.append(Result(
            name=name,
            champ_pct=g["champion"].mean(),
            playoff_pct=g["playoffs"].mean(),
            mean_points=pts.mean(),
            p10_points=float(np.quantile(pts, 0.10)),
            p85_points=float(np.quantile(pts, 0.85)),
            ceiling_cvar=float(pts[pts >= cut].mean()),
            mean_wins=g["wins"].mean(),
            n=len(g),
        ).as_row())

    summary = pd.DataFrame(rows).sort_values("champ_%", ascending=False)
    return summary, detail


def objective(summary: pd.DataFrame, floor: float | None = None) -> pd.DataFrame:
    """Apply the two-part mandate.

    Maximise the mean of the best 15% of seasons, subject to the 10th
    percentile staying above a floor. The floor is a catastrophe constraint,
    not a competitiveness constraint -- if it binds often, it is set too high.
    """
    out = summary.copy()
    if floor is None:
        floor = out["P10_pts"].min() - 1.0
    out["meets_floor"] = out["P10_pts"] >= floor
    out = out.sort_values(["meets_floor", "ceiling_CVaR"], ascending=[False, False])
    return out


def league_report(pool: pd.DataFrame, league: League) -> str:
    """Sanity summary of how this league configuration values positions."""
    board = build_board(pool, league)
    repl = replacement_levels(board, league)
    starters = effective_starters(board, league)
    lines = [league.describe(), ""]
    lines.append(f"{'pos':<5}{'starters':>9}{'replacement':>13}{'top VOR':>10}")
    for pos in sorted(repl):
        top = board.loc[board["position"] == pos, "vor"].max()
        lines.append(f"{pos:<5}{starters.get(pos, 0):>9}{repl[pos]:>13.1f}{top:>10.1f}")
    picks = league.pick_numbers()
    lines.append("")
    lines.append(f"your picks: {picks[:8]} ...")
    lines.append(f"hedge window: {league.hedge_window()}")
    return "\n".join(lines)
