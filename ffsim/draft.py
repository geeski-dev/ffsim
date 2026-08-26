"""The draft engine: snake logic, opponent behaviour, and drafting policies.

The opponent model is where most draft simulators quietly fail. Three things
matter and are implemented here:

1. Positional runs. Real drafts cascade -- three RBs go and everyone panics.
   A simulator without contagion tells you "you can always wait", which is the
   most expensive wrong answer a draft tool can give.
2. Roster need. Nobody takes a fourth RB in round 6.
3. Asymmetric ADP noise. Players fall further than they rise.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd

from .config import League

RUN_WINDOW = 8


# --------------------------------------------------------------------------
# roster bookkeeping
# --------------------------------------------------------------------------

def roster_caps(league: League) -> Dict[str, int]:
    """Soft maximum a sane manager will roster at each position."""
    flex = league.lineup.get("FLEX", 0)
    caps = {}
    for pos in league.positions:
        base = league.lineup.get(pos, 0)
        if pos in league.flex_eligible:
            caps[pos] = base + flex + max(2, league.bench // 2)
        else:
            caps[pos] = base + 1
    return caps


def unfilled_starters(counts: Dict[str, int], league: League) -> int:
    """How many starting slots this roster still cannot fill."""
    need, surplus = 0, 0
    for pos in league.positions:
        req = league.lineup.get(pos, 0)
        have = counts.get(pos, 0)
        if have < req:
            need += req - have
        elif pos in league.flex_eligible:
            surplus += have - req
    flex_need = max(0, league.lineup.get("FLEX", 0) - surplus)
    return need + flex_need


def _need_bonus(pos: str, counts: Dict[str, int], league: League,
                picks_left: int) -> float:
    """Points-equivalent urgency of filling a starting slot at `pos`."""
    req = league.lineup.get(pos, 0)
    have = counts.get(pos, 0)
    if have < req:
        urgency = 1.0 + 2.0 * max(0.0, 1.0 - picks_left / max(league.rounds, 1))
        return 22.0 * urgency
    if pos in league.flex_eligible and unfilled_starters(counts, league) > 0:
        return 8.0
    return 0.0


# --------------------------------------------------------------------------
# opponents
# --------------------------------------------------------------------------

@dataclass
class Personality:
    """One opposing manager's behavioural fingerprint.

    Estimated from your own knowledge of the league. The default is a
    competent ADP drafter; real leaguemates deviate in knowable ways.
    """
    name: str = "adp"
    reach_sd: float = 8.0                # deviation from consensus ADP
    pos_bias: Dict[str, float] = field(default_factory=dict)  # negative = earlier
    need_weight: float = 1.0
    run_sensitivity: float = 1.0
    bpa_weight: float = 0.15             # 0 = pure ADP, 1 = pure value

    def choose(self, board: pd.DataFrame, avail: np.ndarray,
               counts: Dict[str, int], league: League, picks_left: int,
               recent: Sequence[str], rng) -> int:
        caps = roster_caps(league)
        pos = board["position"].to_numpy()

        legal = avail.copy()
        for p, cap in caps.items():
            if counts.get(p, 0) >= cap:
                legal &= pos != p
        if not legal.any():
            legal = avail.copy()

        # must be able to field a lineup by the end
        if picks_left <= unfilled_starters(counts, league):
            forced = _forced_positions(counts, league)
            if forced:
                mask = legal & np.isin(pos, list(forced))
                if mask.any():
                    legal = mask

        adp = board["adp"].to_numpy()
        noise = rng.normal(0.0, self.reach_sd, len(board))
        bias = np.array([self.pos_bias.get(p, 0.0) for p in pos])
        perceived = adp + noise + bias

        run_counts = {p: list(recent).count(p) for p in set(pos)}
        run = np.array([run_counts.get(p, 0) for p in pos]) * 3.0 * self.run_sensitivity
        need = np.array([_need_bonus(p, counts, league, picks_left) for p in pos])

        vor_z = board["vor"].to_numpy()
        vor_z = (vor_z - vor_z.mean()) / (vor_z.std(ddof=0) + 1e-9)

        score = -perceived + run + self.need_weight * need * 0.55 + self.bpa_weight * vor_z * 25.0
        score = np.where(legal, score, -np.inf)
        return int(np.argmax(score))


def _forced_positions(counts: Dict[str, int], league: League) -> set[str]:
    forced = set()
    for pos in league.positions:
        if counts.get(pos, 0) < league.lineup.get(pos, 0):
            forced.add(pos)
    if not forced and unfilled_starters(counts, league) > 0:
        forced = set(league.flex_eligible)
    return forced


ARCHETYPES: Dict[str, Personality] = {
    "adp":        Personality("adp", reach_sd=7.0, bpa_weight=0.10),
    "sharp":      Personality("sharp", reach_sd=5.0, bpa_weight=0.55, run_sensitivity=0.6),
    "homer":      Personality("homer", reach_sd=15.0, bpa_weight=0.05, run_sensitivity=1.3),
    "qb_early":   Personality("qb_early", reach_sd=9.0, pos_bias={"QB": -32.0}),
    "te_early":   Personality("te_early", reach_sd=9.0, pos_bias={"TE": -22.0}),
    "rb_heavy":   Personality("rb_heavy", reach_sd=9.0, pos_bias={"RB": -14.0}, run_sensitivity=1.4),
    "zero_rb":    Personality("zero_rb", reach_sd=9.0, pos_bias={"RB": 20.0, "WR": -10.0}),
    "asleep":     Personality("asleep", reach_sd=22.0, bpa_weight=0.0, need_weight=0.4),
}


def default_field(league: League, rng) -> Dict[int, Personality]:
    """A plausible mix of opponents when you have no leaguemate intel."""
    names = ["adp", "adp", "sharp", "homer", "qb_early", "te_early",
             "rb_heavy", "zero_rb", "asleep", "adp", "sharp", "homer"]
    field_ = {}
    j = 0
    for slot in range(1, league.teams + 1):
        if slot == league.slot:
            continue
        field_[slot] = ARCHETYPES[names[j % len(names)]]
        j += 1
    return field_


# --------------------------------------------------------------------------
# your drafting policy
# --------------------------------------------------------------------------

@dataclass
class Strategy:
    """A parameterised drafting policy.

    Rather than rigid scripts ("Zero RB"), a strategy is a small vector of
    preferences. That makes the strategy space searchable instead of a handful
    of named recipes.
    """
    name: str = "balanced"
    ceiling_weight: float = 0.0      # 0 = draft the median, 1 = draft the 85th pct
    risk_penalty: float = 0.0        # points docked per SD of availability risk
    pos_bonus: Dict[str, float] = field(default_factory=dict)
    early_rounds: int = 3
    ev_cap: float = 0.10             # max fraction of best-available VOR surrendered early
    swing_picks: tuple = ()          # overall pick numbers where ceiling_weight doubles

    def choose(self, board: pd.DataFrame, avail: np.ndarray,
               counts: Dict[str, int], league: League, picks_left: int,
               recent: Sequence[str], rng, overall: int = 0,
               rnd: int = 1) -> int:
        caps = roster_caps(league)
        pos = board["position"].to_numpy()

        legal = avail.copy()
        for p, cap in caps.items():
            if counts.get(p, 0) >= cap:
                legal &= pos != p
        if not legal.any():
            legal = avail.copy()

        if picks_left <= unfilled_starters(counts, league):
            forced = _forced_positions(counts, league)
            if forced:
                mask = legal & np.isin(pos, list(forced))
                if mask.any():
                    legal = mask

        vor = board["vor"].to_numpy()
        vor_p85 = board["vor_p85"].to_numpy()

        cw = self.ceiling_weight
        if overall in self.swing_picks:
            cw = min(1.0, cw * 2.0)
        blended = (1 - cw) * vor + cw * vor_p85

        bonus = np.array([self.pos_bonus.get(p, 0.0) for p in pos])
        need = np.array([_need_bonus(p, counts, league, picks_left) for p in pos])
        risk = board["risk_index"].to_numpy() * self.risk_penalty * 10.0

        score = blended + bonus + need * 0.6 - risk

        # EV sacrifice cap: in the early rounds you may only chase upside among
        # players whose median value is within ev_cap of the best available.
        if rnd <= self.early_rounds:
            legal_vor = np.where(legal, vor, -np.inf)
            best = legal_vor.max()
            if np.isfinite(best):
                floor = best - self.ev_cap * abs(best)
                capped = legal & (vor >= floor)
                if capped.any():
                    legal = capped

        score = np.where(legal, score, -np.inf)
        return int(np.argmax(score))


PRESETS: Dict[str, Strategy] = {
    "bpa":       Strategy("bpa", ceiling_weight=0.0, ev_cap=0.02),
    "balanced":  Strategy("balanced", ceiling_weight=0.25, risk_penalty=0.4, ev_cap=0.08),
    "ceiling":   Strategy("ceiling", ceiling_weight=0.75, risk_penalty=0.0, ev_cap=0.12),
    "max_ceiling": Strategy("max_ceiling", ceiling_weight=1.0, risk_penalty=-0.2, ev_cap=0.25),
    "safe":      Strategy("safe", ceiling_weight=0.0, risk_penalty=1.2, ev_cap=0.03),
    # a real zero-RB tilt delays running backs, it does not refuse them; a
    # large negative bonus produces a roster that cannot fill its lineup
    "zero_rb":   Strategy("zero_rb", ceiling_weight=0.4, pos_bonus={"RB": -12.0, "WR": 6.0}, ev_cap=0.20),
    "hero_rb":   Strategy("hero_rb", ceiling_weight=0.4, pos_bonus={"RB": 10.0}, ev_cap=0.15),
}


# --------------------------------------------------------------------------
# the draft itself
# --------------------------------------------------------------------------

def run_draft(board: pd.DataFrame, league: League, strategy: Strategy,
              field_: Dict[int, Personality], rng) -> Dict[int, List[int]]:
    """Simulate one full snake draft. Returns slot -> list of board row indices."""
    n = len(board)
    avail = np.ones(n, dtype=bool)
    rosters: Dict[int, List[int]] = {s: [] for s in range(1, league.teams + 1)}
    counts: Dict[int, Dict[str, int]] = {s: {} for s in range(1, league.teams + 1)}
    recent = deque(maxlen=RUN_WINDOW)
    pos_arr = board["position"].to_numpy()

    my_picks = set(league.pick_numbers())

    for overall in range(1, league.total_picks + 1):
        slot = league.slot_of_pick(overall)
        rnd = (overall - 1) // league.teams + 1
        picks_left = league.rounds - len(rosters[slot])

        if slot == league.slot:
            idx = strategy.choose(board, avail, counts[slot], league,
                                  picks_left, recent, rng, overall, rnd)
        else:
            idx = field_[slot].choose(board, avail, counts[slot], league,
                                      picks_left, recent, rng)

        avail[idx] = False
        rosters[slot].append(idx)
        p = pos_arr[idx]
        counts[slot][p] = counts[slot].get(p, 0) + 1
        recent.append(p)

    assert my_picks  # pick map sanity
    return rosters
