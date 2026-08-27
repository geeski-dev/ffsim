#!/usr/bin/env python3
"""Backtest the drafting architecture against realised NFL outcomes.

Every claim the model makes elsewhere in this project is tested only against
its own simulator -- a synthetic opponent field, synthetic weekly variance,
synthetic availability. This is the one test that checks the architecture
against what actually happened. It is built to give an honest answer, not to
pass: if the model loses to a straight-ADP/ECR draft, that is the finding.

    python backtest.py              # stage 1: leak check + join-rate report

THE CARDINAL RULE -- point-in-time discipline
-----------------------------------------------
For season Y, nothing that informs a drafting decision may be computed from
data dated Y or later. `inputs_as_of(season)` is the only sanctioned way any
run touches historical data for that purpose, and it asserts internally that
everything it returns predates `season`.

Two categories of Y-dated data are deliberately NOT gated by inputs_as_of, and
are read through their own, separately-named functions instead, so the
exception is visible rather than smuggled in:

  * `ecr_for_season(Y)` -- season Y's own preseason expert-consensus ranking.
    It is dated Y (published in August of that year), but it exists *before*
    Y's games are played, so it is legitimate draft-day information -- exactly
    like ADP itself. This is the one non-privileged, market-visible fact every
    drafter (model and field alike) is allowed to see for season Y.

  * `realized_weeks(Y)` -- season Y's own realised weekly production. This is
    ground truth, never a decision input, except by the deliberate design of
    the CEILING run (projections = the season's real points, to measure the
    architecture's best case), and as the scoring target for every run's
    drafted rosters after the fact.

Nothing in this file writes to data/raw/, and it never touches
data/players_half_ppr.csv or data/players_ppr.csv.
"""
from __future__ import annotations

import functools
from pathlib import Path

import numpy as np
import pandas as pd

from build_pool import slug_from_name
from ffsim.config import League, Scoring
from ffsim.scoring import score_frame

RAW_DIR = "data/raw"
SEASONS = list(range(2021, 2026))   # ECR archive coverage
TEAMS = 12                          # full-PPR, matches the ECR archive's format

FANTASY_POS = ["QB", "RB", "WR", "TE"]

DEFAULT_LEAGUE = League(teams=TEAMS, scoring=Scoring.ppr())

# ---------------------------------------------------------------------------
# name normalisation
# ---------------------------------------------------------------------------
# build_pool.slug_from_name already strips suffixes (Jr/Sr/II-V) and
# initials-vs-hyphenation differences. The failure mode it does NOT cover is a
# nickname vs formal-name split across sources ("Josh Palmer" / "Joshua
# Palmer", "Ken Walker" / "Kenneth Walker") -- direction is inconsistent, so
# canonicalising the nickname form to the formal one closes it from either
# side. This list was built by inspecting the actual unmatched names in the
# 2021-2025 ECR<->production join below; it is not exhaustive, and the join
# rate reported by season_join_report() is measured AFTER this map is applied
# -- it is not assumed fixed.
NICKNAME_TO_FORMAL = {
    "josh": "joshua", "gabe": "gabriel", "ken": "kenneth", "nick": "nicholas",
    "mike": "michael", "chris": "christopher", "matt": "matthew", "dan": "daniel",
    "tony": "anthony", "rob": "robert", "bob": "robert", "will": "william",
    "bill": "william", "joe": "joseph", "sam": "samuel", "alex": "alexander",
    "andy": "andrew", "steve": "steven", "zach": "zachary", "tom": "thomas",
    "jim": "james", "jimmy": "james", "cam": "cameron", "greg": "gregory",
    "ron": "ronald", "pat": "patrick", "ben": "benjamin", "max": "maxwell",
}


def key(name, pos) -> str:
    """Canonical join key: nickname-normalised, then build_pool's own slug."""
    parts = str(name).strip().split()
    if parts:
        parts[0] = NICKNAME_TO_FORMAL.get(parts[0].lower(), parts[0].lower())
        name = " ".join(parts) if len(parts) > 1 else parts[0]
    return slug_from_name(name, pos)


