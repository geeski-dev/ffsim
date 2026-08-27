"""FastAPI service bridging the ffsim model to the web UI.

Two endpoints with very different cost profiles:
  POST /api/league    -- single-digit milliseconds, fires on every settings change
  POST /api/simulate   -- tens of seconds, fires only on explicit user action

The player pool is deterministic (make_pool() is seeded), so it is built once
at import time and reused across every request.
"""
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
    PickChip,
    PlayerRow,
    PositionScarcityRow,
    SimulateRequest,
    SimulateResponse,
    StrategyResultRow,
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

    ceiling_weight = ff.PRESETS[settings.risk_profile].ceiling_weight
    board = board.copy()
    board["draft_score"] = (1 - ceiling_weight) * board["vor"] + ceiling_weight * board["vor_p85"]

    top = board.sort_values("draft_score", ascending=False).head(150)
    players = [
        PlayerRow(
            player_id=row.player_id,
            name=row.name,
            position=row.position,
            team=row.team,
            adp=round(row.adp, 1),
            vor=round(row.vor, 1),
            alpha=None if math.isnan(row.alpha) else round(row.alpha, 1),
            tier=int(row.tier),
            weekly_cv=round(row.weekly_cv, 3),
            draft_score=round(row.draft_score, 1),
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
