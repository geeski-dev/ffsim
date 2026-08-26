"""Week-by-week season simulation, then head-to-head schedule and playoffs.

Two design decisions carry most of the weight here.

Scoring a roster as a sum of projected points throws away everything that
matters -- weekly variance, byes, injuries, and the bench. So the season is
simulated week by week instead.

And lineups are set on *belief*, then scored on *reality*. You do not get to
pick your best player after the fact, which is why the best-ball convexity
argument does not apply to season-long. What you do get is information: after
a few weeks you know more than you did on draft day, and you can bench what
failed and stream a replacement. That option is worth more when your players
are genuinely high-variance in outcome, and it is the real mechanism behind a
ceiling strategy.
"""
from __future__ import annotations

from typing import Dict, List

import numpy as np
import pandas as pd

from .config import League

PRIOR_GAMES = 4.0     # how much draft-day projection outweighs early results


def simulate_player_weeks(board: pd.DataFrame, league: League, rng) -> tuple[np.ndarray, np.ndarray]:
    """Weekly points and availability for every player in one simulated season.

    Uncertainty enters at two levels: a season-long talent shock (did he break
    out or bust?) drawn from the cross-source projection spread, and weekly
    noise around whatever that season turned out to be.
    """
    n = len(board)
    W = league.total_weeks
    ppg = board["proj_ppg"].to_numpy()
    cv = board["weekly_cv"].to_numpy()
    spread = board["proj_spread"].to_numpy()
    byes = board["bye_week"].to_numpy()
    proj_games = board["proj_games"].to_numpy()

    # season-level outcome: the thing you were actually uncertain about
    season_mult = np.exp(rng.normal(-0.5 * spread ** 2, spread))
    true_ppg = np.clip(ppg * season_mult, 0.05, None)

    # weekly noise, gamma-shaped so it stays positive and is right-skewed
    sd = np.clip(true_ppg * cv, 0.05, None)
    shape = np.clip((true_ppg / sd) ** 2, 0.35, 400.0)
    scale = true_ppg / shape
    pts = rng.gamma(shape[:, None], scale[:, None], size=(n, W))

    # availability: bye plus a contiguous injury block
    avail = np.ones((n, W), dtype=bool)
    week_idx = np.arange(1, W + 1)
    avail &= byes[:, None] != week_idx[None, :]

    playable = W - 1
    target = np.clip(np.rint(rng.normal(np.minimum(proj_games, playable), 2.0)),
                     0, playable).astype(int)
    missed = playable - target
    for i in np.nonzero(missed > 0)[0]:
        m = int(missed[i])
        start = int(rng.integers(0, max(W - m, 1)))
        avail[i, start:start + m] = False

    pts = np.where(avail, pts, 0.0)
    return pts, avail


def _posterior(proj_ppg: np.ndarray, cum_pts: np.ndarray,
               cum_games: np.ndarray) -> np.ndarray:
    """Blend draft-day projection with what has actually happened so far."""
    return (PRIOR_GAMES * proj_ppg + cum_pts) / (PRIOR_GAMES + cum_games)


def _set_lineup(roster: List[int], posterior: np.ndarray, realized: np.ndarray,
                avail: np.ndarray, positions: np.ndarray,
                league: League) -> float:
    """Choose starters by belief, score them on reality."""
    healthy = [i for i in roster if avail[i]]
    used: set[int] = set()
    total = 0.0

    for pos, cnt in league.lineup.items():
        if pos == "FLEX":
            continue
        pool = sorted((i for i in healthy if positions[i] == pos and i not in used),
                      key=lambda i: -posterior[i])
        for i in pool[:cnt]:
            used.add(i)
            total += realized[i]

    flex_n = league.lineup.get("FLEX", 0)
    if flex_n:
        pool = sorted((i for i in healthy
                       if positions[i] in league.flex_eligible and i not in used),
                      key=lambda i: -posterior[i])
        for i in pool[:flex_n]:
            used.add(i)
            total += realized[i]
    return total