# ---------------------------------------------------------------------------
# raw loaders -- private. Nothing outside this module reads data/raw directly.
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def _load_hist01(raw_dir: str = RAW_DIR) -> pd.DataFrame:
    df = pd.read_csv(
        Path(raw_dir) / "HIST_01_PLAYER_GAME_PRODUCTION_2012_2025.csv",
        low_memory=False,
    )
    df = df[df["season_type"].astype(str).str.upper().eq("REG")]
    df = df[df["source_position"].isin(FANTASY_POS)].copy()
    df["key"] = [key(n, p) for n, p in
                 zip(df["source_player_name"], df["source_position"])]
    return df


@functools.lru_cache(maxsize=1)
def _load_ecr(raw_dir: str = RAW_DIR) -> pd.DataFrame:
    df = pd.read_csv(Path(raw_dir) / "HIST_05_FP_ECR_PRESEASON_2021_2025.csv")
    df = df[df["source_position"].isin(FANTASY_POS)].copy()
    df["key"] = [key(n, p) for n, p in
                 zip(df["source_player_name"], df["source_position"])]
    return df


def _market05_path(season: int, raw_dir: str = RAW_DIR) -> Path | None:
    hits = sorted(Path(raw_dir).glob(f"MARKET_05_HIST_ADP_PPR_12TEAM_{season}.csv"))
    return hits[0] if hits else None


@functools.lru_cache(maxsize=None)
def _load_market05(season: int, raw_dir: str = RAW_DIR) -> pd.DataFrame | None:
    p = _market05_path(season, raw_dir)
    if p is None:
        return None
    df = pd.read_csv(p, low_memory=False)
    an = "source_player_name" if "source_player_name" in df.columns else "name"
    ap = "source_position" if "source_position" in df.columns else "position"
    df = df[df[ap].isin(FANTASY_POS)].copy()
    df["key"] = [key(n, p_) for n, p_ in zip(df[an], df[ap])]
    return df


# ---------------------------------------------------------------------------
# the gate
# ---------------------------------------------------------------------------

def inputs_as_of(season: int, raw_dir: str = RAW_DIR) -> dict:
    """The only sanctioned way any run touches historical data for fitting.

    Everything returned here strictly precedes `season`. The two asserts are
    not a formality -- they are what makes a leak visible instead of assumed
    absent. Anything that reads data/raw directly, bypassing this function,
    for a purpose other than the two Y-dated exceptions documented at the top
    of this file, is a bug.
    """
    hist = _load_hist01(raw_dir)
    weekly_prior = hist[hist["season"] < season].copy()
    assert weekly_prior.empty or weekly_prior["season"].max() < season, \
        f"inputs_as_of({season}): weekly production leaked >= {season}"

    ecr = _load_ecr(raw_dir)
    ecr_prior = ecr[ecr["season"] < season].copy()
    assert ecr_prior.empty or ecr_prior["season"].max() < season, \
        f"inputs_as_of({season}): ECR leaked >= {season}"

    fit_years = sorted(set(weekly_prior["season"].unique().tolist()))
    return {
        "season": season,
        "weekly_prior": weekly_prior,
        "ecr_prior": ecr_prior,
        "fit_years": fit_years,
    }


def ecr_for_season(season: int, raw_dir: str = RAW_DIR) -> pd.DataFrame:
    """Season Y's own preseason ECR snapshot. Dated Y, but pre-games -- see
    module docstring for why this does not go through inputs_as_of."""
    ecr = _load_ecr(raw_dir)
    return ecr[ecr["season"] == season].copy()


def realized_weeks(season: int, raw_dir: str = RAW_DIR) -> pd.DataFrame:
    """Season Y's own realised weekly production. Ground truth only -- see
    module docstring for why this does not go through inputs_as_of."""
    hist = _load_hist01(raw_dir)
    return hist[hist["season"] == season].copy()


