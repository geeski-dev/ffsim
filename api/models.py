"""Pydantic request/response shapes for the ffsim API.

These mirror ffsim's own domain types (League, Scoring, the board DataFrame,
the evaluate() summary) without depending on ffsim internals directly, so the
API's wire format stays stable even if ffsim's internal representation shifts.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel


class LineupSettings(BaseModel):
    QB: int = 1
    RB: int = 2
    WR: int = 2
    TE: int = 1
    FLEX: int = 1


class LeagueSettingsRequest(BaseModel):
    teams: int = 10
    slot: int = 6
    scoring: Literal["half_ppr", "ppr", "standard"] = "half_ppr"
    bench: int = 6
    lineup: LineupSettings = LineupSettings()
    playoff_teams: int = 4
    reserved_slots: int = 2
    # How much upside to chase in the model's own valuation. Independent of
    # model_influence below -- this shapes OUR number, model_influence
    # decides how much of our number vs. the market's you actually see.
    variance: Literal["Low", "Medium", "High", "Extreme"] = "Medium"
    # Defaults OFF: no backtest to date shows the model beating the market
    # (see ffsim.draft.MODEL_INFLUENCE_LEVELS), so the shipped default must
    # not assert otherwise. Off = pure consensus board, arranged for your
    # league; Extreme = pure model valuation.
    model_influence: Literal["Off", "Low", "Medium", "High", "Extreme"] = "Off"


class PickChip(BaseModel):
    round: int
    overall_pick: int
    gap_to_next: Optional[int] = None


class PositionScarcityRow(BaseModel):
    position: str
    effective_starters: int
    replacement_points: float
    top_vor: float


class PlayerRow(BaseModel):
    player_id: str
    name: str
    position: str
    team: str
    adp: float
    # Expert consensus (median of individual FantasyPros rankers, Fantasy
    # Pros' own aggregate excluded -- see build_pool.py). Null together for a
    # player without 6+ individual rankers; render as an em-dash, not 0.
    expert_rank: Optional[float] = None
    expert_rank_lo: Optional[float] = None
    expert_rank_hi: Optional[float] = None
    # "Ours": the model's own value estimate at the requested Variance /
    # Model Influence combination, and the floor-ceiling band behind it.
    our_value: float
    our_range_lo: float
    our_range_hi: float
    # model_influence * alpha -- see Strategy.value_components. At
    # model_influence="Off" this is exactly 0.0 for every priced player by
    # construction: it states plainly that nothing here asserts the model
    # beats the market. Null for players with no market price to compare to.
    bargain: Optional[float] = None


class LeagueResponse(BaseModel):
    pick_numbers: List[int]
    hedge_window: int
    rounds: int
    reserved_slots: int
    total_rounds: int
    describe: str
    scarcity: List[PositionScarcityRow]
    players: List[PlayerRow]
    picks: List[PickChip]


class SimulateRequest(LeagueSettingsRequest):
    strategies: List[str] = ["bpa", "balanced", "ceiling"]
    n_sims: int = 100


class StrategyResultRow(BaseModel):
    strategy: str
    champ_pct: float
    playoff_pct: float
    mean_pts: float
    p10_pts: float
    p85_pts: float
    ceiling_cvar: float
    mean_wins: float


class SimulateResponse(BaseModel):
    results: List[StrategyResultRow]
