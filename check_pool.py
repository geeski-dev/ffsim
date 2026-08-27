#!/usr/bin/env python3
"""Sanity-check the built pool before trusting anything it says.

    python check_pool.py                       # half PPR
    python check_pool.py data/players_ppr.csv  # full PPR
"""
import glob
import sys

import pandas as pd

import ffsim as ff
from build_pool import norm_id

path = sys.argv[1] if len(sys.argv) > 1 else "data/players_half_ppr.csv"
pool = ff.validate(pd.read_csv(path))
lg = ff.League(teams=10, slot=6)
board = ff.build_board(pool, lg)
pd.set_option("display.width", 200)


def hr(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


# ---- 1. did the ADP join actually work, or are we losing real players? ----
hr("1. ADP JOIN — is the 179/313 shortfall K/DST, or broken slugs?")
mk = glob.glob("data/raw/**/MARKET_01*.csv", recursive=True)
if mk:
    m = pd.read_csv(mk[0], low_memory=False)
    m10 = m[m["format_teams"].astype(str).str.contains("10", na=False)]
    ids = set(pool["player_id"].map(norm_id))
    orph = m10[~m10["player_id"].map(norm_id).isin(ids)]
    print(f"  10-team market rows: {len(m10)}   unmatched: {len(orph)}")
    if "source_position" in orph.columns:
        print(f"  by position: {orph['source_position'].value_counts().to_dict()}")
        real = orph[~orph["source_position"].astype(str).str.upper()
                    .isin(["K", "DST", "DEF", "D/ST"])]
        print(f"\n  unmatched SKILL players (these are the problem): {len(real)}")
        if len(real):
            cols = [c for c in ["player_id", "source_player_name",
                                "source_position", "adp_overall"] if c in real.columns]
            print(real.nsmallest(min(20, len(real)), "adp_overall")[cols].to_string(index=False))
else:
    print("  MARKET_01 not found")

# ---- 2. does the board look like real football? --------------------------
hr("2. TOP 24 BY VOR — do these look like sensible 2026 picks?")
cols = ["name", "position", "team", "adp", "vor", "alpha", "tier"]
print(board.nlargest(24, "vor")[cols].round(1).to_string(index=False))

hr("3. TOP 15 BY ALPHA — the players the market underrates")
print(board.nlargest(15, "alpha")[cols].round(1).to_string(index=False))

hr("4. BOTTOM 10 BY ALPHA — the players it overrates")
print(board.nsmallest(10, "alpha")[cols].round(1).to_string(index=False))

# ---- 3. how much of the board is real vs. synthesised? -------------------
hr("5. DATA QUALITY WHERE IT MATTERS — top 100 by VOR")
top = board.nlargest(100, "vor")
synth_adp = int(top.get("adp_is_estimated", top["adp"] * 0).astype(bool).sum())
flat_spread = (top["proj_spread"].round(2) == 0.22).sum()
print(f"  players with a fabricated deep ADP : {synth_adp}/100")
print(f"  players with defaulted proj_spread : {flat_spread}/100")
print("\n  (the second number is the ceiling model's blind spot — those players")
print("   have no cross-source disagreement estimate, so their upside is a guess)")

# ---- 4. positional structure --------------------------------------------
hr("6. LEAGUE REPORT — replacement levels from real data")
print(ff.league_report(pool, lg))

hr("7. ALPHA BY POSITION — should be roughly centred, no position dominating")
print(board.groupby("position")["alpha"].agg(["mean", "max", "count"]).round(1).to_string())