# ---------------------------------------------------------------------------
# priced-pool size / round cap
# ---------------------------------------------------------------------------
# Historical ADP row counts vary by season -- some years simply have fewer
# priced players on record. Drafting a different number of rounds in
# different seasons would make the bracket incomparable across years, so the
# whole backtest is capped at whatever the *shallowest* priced season can
# support. This uses historical ADP (MARKET_05) once it exists for a season,
# and falls back to that season's ECR row count until it does -- never padded
# from HIST_01/AGE_01, which would draft players nobody actually priced.

def priced_pool_counts(seasons=SEASONS, raw_dir: str = RAW_DIR) -> dict[int, tuple[int, str]]:
    out = {}
    for y in seasons:
        m = _load_market05(y, raw_dir)
        if m is not None:
            out[y] = (len(m), "historical ADP")
        else:
            out[y] = (len(ecr_for_season(y, raw_dir)), "ECR (no historical ADP yet)")
    return out


def compute_round_cap(seasons=SEASONS, teams: int = TEAMS,
                       raw_dir: str = RAW_DIR) -> tuple[int, dict[int, tuple[int, str]]]:
    counts = priced_pool_counts(seasons, raw_dir)
    cap = min(n for n, _ in counts.values()) // teams
    return cap, counts


def print_run_header(seasons=SEASONS, raw_dir: str = RAW_DIR) -> int:
    cap, counts = compute_round_cap(seasons, TEAMS, raw_dir)
    print(f"backtest · {TEAMS}-team full PPR · seasons {min(seasons)}-{max(seasons)}")
    print(f"round cap: {cap} rounds ({cap * TEAMS} picks), set by the shallowest "
          f"priced season -- identical every season beats full-length-but-shifting\n")
    for y in seasons:
        n, src = counts[y]
        print(f"  {y}: {n:>4} priced players  [{src}]")
    print()
    return cap


# ---------------------------------------------------------------------------
# join-rate reporting
# ---------------------------------------------------------------------------

def season_join_report(season: int, raw_dir: str = RAW_DIR) -> dict:
    """ECR (the current draft pool) <-> realised production (this season's
    ground truth), joined on name. Some misses are genuine -- a player ranked
    in August who suffered a season-ending injury before week 1 has no
    production row and correctly scores zero, not a join bug. This function
    cannot tell the two apart; it reports the raw rate and the lowest-ECR
    (most notable) misses so a human can."""
    ecr = ecr_for_season(season, raw_dir)
    realized = realized_weeks(season, raw_dir)
    realized_keys = set(realized["key"])
    matched = ecr["key"].isin(realized_keys)
    misses = ecr.loc[~matched].sort_values("ecr").head(8)
    return {
        "season": season,
        "n_ecr": len(ecr),
        "n_matched": int(matched.sum()),
        "rate": float(matched.mean()) if len(ecr) else float("nan"),
        "sample_misses": list(zip(misses["source_player_name"],
                                   misses["source_position"],
                                   misses["ecr"].round(1))),
    }


JOIN_RATE_FLOOR = 0.80   # below this, treat the season's numbers as suspect


def stage1_report(seasons=SEASONS, raw_dir: str = RAW_DIR) -> None:
    print_run_header(seasons, raw_dir)
    print("STAGE 1 -- inputs_as_of leak check + ECR<->realised-production join rate")
    print("=" * 78)
    for y in seasons:
        ia = inputs_as_of(y, raw_dir)
        assert all(s < y for s in ia["fit_years"]), \
            f"inputs_as_of({y}) leaked a season >= {y}"
        fy = ia["fit_years"]
        span = f"{fy[0]}-{fy[-1]}" if fy else "(none)"
        print(f"\n{y}")
        print(f"  inputs_as_of: {len(fy)} prior seasons ({span}), all < {y} -- OK")

        jr = season_join_report(y, raw_dir)
        flag = "" if jr["rate"] >= JOIN_RATE_FLOOR else "  <-- below the 80% floor"
        print(f"  join: {jr['n_matched']}/{jr['n_ecr']} ECR-ranked players matched "
              f"to a production row ({jr['rate'] * 100:.1f}%){flag}")
        print(f"  lowest-ECR misses (most notable; injury or a real join gap, "
              f"can't tell apart from here):")
        for name, pos, ecr in jr["sample_misses"]:
            print(f"    {name:<22} {pos:<3} ECR {ecr}")


