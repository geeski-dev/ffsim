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
    downside_weight: float = 0.0     # points docked per point of floor collapse (vor - vor_p15)
    model_influence: float = 1.0     # 0 = market-implied value, 1 = model VOR
    pos_bonus: Dict[str, float] = field(default_factory=dict)
    early_rounds: int = 3
    ev_cap: float = 0.10             # max fraction of best-available VOR surrendered early
    swing_picks: tuple = ()          # overall pick numbers where ceiling_weight doubles

    def value_components(self, board: pd.DataFrame, overall: int = 0) -> Dict[str, np.ndarray]:
        """The model's per-player value, independent of roster context.

        No positional need bonus, no legality/EV-cap masking -- those only
        mean anything mid-draft. This is the one place the model_influence
        blend and the ceiling/risk/downside score are computed, shared by
        choose() (which adds roster context on top) and by any static-board
        caller, e.g. the API's player valuation table, so there is exactly
        one implementation of the blend math to keep in sync.
        """
        vor = board["vor"].to_numpy()
        vor_p85 = board["vor_p85"].to_numpy()
        vor_p15 = board["vor_p15"].to_numpy()
        mi = self.model_influence
        if mi == 1.0 or "market_implied_vor" not in board.columns:
            effective_vor = vor
            effective_vor_p85 = vor_p85
            effective_vor_p15 = vor_p15
        else:
            market = board["market_implied_vor"].to_numpy()
            priced = np.isfinite(market)
            effective_vor = np.where(priced, market + mi * (vor - market), vor)
            # Anchor the floor/ceiling to the (possibly market-shifted) center
            # and add back the model's OWN raw upside/downside gap, rather
            # than blending vor_p85/vor_p15 independently toward the same
            # flat market scalar. The latter (Stage 1's original approach)
            # collapses vor/vor_p85/vor_p15 onto one number the moment
            # mi=0.0 -- there is only one market_implied_vor, not a separate
            # market-implied p85/p15 -- which would make ceiling_weight and
            # downside_weight (Variance) silent no-ops at model_influence
            # "Off", contradicting the requirement that Variance stay fully
            # active there (chasing ceiling among market-priced players is
            # untested and unrejected; Off must not disable testing it).
            # Bit-identical with the old formula at mi=1.0 (gap added to
            # vor itself) and at mi=0.0 on unpriced rows (gap added to vor).
            effective_vor_p85 = np.where(priced, effective_vor + (vor_p85 - vor), vor_p85)
            effective_vor_p15 = np.where(priced, effective_vor - (vor - vor_p15), vor_p15)

        cw = self.ceiling_weight
        if overall in self.swing_picks:
            cw = min(1.0, cw * 2.0)
        blended = (1 - cw) * effective_vor + cw * effective_vor_p85

        risk = board["risk_index"].to_numpy() * self.risk_penalty * 10.0
        # size of the floor collapse, not its level -- vor is already in the
        # blended term, so this must not double-count it
        downside = (effective_vor - effective_vor_p15) * self.downside_weight

        return {
            "effective_vor": effective_vor,
            "effective_vor_p85": effective_vor_p85,
            "effective_vor_p15": effective_vor_p15,
            "score": blended - risk - downside,
        }

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

        comp = self.value_components(board, overall)
        effective_vor = comp["effective_vor"]

        bonus = np.array([self.pos_bonus.get(p, 0.0) for p in pos])
        need = np.array([_need_bonus(p, counts, league, picks_left) for p in pos])

        score = comp["score"] + bonus + need * 0.6

        # EV sacrifice cap: in the early rounds you may only chase upside among
        # players whose median value is within ev_cap of the best available.
        if rnd <= self.early_rounds:
            legal_vor = np.where(legal, effective_vor, -np.inf)
            best = legal_vor.max()
            if np.isfinite(best):
                floor = best - self.ev_cap * abs(best)
                capped = legal & (effective_vor >= floor)
                if capped.any():
                    legal = capped

        score = np.where(legal, score, -np.inf)
        return int(np.argmax(score))


