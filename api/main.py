"""FastAPI service bridging the ffsim model to the web UI.

Two endpoints with very different cost profiles:
  POST /api/league    -- single-digit milliseconds, fires on every settings change
  POST /api/simulate   -- tens of seconds, fires only on explicit user action

The player pools are loaded from static CSVs (data/players_*.csv), so they are
read once at import time and reused across every request.
"""
import dataclasses
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI, HTTPException

import ffsim as ff
from ffsim.valuation import effective_starters, replacement_levels

from models import (
    LeagueResponse,
    LeagueSettingsRequest,
    NextPickPlayerRow,
    NextPickRequest,
    NextPickResponse,
    PickChip,
    PlayerRow,
    PositionScarcityRow,
    SimulateRequest,
    SimulateResponse,
    StrategyResultRow,
    TierDepletionRow,
)

app = FastAPI(title="ffsim API")

# Real player pools, one per scoring format with a dedicated ADP/market
# snapshot. There is no "standard" market snapshot (build_pool.py only
# collects half_ppr/ppr), so standard scoring reuses the half_ppr pool --
# component stats are scoring-format agnostic, only the ADP differs, and
# half_ppr's ADP is the more neutral of the two available snapshots.
POOL_FILES = {
    "half_ppr": REPO_ROOT / "data" / "players_half_ppr.csv",
    "ppr": REPO_ROOT / "data" / "players_ppr.csv",
}
POOLS = {key: ff.load_csv(str(path)) for key, path in POOL_FILES.items()}
POOLS["standard"] = POOLS["half_ppr"]

SCORING_BUILDERS = {
    "half_ppr": ff.Scoring.half_ppr,
    "ppr": ff.Scoring.ppr,
    "standard": ff.Scoring.standard,
}


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


