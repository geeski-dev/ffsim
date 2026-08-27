#!/usr/bin/env python3
"""Backtest the drafting architecture against realised NFL outcomes.

Every claim the model makes elsewhere in this project is tested only against
its own simulator -- a synthetic opponent field, synthetic weekly variance,
synthetic availability. This is the one test that checks the architecture
against what actually happened. It is built to give an honest answer, not to
pass: if the model loses to a straight-ADP/ECR draft, that is the finding.

    python backtest.py              # stage 1: leak check + join-rate report
    python -c "import backtest; backtest.stage3_report()"   # NULL vs CEILING

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

import dataclasses
import functools
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd

from build_pool import slug_from_name
from ffsim.config import League, Scoring
from ffsim.draft import ARCHETYPES, PRESETS, Personality, Strategy, default_field
from ffsim.scoring import score_frame
from ffsim.valuation import replacement_levels

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
    "josh": "joshua", "gabe": "gabriel", "ken": "kenneth", "kenny": "kenneth",
    "nick": "nicholas", "mike": "michael", "chris": "christopher", "matt": "matthew",
    "dan": "daniel", "tony": "anthony", "rob": "robert", "bob": "robert",
    "will": "william", "bill": "william", "joe": "joseph", "sam": "samuel",
    "alex": "alexander", "andy": "andrew", "steve": "steven", "zach": "zachary",
    "tom": "thomas", "jim": "james", "jimmy": "james", "cam": "cameron",
    "greg": "gregory", "ron": "ronald", "pat": "patrick", "ben": "benjamin",
    "max": "maxwell",
}

# Full-name substitutions that don't fit the first-token nickname pattern
# above (a stage-name, not a diminutive of the formal first name). Found by
# inspecting the ADP<->realised-production join misses in season_join_report.
FULL_NAME_ALIASES = {
    "hollywood brown": "marquise brown",
}


def key(name, pos) -> str:
    """Canonical join key: nickname/alias-normalised, then build_pool's slug."""
    parts = str(name).strip().split()
    if parts:
        parts[0] = NICKNAME_TO_FORMAL.get(parts[0].lower(), parts[0].lower())
        name = " ".join(parts) if len(parts) > 1 else parts[0]
    name = FULL_NAME_ALIASES.get(name.lower(), name)
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

def priced_baseline(season: int, raw_dir: str = RAW_DIR) -> tuple[pd.DataFrame, str]:
    """The baseline draft pool for `season` -- what every run's opponents
    (and NULL's own team) draft from: historical ADP (MARKET_05) when it
    exists for this season, that season's ECR order otherwise. Never padded
    with players from any other source ("do not fill beyond the priced pool
    from any other source"). Returns (frame[key,name,position,adp], label).
    """
    m = _load_market05(season, raw_dir)
    if m is not None:
        out = pd.DataFrame({
            "key": m["key"].to_numpy(),
            "name": m["source_player_name"].to_numpy(),
            "position": m["source_position"].to_numpy(),
            "adp": m["adp_overall"].to_numpy(dtype=float),
        })
        return out, "historical ADP"
    ecr = ecr_for_season(season, raw_dir)
    out = pd.DataFrame({
        "key": ecr["key"].to_numpy(),
        "name": ecr["source_player_name"].to_numpy(),
        "position": ecr["source_position"].to_numpy(),
        "adp": ecr["ecr"].to_numpy(dtype=float),
    })
    return out, "ECR (no historical ADP yet)"


def priced_pool_counts(seasons=SEASONS, raw_dir: str = RAW_DIR) -> dict[int, tuple[int, str]]:
    return {y: (len(priced_baseline(y, raw_dir)[0]), priced_baseline(y, raw_dir)[1])
            for y in seasons}


def priced_join_report(season: int, raw_dir: str = RAW_DIR) -> dict:
    """Same idea as season_join_report, but against whichever pool actually
    feeds the draft (priced_baseline), not always ECR. This is what stage 3
    and onward actually depend on."""
    base, source = priced_baseline(season, raw_dir)
    realized = realized_weeks(season, raw_dir)
    realized_keys = set(realized["key"])
    matched = base["key"].isin(realized_keys)
    misses = base.loc[~matched].sort_values("adp").head(5)
    return {
        "season": season, "source": source, "n": len(base),
        "n_matched": int(matched.sum()),
        "rate": float(matched.mean()) if len(base) else float("nan"),
        "sample_misses": list(zip(misses["name"], misses["position"], misses["adp"].round(1))),
    }


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