PRESETS: Dict[str, Strategy] = {
    "bpa":       Strategy("bpa", ceiling_weight=0.0, ev_cap=0.02),
    "balanced":  Strategy("balanced", ceiling_weight=0.25, risk_penalty=0.4, ev_cap=0.08),
    "ceiling":   Strategy("ceiling", ceiling_weight=0.75, risk_penalty=0.0, ev_cap=0.12),
    "max_ceiling": Strategy("max_ceiling", ceiling_weight=1.0, risk_penalty=0.0, ev_cap=0.25),
    # chase the ceiling, refuse the cliff: same as max_ceiling, but docks
    # points for a steep floor collapse instead of ignoring it
    "ceiling_guarded": Strategy("ceiling_guarded", ceiling_weight=1.0, risk_penalty=0.0,
                                downside_weight=0.35, ev_cap=0.25),
    "safe":      Strategy("safe", ceiling_weight=0.0, risk_penalty=1.2, ev_cap=0.03),
    # a real zero-RB tilt delays running backs, it does not refuse them; a
    # large negative bonus produces a roster that cannot fill its lineup
    "zero_rb":   Strategy("zero_rb", ceiling_weight=0.4, pos_bonus={"RB": -12.0, "WR": 6.0}, ev_cap=0.20),
    "hero_rb":   Strategy("hero_rb", ceiling_weight=0.4, pos_bonus={"RB": 10.0}, ev_cap=0.15),
}


# --------------------------------------------------------------------------
# the app's two knobs: Variance and Model Influence
# --------------------------------------------------------------------------
# Separate from PRESETS above -- PRESETS are named whole-strategy recipes
# used by the backtest/simulator; these are the two independent dials the
# web app exposes. risk_penalty is deliberately NOT part of the Variance
# table: it is held constant at 0.25 for every level. Measured reason: the
# "safe" preset (risk_penalty=1.2) is dominated on BOTH axes by max_ceiling
# in the stage-5 backtest sweep -- fewer titles (4.79% vs 7.71%) and MORE
# bottom-three finishes (44.4% vs 39.8%) -- because injury risk correlates
# with being good (McCaffrey's miss_rate sits at the top of the top 16), so
# a large risk penalty doesn't buy safety, it buys avoiding elite players.
# Putting risk_penalty on this knob would make "Low" produce more disasters,
# not fewer.
VARIANCE_LEVELS: Dict[str, Strategy] = {
    "Low":     Strategy("Low", ceiling_weight=0.0, risk_penalty=0.25, downside_weight=0.35, ev_cap=0.05),
    "Medium":  Strategy("Medium", ceiling_weight=0.3, risk_penalty=0.25, downside_weight=0.20, ev_cap=0.10),
    "High":    Strategy("High", ceiling_weight=0.7, risk_penalty=0.25, downside_weight=0.10, ev_cap=0.20),
    "Extreme": Strategy("Extreme", ceiling_weight=1.0, risk_penalty=0.25, downside_weight=0.00, ev_cap=0.35),
}

# swing_picks is a set of OVERALL pick numbers -- inherently specific to a
# league (team count and draft slot), so it can't be baked into a static
# preset here. This flag says which variance levels want it turned on; the
# caller (the API, once it has a real League) fills in the actual pick
# numbers via dataclasses.replace(..., swing_picks=tuple(league.pick_numbers())).
VARIANCE_SWING_ENABLED: Dict[str, bool] = {
    "Low": False, "Medium": False, "High": False, "Extreme": True,
}

# Off = look at the market's own board, Extreme = look at only ours. Applied
# via Strategy.model_influence (see value_components). The API defaults to
# "Off" -- see the app's own "do not" list: no evidence the model beats the
# market, so the default must not assert otherwise.
MODEL_INFLUENCE_LEVELS: Dict[str, float] = {
    "Off": 0.0, "Low": 0.25, "Medium": 0.5, "High": 0.75, "Extreme": 1.0,
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