def simulate_season(board: pd.DataFrame, league: League,
                    rosters: Dict[int, List[int]], rng) -> Dict[str, np.ndarray]:
    """Run one full season: weekly scores for every team, waivers included."""
    pts, avail = simulate_player_weeks(board, league, rng)
    positions = board["position"].to_numpy()
    proj_ppg = board["proj_ppg"].to_numpy()
    n = len(board)

    rosters = {s: list(v) for s, v in rosters.items()}
    on_roster = np.zeros(n, dtype=bool)
    for v in rosters.values():
        on_roster[v] = True

    cum_pts = np.zeros(n)
    cum_games = np.zeros(n)

    W = league.total_weeks
    teams = sorted(rosters)
    weekly = {s: np.zeros(W) for s in teams}

    for w in range(W):
        post = _posterior(proj_ppg, cum_pts, cum_games)

        if league.waivers_enabled and w >= 2:
            free = np.nonzero(~on_roster)[0]
            if len(free):
                order = free[np.argsort(-post[free])]
                for s in teams:
                    if not len(order):
                        break
                    worst = min(rosters[s], key=lambda i: post[i])
                    best_fa = order[0]
                    if post[best_fa] > post[worst] + league.waiver_margin:
                        rosters[s].remove(worst)
                        rosters[s].append(int(best_fa))
                        on_roster[worst] = False
                        on_roster[best_fa] = True
                        order = order[1:]

        for s in teams:
            weekly[s][w] = _set_lineup(rosters[s], post, pts[:, w],
                                       avail[:, w], positions, league)

        played = avail[:, w]
        cum_pts[played] += pts[played, w]
        cum_games[played] += 1

    return {"weekly": weekly, "final_rosters": rosters}


# --------------------------------------------------------------------------
# head to head
# --------------------------------------------------------------------------

def _round_robin(teams: List[int], weeks: int) -> List[List[tuple[int, int]]]:
    """Circle-method schedule, repeated to fill the regular season."""
    t = list(teams)
    if len(t) % 2:
        t.append(-1)
    n = len(t)
    base = []
    for _ in range(n - 1):
        pairs = [(t[i], t[n - 1 - i]) for i in range(n // 2)
                 if t[i] != -1 and t[n - 1 - i] != -1]
        base.append(pairs)
        t = [t[0]] + [t[-1]] + t[1:-1]
    return [base[w % len(base)] for w in range(weeks)]


def play_league(league: League, weekly: Dict[int, np.ndarray]) -> Dict[int, dict]:
    """Regular season, seeding, and a single-elimination bracket."""
    teams = sorted(weekly)
    schedule = _round_robin(teams, league.regular_weeks)

    wins = {s: 0 for s in teams}
    pts_for = {s: 0.0 for s in teams}
    for w, pairs in enumerate(schedule):
        for a, b in pairs:
            sa, sb = weekly[a][w], weekly[b][w]
            pts_for[a] += sa
            pts_for[b] += sb
            if sa > sb:
                wins[a] += 1
            elif sb > sa:
                wins[b] += 1
            else:
                wins[a] += 0.5
                wins[b] += 0.5

    seeds = sorted(teams, key=lambda s: (-wins[s], -pts_for[s]))
    made = seeds[:league.playoff_teams]

    bracket = list(made)
    wk = 0
    playoff_weeks = list(league.playoff_weeks)
    while len(bracket) > 1 and wk < len(playoff_weeks):
        w_idx = playoff_weeks[wk] - 1
        nxt = []
        for i in range(len(bracket) // 2):
            a, b = bracket[i], bracket[len(bracket) - 1 - i]
            nxt.append(a if weekly[a][w_idx] >= weekly[b][w_idx] else b)
        bracket = nxt
        wk += 1
    champion = bracket[0] if bracket else None

    return {
        s: dict(
            wins=wins[s],
            points=pts_for[s],
            seed=seeds.index(s) + 1,
            made_playoffs=s in made,
            champion=(s == champion),
        )
        for s in teams
    }
