"""Pydantic request/response shapes for the ffsim API.

These mirror ffsim's own domain types (League, Scoring, the board DataFrame,
the evaluate() summary) without depending on ffsim internals directly, so the
API's wire format stays stable even if ffsim's internal representation shifts.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class LineupSettings(BaseModel):
    QB: int = Field(1, ge=0, le=10)
    RB: int = Field(2, ge=0, le=10)
    WR: int = Field(2, ge=0, le=10)
    TE: int = Field(1, ge=0, le=10)
    FLEX: int = Field(1, ge=0, le=10)


class LeagueSettingsRequest(BaseModel):
    teams: int = Field(10, ge=2, le=32)
    slot: int = Field(6, ge=1, le=32)
    scoring: Literal["half_ppr", "ppr", "standard"] = "half_ppr"
    bench: int = Field(6, ge=0, le=30)
    lineup: LineupSettings = LineupSettings()
    playoff_teams: int = Field(4, ge=0, le=32)
    reserved_slots: int = Field(2, ge=0, le=30)
    # How much upside to chase in the model's own valuation. Independent of
    # model_influence below -- this shapes OUR number, model_influence
    # decides how much of our number vs. the market's you actually see.
    variance: Literal["Low", "Medium", "High", "Extreme"] = "Medium"
    # Defaults OFF: no backtest to date shows the model beating the market
    # (see ffsim.draft.MODEL_INFLUENCE_LEVELS), so the shipped default must
    # not assert otherwise. Off = pure consensus board, arranged for your
    # league; Extreme = pure model valuation.
    model_influence: Literal["Off", "Low", "Medium", "High", "Extreme"] = "Off"

    @model_validator(mode="after")
    def _slot_within_teams(self) -> "LeagueSettingsRequest":
        if self.slot > self.teams:
            raise ValueError(f"slot {self.slot} is greater than teams {self.teams}")
        return self


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
    # Raw alpha (vor_surplus - market_implied_vor), unscaled by model_influence.
    # Only for display: at Off, the UI shows this instead of the (always 0.0)
    # bargain figure, greyed out -- informative rather than dead, without
    # implying it's being acted on. Null for the same players bargain is null
    # for (no market price to compare to).
    alpha: Optional[float] = None


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
    # False when this deployment cannot serve live simulation (see main.py).
    # The frontend hides the Simulation panel rather than offering a control
    # that would 503.
    live_simulation: bool = True


class SimulateRequest(LeagueSettingsRequest):
    strategies: List[str] = Field(["bpa", "balanced", "ceiling"], max_length=8)
    # 5,000 is the run that settled the aggression question (docs/TEST_LOG.md);
    # the ceiling must stay reachable.
    n_sims: int = Field(100, ge=1, le=5000)


class NextPickRequest(LeagueSettingsRequest):
    gone: List[str] = Field([], max_length=1000)  # player_ids taken by anyone (includes `mine`)
    mine: List[str] = Field([], max_length=100)   # player_ids I've drafted -- drives roster need
    current_pick: int = Field(1, ge=1)            # overall pick number happening right now
    # Which overall pick to compute availability for. None (the default)
    # means "my own next pick" -- the header's own framing. A future round-
    # chip click in DraftPosition will pass an explicit overall pick here to
    # preview availability at THAT pick instead; same endpoint, same
    # availability(df, pick) call, just a different target.
    target_pick: Optional[int] = Field(None, ge=1)


class NextPickPlayerRow(BaseModel):
    player_id: str
    name: str
    position: str
    team: str
    our_value: float
    availability: float   # P(still on the board at `next_pick`), 0..1


class TierDepletionRow(BaseModel):
    position: str
    tier: int
    remaining: int


class NextPickResponse(BaseModel):
    current_pick: int
    next_pick: Optional[int] = None    # YOUR own next pick, always -- what the header names
    picks_away: Optional[int] = None   # gap from current_pick to next_pick
    target_pick: Optional[int] = None  # the pick take_now/can_wait were actually computed for
    hedge_window: int
    take_now: List[NextPickPlayerRow]    # availability < 50% at target_pick -- won't be there
    can_wait: List[NextPickPlayerRow]    # availability >= 50% at target_pick -- take someone else first
    tier_depletion: List[TierDepletionRow]


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