# ---------------------------------------------------------------------------
# stage 3 -- NULL and CEILING: one draft simulation, three information regimes
# ---------------------------------------------------------------------------
# A GENUINE DEVIATION FROM ffsim/draft.py, disclosed rather than worked
# around: ffsim.draft.run_draft takes exactly one rng, shared by the model's
# own pick and every opponent's pick, consumed in snake order. That is fine
# for the existing simulator, where every team draws from the same board.
# Here it would silently break "identical opponent behaviour ... across all
# three runs" (approved design): NULL's model picks via a stochastic
# Personality (consumes rng draws), CEILING/REAL's model picks via a
# deterministic Strategy (consumes none), so a single shared rng desyncs the
# ELEVEN OPPONENTS' draws from each other the moment the model's stochastic
# footprint differs between runs -- exactly the "draft luck" the common-
# random-numbers requirement exists to remove. run_backtest_draft below is a
# ~20-line reimplementation of run_draft's own loop (unchanged snake logic,
# unchanged Strategy/Personality.choose calls) with two independent rng
# streams: one that only ever touches the model's own slot, one shared by the
# eleven opponents. This is not a modification of ffsim/draft.py -- it is a
# local loop that calls ffsim's own Strategy/Personality objects, because
# their shared-rng signature is what blocks the two-stream design.

NULL_ARCHETYPE_ROTATION = ["adp", "adp", "sharp", "homer", "qb_early", "te_early",
                           "rb_heavy", "zero_rb", "asleep", "adp", "sharp", "homer"]


def run_backtest_draft(board: pd.DataFrame, league: League, model_policy,
                       field_: dict[int, Personality], rng_model, rng_opponents
                       ) -> dict[int, list[int]]:
    n = len(board)
    avail = np.ones(n, dtype=bool)
    rosters: dict[int, list[int]] = {s: [] for s in range(1, league.teams + 1)}
    counts: dict[int, dict[str, int]] = {s: {} for s in range(1, league.teams + 1)}
    recent = deque(maxlen=8)   # RUN_WINDOW in ffsim.draft
    pos_arr = board["position"].to_numpy()

    for overall in range(1, league.total_picks + 1):
        slot = league.slot_of_pick(overall)
        rnd = (overall - 1) // league.teams + 1
        picks_left = league.rounds - len(rosters[slot])

        if slot == league.slot:
            if isinstance(model_policy, Strategy):
                idx = model_policy.choose(board, avail, counts[slot], league,
                                          picks_left, recent, rng_model, overall, rnd)
            else:
                idx = model_policy.choose(board, avail, counts[slot], league,
                                          picks_left, recent, rng_model)
        else:
            idx = field_[slot].choose(board, avail, counts[slot], league,
                                      picks_left, recent, rng_opponents)

        avail[idx] = False
        rosters[slot].append(idx)
        p = pos_arr[idx]
        counts[slot][p] = counts[slot].get(p, 0) + 1
        recent.append(p)
    return rosters


def _blind_field(league: League) -> dict[int, Personality]:
    """The eleven opponents, informationally identical across NULL/CEILING/
    REAL: default_field's usual archetype mix and reach noise, with
    bpa_weight zeroed so they are mathematically insensitive to whichever
    'vor' column the model's own run has attached to the shared board.
    Without this, CEILING would leak a sliver of perfect foresight into the
    field too. (Approved design, stage-1 report judgment call #1.)"""
    base = default_field(league, None)   # default_field never reads rng
    return {slot: dataclasses.replace(p, bpa_weight=0.0) for slot, p in base.items()}


def _null_model_policy(league: League) -> Personality:
    """NULL's own team is an ordinary field member, not a special case: the
    same archetype the rotation would hand an opponent sitting in this seat,
    also blinded to vor for the same cross-run parity reason as the field.
    This is what makes NULL a free self-test of the harness -- see review
    note 1: with no informational edge over the field, it should finish
    mid-pack, and a systematic deviation is a harness bug, not a finding."""
    arche = NULL_ARCHETYPE_ROTATION[(league.slot - 1) % len(NULL_ARCHETYPE_ROTATION)]
    return dataclasses.replace(ARCHETYPES[arche], bpa_weight=0.0)


def _capped_league(base: League, round_cap: int) -> League:
    """Apply the round cap (see priced_pool_counts / compute_round_cap) by
    adjusting bench size, since League.rounds is starters+bench and
    ffsim.draft.run_draft has no separate round-count parameter. A no-op
    while the cap doesn't bind (today: ECR-derived, ~35 rounds, well above
    the default 13); becomes load-bearing once historical ADP lands with
    materially shallower per-season pools."""
    if base.rounds <= round_cap:
        return base
    bench = round_cap - base.starters
    if bench < 0:
        raise ValueError(
            f"round cap {round_cap} is below the {base.starters} required "
            f"starting slots -- cannot draft a legal roster this season")
    print(f"  round cap binds: {base.rounds} -> {round_cap} rounds "
          f"(bench {base.bench} -> {bench})")
    return dataclasses.replace(base, bench=bench)


