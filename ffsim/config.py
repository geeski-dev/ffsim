"""League configuration. Every parameter of the model lives here.

Nothing downstream hardcodes a league size, a scoring rule, or a roster shape.
Change a value in League and the replacement levels, tiers, positional values,
pick map, and simulator all recompute from it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass(frozen=True)
class Scoring:
    """Points per unit of component stat.

    Component-based on purpose: this is why the same player pool can be scored
    as half-PPR or full PPR without recollecting anything.
    """
    pass_yd: float = 0.04
    pass_td: float = 4.0
    interception: float = -2.0
    rush_yd: float = 0.10
    rush_td: float = 6.0
    reception: float = 0.5
    rec_yd: float = 0.10
    rec_td: float = 6.0
    fumble_lost: float = -2.0
    two_pt: float = 2.0

    @classmethod
    def half_ppr(cls) -> "Scoring":
        return cls(reception=0.5)

    @classmethod
    def ppr(cls) -> "Scoring":
        return cls(reception=1.0)

    @classmethod
    def standard(cls) -> "Scoring":
        return cls(reception=0.0)

    @classmethod
    def te_premium(cls, te_bonus: float = 0.5) -> "Scoring":
        # TE premium is handled as a per-position adjustment in scoring.py
        return cls(reception=0.5 + 0.0)


DEFAULT_LINEUP: Dict[str, int] = {
    "QB": 1,
    "RB": 2,
    "WR": 2,
    "TE": 1,
    "FLEX": 1,
}


@dataclass(frozen=True)
class League:
    """A complete league specification.

    Example
    -------
    >>> League(teams=10, slot=6, scoring=Scoring.half_ppr())
    >>> League(teams=12, slot=3, scoring=Scoring.ppr(), bench=7)
    """
    teams: int = 10
    slot: int = 6                       # your draft position, 1-indexed
    lineup: Dict[str, int] = field(default_factory=lambda: dict(DEFAULT_LINEUP))
    flex_eligible: Tuple[str, ...] = ("RB", "WR", "TE")
    bench: int = 6
    scoring: Scoring = field(default_factory=Scoring.half_ppr)
    reserved_slots: int = 2             # non-simulated roster spots, e.g. K/DST

    # season structure
    regular_weeks: int = 14
    playoff_weeks: Tuple[int, ...] = (15, 16, 17)
    playoff_teams: int = 4
    total_weeks: int = 17

    # in-season management
    waivers_enabled: bool = True
    waiver_margin: float = 1.5          # ppg edge required to make a swap

    def __post_init__(self):
        if not 1 <= self.slot <= self.teams:
            raise ValueError(f"slot {self.slot} outside 1..{self.teams}")
        if self.playoff_teams > self.teams:
            raise ValueError("playoff_teams exceeds teams")

    # ---- derived -------------------------------------------------------

    @property
    def starters(self) -> int:
        return sum(self.lineup.values())

    @property
    def roster_size(self) -> int:
        return self.starters + self.bench

    @property
    def rounds(self) -> int:
        return self.roster_size

    @property
    def total_rounds(self) -> int:
        return self.rounds + self.reserved_slots

    @property
    def total_picks(self) -> int:
        return self.rounds * self.teams

    @property
    def positions(self) -> Tuple[str, ...]:
        return tuple(p for p in self.lineup if p != "FLEX")

    def base_starters(self, pos: str) -> int:
        """League-wide starting slots at a position, before flex."""
        return self.lineup.get(pos, 0) * self.teams

    @property
    def flex_slots(self) -> int:
        return self.lineup.get("FLEX", 0) * self.teams

    def pick_numbers(self, slot: int | None = None) -> list[int]:
        """Overall pick numbers for a draft slot in a snake draft."""
        s = self.slot if slot is None else slot
        picks = []
        for r in range(self.rounds):
            if r % 2 == 0:
                picks.append(r * self.teams + s)
            else:
                picks.append(r * self.teams + (self.teams - s + 1))
        return picks

    def hedge_window(self, slot: int | None = None) -> int:
        """Shortest gap between consecutive picks.

        Measures how quickly you can respond after a swing goes wrong. Maximal
        at the turns (1 at slots 1 and N), minimal in the middle.
        """
        p = self.pick_numbers(slot)
        return min(b - a for a, b in zip(p, p[1:])) if len(p) > 1 else 0

    def slot_of_pick(self, overall: int) -> int:
        """Which draft slot owns a given overall pick number."""
        r, idx = divmod(overall - 1, self.teams)
        return idx + 1 if r % 2 == 0 else self.teams - idx

    def describe(self) -> str:
        lu = " / ".join(f"{v}{k}" for k, v in self.lineup.items())
        return (
            f"{self.teams}-team | {lu} | bench {self.bench} | "
            f"{self.scoring.reception} PPR | slot {self.slot} "
            f"(hedge window {self.hedge_window()})"
        )
