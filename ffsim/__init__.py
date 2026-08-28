"""ffsim -- a parameterised fantasy football draft and season model.

Everything is driven by one config object. Change the league, not the code.

    from ffsim import League, Scoring, evaluate, make_pool

    pool = make_pool()                       # or pool.load_csv("players.csv")
    lg   = League(teams=10, slot=6, scoring=Scoring.half_ppr())
    summary, detail = evaluate(pool, lg, ["bpa", "balanced", "ceiling"])
"""
from .config import DEFAULT_LINEUP, League, Scoring
from .draft import (ARCHETYPES, MODEL_INFLUENCE_LEVELS, PRESETS,
                    VARIANCE_LEVELS, VARIANCE_SWING_ENABLED, Personality,
                    Strategy, default_field, run_draft)
from .engine import build_board, evaluate, league_report, objective
from .pool import load_csv, prepare, validate
from .season import play_league, simulate_season
from .synthetic import make_pool
from .valuation import add_valuation, availability, market_curve, replacement_levels

__all__ = [
    "League", "Scoring", "DEFAULT_LINEUP",
    "Strategy", "Personality", "PRESETS", "ARCHETYPES", "default_field", "run_draft",
    "VARIANCE_LEVELS", "VARIANCE_SWING_ENABLED", "MODEL_INFLUENCE_LEVELS",
    "evaluate", "objective", "build_board", "league_report",
    "make_pool", "load_csv", "prepare", "validate",
    "simulate_season", "play_league",
    "add_valuation", "replacement_levels", "market_curve", "availability",
]

__version__ = "0.1.0"