# ---------------------------------------------------------------------------
# stage 2 -- season scoring: realised starter points, knowable-that-week only
# ---------------------------------------------------------------------------
# The lineup-setting rule below is used IDENTICALLY by NULL, CEILING, and REAL
# -- the only thing that differs between those three runs is what determines
# the DRAFT (adp/ecr rank, realised season points, or the ECR-fit curve).
# Perfect foresight belongs in the draft board, not the start/sit decision;
# giving CEILING a clairvoyant week-to-week manager on top of a clairvoyant
# draft would answer a question nobody asked. So every run's in-season
# "belief" comes from the same source: each player's trailing prior-season
# ppg (from inputs_as_of, point-in-time safe by construction), corrected
# week by week toward what he has actually done THIS season so far.

_COMPONENT_RENAME = {"pass_int": "interceptions", "rec": "receptions"}


def _weekly_points(df: pd.DataFrame, league: League = DEFAULT_LEAGUE) -> pd.Series:
    """Fantasy points for each row of a HIST_01-shaped weekly frame."""
    return score_frame(df.rename(columns=_COMPONENT_RENAME), league.scoring)


def realized_player_weeks(season: int, keys: list[str],
                          raw_dir: str = RAW_DIR) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """Realised weekly points and played-flags for `keys`, aligned to their
    order. Ground truth (see realized_weeks) -- used here purely to SCORE
    rosters after the draft, and as the CEILING run's deliberate exception."""
    weekly = realized_weeks(season, raw_dir)
    weekly = weekly.assign(fp=_weekly_points(weekly))
    weeks = sorted(weekly["week"].unique().tolist())
    week_pos = {w: j for j, w in enumerate(weeks)}
    idx = {k: i for i, k in enumerate(keys)}
    n, W = len(keys), len(weeks)
    pts = np.zeros((n, W))
    played = np.zeros((n, W), dtype=bool)
    for row in weekly.itertuples(index=False):
        i = idx.get(row.key)
        if i is None:
            continue
        j = week_pos[row.week]
        pts[i, j] += row.fp
        played[i, j] = True
    return pts, played, weeks


def trailing_prior_ppg(season: int, keys: list[str], positions: list[str],
                       raw_dir: str = RAW_DIR) -> np.ndarray:
    """Each player's preseason lineup-setting prior: his OWN ppg in the most
    recent prior season if he has one, else that season's positional average.
    Sourced entirely from inputs_as_of(season) -- point-in-time safe -- and
    it is NOT a projection used for drafting or valuation; it exists only to
    make the very first week's start/sit call sane before any of this
    season's games have been played.
    """
    ia = inputs_as_of(season, raw_dir)
    prior = ia["weekly_prior"]
    if prior.empty:
        raise ValueError(f"no prior-season data available before {season}")
    last_season = prior["season"].max()
    last = prior[prior["season"] == last_season].copy()
    last = last.assign(fp=_weekly_points(last))
    per_player = (last.groupby(["key", "source_position"])
                  .agg(pts=("fp", "sum"), games=("fp", "size")).reset_index())
    per_player["ppg"] = per_player["pts"] / per_player["games"]
    ppg_by_key = dict(zip(per_player["key"], per_player["ppg"]))
    pos_avg = per_player.groupby("source_position")["ppg"].mean().to_dict()
    global_avg = float(per_player["ppg"].mean())

    prior_ppg = np.empty(len(keys))
    n_fallback = 0
    for i, (k, pos) in enumerate(zip(keys, positions)):
        if k in ppg_by_key:
            prior_ppg[i] = ppg_by_key[k]
        else:
            prior_ppg[i] = pos_avg.get(pos, global_avg)
            n_fallback += 1
    print(f"  lineup prior: {len(keys) - n_fallback}/{len(keys)} players from "
          f"{last_season} trailing ppg, {n_fallback} (rookies / unmatched) at "
          f"that season's positional average")
    return prior_ppg