def build_season_board(season: int, raw_dir: str = RAW_DIR
                       ) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, list[int], str]:
    """The draft pool for `season`: priced_baseline (historical ADP when
    present, ECR order otherwise -- never padded from HIST_01/AGE_01, a
    player nobody priced isn't in the draft pool), with realised season
    points attached where a production row exists (0 where it doesn't --
    see priced_join_report for why that is usually correct, not a bug)."""
    base, source = priced_baseline(season, raw_dir)
    keys = base["key"].tolist()
    pts, played, weeks = realized_player_weeks(season, keys, raw_dir)
    board = pd.DataFrame({
        "key": keys,
        "name": base["name"].tolist(),
        "position": base["position"].tolist(),
        "adp": base["adp"].to_numpy(dtype=float),
        "realized_points": pts.sum(axis=1),
        "realized_games": played.sum(axis=1),
    })
    return board, pts, played, weeks, source


def _with_valuation(board: pd.DataFrame, points_col: str, league: League) -> pd.DataFrame:
    """Attach vor from `points_col`. vor_p85/vor_p15/risk_index are set equal
    to vor / 0 -- placeholders required by Strategy.choose's column access,
    inert under ceiling_weight=0 and risk_penalty=0 (see the "bpa" preset
    note in run_ceiling): this backtest does not exercise CL-000's
    up_spread/down_spread/downside_weight machinery at all."""
    out = board.copy()
    repl = replacement_levels(out, league, points_col=points_col)
    out["vor"] = out[points_col] - out["position"].map(repl).astype(float)
    out["vor_p85"] = out["vor"]
    out["vor_p15"] = out["vor"]
    out["risk_index"] = 0.0
    return out


def _rank_and_points(starter_pts: dict[int, float], model_slot: int) -> tuple[int, float]:
    ordered = sorted(starter_pts, key=lambda s: -starter_pts[s])
    return ordered.index(model_slot) + 1, starter_pts[model_slot]


def _rng_pair(base_seed: int, season: int, seed_idx: int):
    rng_model = np.random.default_rng([base_seed, season, seed_idx, 1])
    rng_opponents = np.random.default_rng([base_seed, season, seed_idx, 0])
    return rng_model, rng_opponents


NULL_RANK_FLOOR, NULL_RANK_CEIL = 6.0, 7.0   # self-test band, see review note 1


def run_null(seasons=SEASONS, seeds=range(8), base_seed: int = 0,
            league: League = DEFAULT_LEAGUE, raw_dir: str = RAW_DIR) -> pd.DataFrame:
    """Draft straight down the baseline (ECR) board, no model. Every one of
    the 12 teams -- model included -- is an ordinary blinded field member;
    see _null_model_policy. This is the thing CEILING has to beat, and its
    own aggregate stats are the harness self-test (review note 1)."""
    round_cap, _ = compute_round_cap(seasons, TEAMS, raw_dir)
    base_league = _capped_league(league, round_cap)
    rows = []
    for season in seasons:
        board, pts, played, weeks, source = build_season_board(season, raw_dir)
        jr = priced_join_report(season, raw_dir)
        print(f"  {season}: {len(board)} players from {source}, "
              f"{jr['n_matched']}/{jr['n']} ({jr['rate'] * 100:.1f}%) matched "
              f"to realised production")
        board = board.assign(vor=0.0)   # inert placeholder; every archetype is blinded
        positions = board["position"].to_numpy()
        prior = trailing_prior_ppg(season, board["key"].tolist(),
                                   board["position"].tolist(), raw_dir)
        for slot in range(1, TEAMS + 1):
            lg = dataclasses.replace(base_league, slot=slot)
            model_policy = _null_model_policy(lg)
            field_ = _blind_field(lg)
            for seed_idx in seeds:
                rng_model, rng_opp = _rng_pair(base_seed, season, seed_idx)
                rosters = run_backtest_draft(board, lg, model_policy, field_,
                                             rng_model, rng_opp)
                scored = score_season(positions, rosters, pts, played, prior, lg)
                rank, points = _rank_and_points(scored["starter_pts"], slot)
                rows.append(dict(run="NULL", season=season, slot=slot,
                                 seed=seed_idx, rank=rank, starter_pts=points))
    return pd.DataFrame(rows)


