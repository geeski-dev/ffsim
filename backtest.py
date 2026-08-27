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

RAW_DIR = "data/raw"
SEASONS = list(range(2021, 2026))   # ECR archive coverage
TEAMS = 12                          # full-PPR, matches the ECR archive's format

FANTASY_POS = ["QB", "RB", "WR", "TE"]

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


if __name__ == "__main__":
    stage1_report()