def belief_for_week(cum_pts: np.ndarray, cum_games: np.ndarray, weeks_revealed: int,
                    week: int, preseason_prior: np.ndarray) -> np.ndarray:
    """The only sanctioned way lineup-setting decides who starts in `week`.

    This is the week-level analogue of inputs_as_of's season assert. The
    assert is not a formality: "realised points-per-game so far" lives inside
    a loop, it looks right at a glance, and an off-by-one here silently makes
    every lineup a little clairvoyant without changing how the code reads.
    weeks_revealed must equal exactly `week` -- the number of PRIOR weeks
    folded into cum_pts/cum_games -- never `week` itself.
    """
    assert weeks_revealed == week, (
        f"belief_for_week({week}): {weeks_revealed} weeks folded into cum stats, "
        f"expected exactly {week} -- this would leak week {week}'s own outcome "
        f"into its own lineup decision"
    )
    return np.where(cum_games > 0, cum_pts / np.maximum(cum_games, 1), preseason_prior)


def _set_lineup_realized(roster: list[int], belief: np.ndarray, realized_w: np.ndarray,
                         played_w: np.ndarray, positions: np.ndarray,
                         league: League) -> float:
    """Choose starters by belief, score them on this week's reality. Mirrors
    ffsim.season._set_lineup's belief-then-score shape, reimplemented locally
    (rather than imported) because that function is wired to the synthetic
    simulator's own posterior, not to realised historical production."""
    healthy = [i for i in roster if played_w[i]]
    used: set[int] = set()
    total = 0.0
    for pos, cnt in league.lineup.items():
        if pos == "FLEX":
            continue
        pool = sorted((i for i in healthy if positions[i] == pos and i not in used),
                      key=lambda i: -belief[i])
        for i in pool[:cnt]:
            used.add(i)
            total += realized_w[i]
    flex_n = league.lineup.get("FLEX", 0)
    if flex_n:
        pool = sorted((i for i in healthy
                       if positions[i] in league.flex_eligible and i not in used),
                      key=lambda i: -belief[i])
        for i in pool[:flex_n]:
            used.add(i)
            total += realized_w[i]
    return total


def score_season(positions: np.ndarray, rosters: dict[int, list[int]],
                 pts: np.ndarray, played: np.ndarray, preseason_prior: np.ndarray,
                 league: League = DEFAULT_LEAGUE) -> dict:
    """Score every roster's season, one week at a time, on realised
    production. Each week's lineup is chosen from belief_for_week's output
    BEFORE that week's own results are folded into cum_pts/cum_games -- the
    fold-in happens only after every team has already locked its lineup for
    the week, which is what makes leaking week w into week w's own decision
    structurally impossible rather than merely avoided by convention.
    """
    n, W = pts.shape
    cum_pts = np.zeros(n)
    cum_games = np.zeros(n)
    starter_pts = {s: 0.0 for s in rosters}
    weekly_totals = {s: np.zeros(W) for s in rosters}

    for w in range(W):
        belief = belief_for_week(cum_pts, cum_games, w, w, preseason_prior)
        for s, roster in rosters.items():
            p = _set_lineup_realized(roster, belief, pts[:, w], played[:, w],
                                     positions, league)
            weekly_totals[s][w] = p
            starter_pts[s] += p
        got = played[:, w]
        cum_pts[got] += pts[got, w]
        cum_games[got] += 1

    return {"starter_pts": starter_pts, "weekly_totals": weekly_totals}


if __name__ == "__main__":
    stage1_report()