def run_ceiling(seasons=SEASONS, seeds=range(8), base_seed: int = 0,
               model_preset: str = "bpa", league: League = DEFAULT_LEAGUE,
               raw_dir: str = RAW_DIR) -> pd.DataFrame:
    """Projections = the season's own realised points: the architecture with
    perfect foresight. Needs no ADP. Opponents stay blind to it (see
    _blind_field) -- only the model team's own valuation uses the future."""
    round_cap, _ = compute_round_cap(seasons, TEAMS, raw_dir)
    base_league = _capped_league(league, round_cap)
    strategy = PRESETS[model_preset]
    rows = []
    for season in seasons:
        board, pts, played, weeks, source = build_season_board(season, raw_dir)
        board = _with_valuation(board, "realized_points", base_league)
        positions = board["position"].to_numpy()
        prior = trailing_prior_ppg(season, board["key"].tolist(),
                                   board["position"].tolist(), raw_dir)
        for slot in range(1, TEAMS + 1):
            lg = dataclasses.replace(base_league, slot=slot)
            field_ = _blind_field(lg)
            for seed_idx in seeds:
                rng_model, rng_opp = _rng_pair(base_seed, season, seed_idx)
                rosters = run_backtest_draft(board, lg, strategy, field_,
                                             rng_model, rng_opp)
                scored = score_season(positions, rosters, pts, played, prior, lg)
                rank, points = _rank_and_points(scored["starter_pts"], slot)
                rows.append(dict(run="CEILING", season=season, slot=slot,
                                 seed=seed_idx, rank=rank, starter_pts=points))
    return pd.DataFrame(rows)


def _summarize(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby(["run", "season"])
    out = g.agg(mean_rank=("rank", "mean"),
               win_rate=("rank", lambda r: (r == 1).mean()),
               mean_starter_pts=("starter_pts", "mean"),
               n=("rank", "size")).reset_index()
    return out


def stage3_report(seasons=SEASONS, seeds=range(8), base_seed: int = 0,
                  model_preset: str = "bpa", raw_dir: str = RAW_DIR) -> None:
    print_run_header(seasons, raw_dir)
    print(f"STAGE 3 -- NULL vs CEILING, {len(list(seeds))} seeds x 12 slots x "
          f"{len(seasons)} seasons = {len(list(seeds)) * TEAMS * len(seasons)} "
          f"drafts each\n")
    print(f"model preset for CEILING: \"{model_preset}\" "
          f"(ceiling_weight={PRESETS[model_preset].ceiling_weight}, "
          f"risk_penalty={PRESETS[model_preset].risk_penalty}, "
          f"downside_weight={PRESETS[model_preset].downside_weight})")
    if PRESETS[model_preset].ceiling_weight == 0 and PRESETS[model_preset].risk_penalty == 0:
        print("  ceiling_weight=0 and risk_penalty=0 -> vor_p85, vor_p15, and "
              "downside_weight never engage. This backtest does NOT validate "
              "CL-000's up/down-spread machinery or any ceiling-chasing "
              "preset -- it isolates whether replacement-level VOR beats "
              "rank-order drafting, nothing more.\n")

    null_df = run_null(seasons, seeds, base_seed, raw_dir=raw_dir)
    null_mean_rank = null_df["rank"].mean()
    print(f"NULL self-test: mean rank {null_mean_rank:.2f} of 12 across all "
          f"seasons/slots/seeds (expected ~6.0-7.0 with no informational edge)")
    if not (NULL_RANK_FLOOR <= null_mean_rank <= NULL_RANK_CEIL):
        print(f"\n  !! OUTSIDE the {NULL_RANK_FLOOR}-{NULL_RANK_CEIL} band -- "
              f"treat this as a harness bug, not a finding. Stopping before "
              f"CEILING per review note 1.")
        print(_summarize(null_df).to_string(index=False))
        return
    print("  within band -- harness validated, proceeding to CEILING.\n")

    ceiling_df = run_ceiling(seasons, seeds, base_seed, model_preset, raw_dir=raw_dir)
    both = pd.concat([null_df, ceiling_df], ignore_index=True)
    summary = _summarize(both)
    print(summary.to_string(index=False))

    agg = both.groupby("run").agg(mean_rank=("rank", "mean"),
                                  win_rate=("rank", lambda r: (r == 1).mean()),
                                  mean_starter_pts=("starter_pts", "mean")).reset_index()
    print("\naggregate, all seasons pooled:")
    print(agg.to_string(index=False))

    null_rank = agg.loc[agg["run"] == "NULL", "mean_rank"].iloc[0]
    ceil_rank = agg.loc[agg["run"] == "CEILING", "mean_rank"].iloc[0]
    null_pts = agg.loc[agg["run"] == "NULL", "mean_starter_pts"].iloc[0]
    ceil_pts = agg.loc[agg["run"] == "CEILING", "mean_starter_pts"].iloc[0]
    print(f"\nCEILING - NULL: rank {ceil_rank - null_rank:+.2f} "
          f"(negative = CEILING finishes higher), "
          f"starter points {ceil_pts - null_pts:+.1f}")
    print("This gap is the number that decides whether the architecture is "
          "worth continuing: it is the most VOR-based drafting could possibly "
          "win, given perfect projections.")


if __name__ == "__main__":
    stage1_report()
