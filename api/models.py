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
    vor: float
    alpha: float
    tier: int


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