def build_league(settings: LeagueSettingsRequest) -> ff.League:
    scoring_fn = SCORING_BUILDERS[settings.scoring]
    lineup = settings.lineup.model_dump()
    try:
        return ff.League(
            teams=settings.teams,
            slot=settings.slot,
            lineup=lineup,
            flex_eligible=("RB", "WR", "TE"),
            bench=settings.bench,
            scoring=scoring_fn(),
            playoff_teams=settings.playoff_teams,
            reserved_slots=settings.reserved_slots,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def build_strategy(settings: LeagueSettingsRequest, league: "ff.League") -> ff.Strategy:
    """The Variance + Model Influence dropdowns, resolved into one Strategy.

    risk_penalty is intentionally NOT read from settings -- it is fixed at
    0.25 inside every ffsim.draft.VARIANCE_LEVELS entry (see that table's own
    comment for why it is not on this knob). swing_picks is the one field
    VARIANCE_LEVELS can't bake in statically, since "overall pick numbers"
    only mean something once teams/slot are known -- filled in here, only at
    the "Extreme" variance level (ff.VARIANCE_SWING_ENABLED), from this
    request's own League.
    """
    strategy = ff.VARIANCE_LEVELS[settings.variance]
    strategy = dataclasses.replace(
        strategy, model_influence=ff.MODEL_INFLUENCE_LEVELS[settings.model_influence])
    if ff.VARIANCE_SWING_ENABLED[settings.variance]:
        strategy = dataclasses.replace(strategy, swing_picks=tuple(league.pick_numbers()))
    return strategy


@app.post("/api/league", response_model=LeagueResponse)
def api_league(settings: LeagueSettingsRequest) -> LeagueResponse:
    league = build_league(settings)
    pool = POOLS[settings.scoring]
    board = ff.build_board(pool, league)
    repl = replacement_levels(board, league)
    starters = effective_starters(board, league)

    scarcity = [
        PositionScarcityRow(
            position=pos,
            effective_starters=starters.get(pos, 0),
            replacement_points=round(repl[pos], 1),
            top_vor=round(float(board.loc[board.position == pos, "vor"].max()), 1),
        )
        for pos in sorted(repl)
    ]

    strategy = build_strategy(settings, league)
    mi = ff.MODEL_INFLUENCE_LEVELS[settings.model_influence]
    comp = strategy.value_components(board)
    board = board.copy()
    board["our_value"] = comp["score"]
    board["our_range_lo"] = comp["effective_vor_p15"]
    board["our_range_hi"] = comp["effective_vor_p85"]
    board["bargain"] = mi * board["alpha"]

    top = board.sort_values("our_value", ascending=False).head(150)
    players = [
        PlayerRow(
            player_id=row.player_id,
            name=row.name,
            position=row.position,
            team=row.team,
            adp=round(row.adp, 1),
            expert_rank=None if math.isnan(row.expert_rank) else round(row.expert_rank, 1),
            expert_rank_lo=None if math.isnan(row.expert_rank_lo) else round(row.expert_rank_lo, 1),
            expert_rank_hi=None if math.isnan(row.expert_rank_hi) else round(row.expert_rank_hi, 1),
            our_value=round(row.our_value, 1),
            our_range_lo=round(row.our_range_lo, 1),
            our_range_hi=round(row.our_range_hi, 1),
            bargain=None if math.isnan(row.bargain) else round(row.bargain, 1),
            alpha=None if math.isnan(row.alpha) else round(row.alpha, 1),
        )
        for row in top.itertuples()
    ]

    pick_numbers = league.pick_numbers()
    picks = [
        PickChip(
            round=i + 1,
            overall_pick=overall,
            gap_to_next=(pick_numbers[i + 1] - overall) if i + 1 < len(pick_numbers) else None,
        )
        for i, overall in enumerate(pick_numbers)
    ]

    return LeagueResponse(
        pick_numbers=pick_numbers,
        hedge_window=league.hedge_window(),
        rounds=league.rounds,
        reserved_slots=league.reserved_slots,
        total_rounds=league.total_rounds,
        describe=league.describe(),
        scarcity=scarcity,
        players=players,
        picks=picks,
    )


def _positions_still_needed(mine_positions: list[str], league: "ff.League") -> set[str]:
    """Which starting positions aren't filled yet, given what `mine` holds.

    Display-only: this decides which positions are worth a tier-depletion
    flag, not a drafting decision, so it doesn't need _need_bonus's urgency
    weighting -- just "is there still an empty starting slot here."
    """
    counts: dict[str, int] = {}
    for p in mine_positions:
        counts[p] = counts.get(p, 0) + 1
    needed = {pos for pos in league.positions if counts.get(pos, 0) < league.lineup.get(pos, 0)}
    flex_req = league.lineup.get("FLEX", 0)
    flex_filled = sum(max(0, counts.get(p, 0) - league.lineup.get(p, 0)) for p in league.flex_eligible)
    if flex_filled < flex_req:
        needed.update(league.flex_eligible)
    return needed


@app.post("/api/next-pick", response_model=NextPickResponse)
def api_next_pick(req: NextPickRequest) -> NextPickResponse:
    """What to do right now, framed around your NEXT pick, not a ranked list.

    Replacement/VOR are never recomputed from what's left (see build_strategy/
    value_components -- same static board every other endpoint uses). What
    DOES change here: availability (ff.availability, at your next pick) and
    tier depletion, both filtered to players not yet gone.
    """
    league = build_league(req)
    pool = POOLS[req.scoring]
    board = ff.build_board(pool, league)

    strategy = build_strategy(req, league)
    comp = strategy.value_components(board)
    board = board.copy()
    board["our_value"] = comp["score"]

    gone = set(req.gone)
    available = board[~board["player_id"].isin(gone)].copy()

    pick_numbers = league.pick_numbers()
    next_pick = next((p for p in pick_numbers if p > req.current_pick), None)
    target_pick = req.target_pick if req.target_pick is not None else next_pick
    available["availability"] = (
        ff.availability(available, target_pick).to_numpy() if target_pick is not None else 1.0
    )

    ranked = available.sort_values("our_value", ascending=False).head(15)
    take_now: list[NextPickPlayerRow] = []
    can_wait: list[NextPickPlayerRow] = []
    for row in ranked.itertuples():
        item = NextPickPlayerRow(
            player_id=row.player_id, name=row.name, position=row.position, team=row.team,
            our_value=round(row.our_value, 1), availability=round(float(row.availability), 3),
        )
        (take_now if row.availability < 0.5 else can_wait).append(item)

    mine_positions = board.loc[board["player_id"].isin(set(req.mine)), "position"].tolist()
    tier_depletion = []
    for pos in sorted(_positions_still_needed(mine_positions, league)):
        pos_avail = available[available["position"] == pos]
        if pos_avail.empty:
            continue
        current_tier = int(pos_avail["tier"].min())
        remaining = int((pos_avail["tier"] == current_tier).sum())
        tier_depletion.append(TierDepletionRow(position=pos, tier=current_tier, remaining=remaining))

    return NextPickResponse(
        current_pick=req.current_pick,
        next_pick=next_pick,
        picks_away=(next_pick - req.current_pick) if next_pick is not None else None,
        target_pick=target_pick,
        hedge_window=league.hedge_window(),
        take_now=take_now,
        can_wait=can_wait,
        tier_depletion=tier_depletion,
    )


@app.post("/api/simulate", response_model=SimulateResponse)
def api_simulate(req: SimulateRequest) -> SimulateResponse:
    league = build_league(req)
    pool = POOLS[req.scoring]
    unknown = [s for s in req.strategies if s not in ff.PRESETS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown strategies: {unknown}")

    summary, _detail = ff.evaluate(pool, league, req.strategies, n_sims=req.n_sims, seed=0)

    results = [
        StrategyResultRow(
            strategy=row["strategy"],
            champ_pct=row["champ_%"],
            playoff_pct=row["playoff_%"],
            mean_pts=row["mean_pts"],
            p10_pts=row["P10_pts"],
            p85_pts=row["P85_pts"],
            ceiling_cvar=row["ceiling_CVaR"],
            mean_wins=row["mean_wins"],
        )
        for _, row in summary.iterrows()
    ]
    return SimulateResponse(results=results)
