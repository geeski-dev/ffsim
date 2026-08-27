#!/usr/bin/env python3
"""Test the hypotheses that came out of Grant's player takes.

    python test_hypotheses.py --inspect     # show schemas of the new history files
    python test_hypotheses.py               # run both tests

H1  The aging-RB cliff. Do running backs decline with age faster than other
    positions, and is there a threshold? 14 seasons of player-weeks makes this
    a measurement rather than a folk belief.

H2  The separation gap. A receiver who gets open but doesn't get targeted is a
    situation problem a QB change can fix. One who can't get open is declining.
    TPRR alone conflates the two; separation splits them apart.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

pd.set_option("display.width", 200)

ALIASES = {
    "name":       ["source_player_name", "player_display_name", "player_name",
                   "full_name", "name", "player"],
    "season":     ["season", "year"],
    "week":       ["week"],
    "position":   ["source_position", "position", "pos", "position_group"],
    "birthdate":  ["birth_date", "birthdate", "dob", "date_of_birth"],
    "targets":    ["targets", "tgt", "receiving_targets"],
    "receptions": ["receptions", "rec", "catches"],
    "rec_yds":    ["receiving_yards", "rec_yds", "rec_yards"],
    "rec_td":     ["receiving_tds", "rec_td", "receiving_td"],
    "rush_yds":   ["rushing_yards", "rush_yds"],
    "rush_td":    ["rushing_tds", "rush_td"],
    "carries":    ["carries", "rushing_attempts", "rush_att", "attempts"],
    "separation": ["avg_separation", "average_separation", "separation"],
    "cushion":    ["avg_cushion", "average_cushion", "cushion"],
    "stat_type":  ["stat_type", "type", "metric_type"],
}


def col(df: pd.DataFrame, canon: str):
    low = {c.lower().strip(): c for c in df.columns}
    for cand in ALIASES.get(canon, [canon]):
        if cand in low:
            return low[cand]
    return None


def load(stem: str, directory: str = "data/raw"):
    hits = [h for h in glob.glob(os.path.join(directory, "**", f"*{stem}*.csv"),
                                 recursive=True)
            if "_SOURCES" not in h.upper() and "_GAPS" not in h.upper()]
    if not hits:
        return None
    return pd.read_csv(sorted(hits, key=len)[0], low_memory=False)


SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def key(df: pd.DataFrame) -> pd.Series:
    """Join on the source-published name, never on a provider's own ID.

    Every feed invents its own identifier -- nflverse uses gsis ids like
    00-0034796, FFC uses integers, our pool uses slugs. The player's name is
    the only thing all of them agree on.
    """
    import re
    n, p = col(df, "name"), col(df, "position")
    if n is None:
        raise KeyError(f"no name column; have {list(df.columns)[:8]}")
    def one(nm, ps):
        w = [t for t in re.sub(r"[^a-z ]", "", str(nm).lower()).split()
             if t not in SUFFIXES]
        return "-".join(w) + ("-" + str(ps).strip().lower() if ps else "")
    if p is not None:
        return pd.Series([one(a, b) for a, b in zip(df[n], df[p])], index=df.index)
    return pd.Series([one(a, None) for a in df[n]], index=df.index)


def hr(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def inspect(directory):
    for stem in ["AGE_01", "HIST_01", "HIST_02", "HIST_04", "SCHEDULE_01",
                 "MARKET_04", "PROJ_02"]:
        df = load(stem, directory)
        if df is None:
            print(f"{stem}: NOT FOUND\n")
            continue
        print(f"{stem}  ({len(df):,} rows)")
        print("  " + ", ".join(df.columns) + "\n")


# ────────────────────────────────────────────────────────────────────────
def h1_aging(directory):
    hr("H1 — THE AGING CLIFF  (does RB decline faster, and where?)")
    bio, prod = load("AGE_01", directory), load("HIST_01", directory)
    if bio is None or prod is None:
        print("  missing AGE_01 or HIST_01"); return

    bd, pos_c = col(bio, "birthdate"), col(bio, "position")
    if bd is None:
        print("  no birthdate column in AGE_01"); return
    bio = bio.assign(k=key(bio), bd=pd.to_datetime(bio[bd], errors="coerce"),
                     pos=bio[pos_c] if pos_c else np.nan)
    bio = bio.dropna(subset=["bd"]).drop_duplicates("k")[["k", "bd", "pos"]]

    s_c = col(prod, "season")
    parts = {c: col(prod, c) for c in
             ["receptions", "rec_yds", "rec_td", "rush_yds", "rush_td"]}
    parts = {k: v for k, v in parts.items() if v}
    if not s_c or len(parts) < 3:
        print("  HIST_01 missing season or component columns"); return

    prod = prod.assign(k=key(prod))
    pts = np.zeros(len(prod))
    for name, c in parts.items():
        w = {"receptions": 0.5, "rec_yds": 0.1, "rec_td": 6.0,
             "rush_yds": 0.1, "rush_td": 6.0}[name]
        pts += prod[c].fillna(0).to_numpy(dtype=float) * w
    prod = prod.assign(half_ppr=pts)

    ssn = (prod.groupby(["k", s_c])
               .agg(pts=("half_ppr", "sum"), games=("half_ppr", "size"))
               .reset_index())
    ssn = ssn[ssn["games"] >= 6]
    ssn = ssn.merge(bio, on="k", how="inner")
    ssn["age"] = ssn[s_c] - ssn["bd"].dt.year
    ssn["ppg"] = ssn["pts"] / ssn["games"]
    ssn = ssn[(ssn["age"].between(21, 35)) & ssn["pos"].isin(["RB", "WR", "TE", "QB"])]

    print(f"  {len(ssn):,} player-seasons, {ssn[s_c].min()}–{ssn[s_c].max()}\n")

    # relative to each player's own peak — controls for talent entirely
    ssn["peak"] = ssn.groupby("k")["ppg"].transform("max")
    ssn["pct_of_peak"] = ssn["ppg"] / ssn["peak"].replace(0, np.nan)

    tbl = (ssn.pivot_table(index="age", columns="pos", values="pct_of_peak",
                           aggfunc="median") * 100).round(1)
    print("  MEDIAN % OF OWN CAREER PEAK, BY AGE")
    print("  (each player compared against himself — talent controlled for)\n")
    print(tbl.to_string())

    print("\n  YEAR-OVER-YEAR CHANGE IN THAT FIGURE (negative = decline)")
    print(tbl.diff().round(1).to_string())

    print("\n  Read the RB column for the first sustained negative run.")
    print("  If RB turns down earlier or harder than WR/TE, the folk belief holds.")


# ────────────────────────────────────────────────────────────────────────
def h2_separation(directory):
    """Superseded. The version that lived here measured role, not opportunity.

    It compared raw separation against raw targets, so the "open but not
    targeted" column filled with tight ends and slot receivers -- players who
    are open by route design -- and the "targeted anyway" column filled with
    outside X receivers running into press. The -0.25 it reported was the
    composition of those two groups, not a signal.

    test_h2_separation.py rebuilds it with position, target depth and cushion
    controlled, then asks whether the leftover openness forecasts next
    season's targets once current volume is held fixed. It does not.
    """
    hr("H2 — SUPERSEDED")
    print("  run:  python test_h2_separation.py")
    print("  (role-controlled, with a forward-looking test the old one lacked)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="data/raw")
    ap.add_argument("--inspect", action="store_true")
    a = ap.parse_args()
    if a.inspect:
        inspect(a.dir)
        sys.exit()
    h1_aging(a.dir)
    h2_separation(a.dir)
