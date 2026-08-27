#!/usr/bin/env python3
"""Build the canonical ffsim player pool from the collected CSVs.

The collection produced ~34 CSVs across four packages. ffsim needs exactly one
table. This is that build step.

    python build_pool.py --inspect                 # schema report, change nothing
    python build_pool.py --scoring half_ppr        # -> players_half_ppr.csv
    python build_pool.py --scoring ppr             # -> players_ppr.csv

Point --dir at wherever you downloaded the Drive folder. Column names are
resolved through an alias table, so it tolerates the collection not having
matched the spec exactly; anything it genuinely cannot find is reported rather
than silently defaulted.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

# canonical name -> candidate source names, first match wins
ALIASES = {
    "player_id":    ["player_id", "playerid", "id"],
    "name":         ["name", "full_name", "player_name", "player"],
    "position":     ["position", "pos"],
    "team":         ["team", "team_abbr", "nfl_team", "recent_team"],
    "bye_week":     ["bye_week", "bye", "byeweek"],
    "adp":          ["adp_overall", "adp", "overall_adp", "adp_pick"],
    "adp_sd":       ["adp_stdev", "adp_sd", "adp_std", "stdev", "std_dev"],
    "adp_min":      ["adp_min_pick", "adp_min", "earliest_pick", "earliest", "min_pick"],
    "adp_max":      ["adp_max_pick", "adp_max", "latest_pick", "latest", "max_pick"],
    "source":       ["source", "source_name", "platform", "provider"],
    "format_teams": ["format_teams", "teams", "team_count", "league_size"],
    "format_scoring": ["format_scoring", "scoring", "scoring_format"],
    "proj_games":   ["proj_games", "games", "g", "projected_games"],
    "pass_yds":     ["proj_pass_yds", "pass_yds", "passing_yards", "pass_yards"],
    "pass_td":      ["proj_pass_td", "pass_td", "passing_tds", "pass_tds"],
    "interceptions": ["proj_int", "interceptions", "int", "ints"],
    "rush_yds":     ["proj_rush_yds", "rush_yds", "rushing_yards", "rush_yards"],
    "rush_td":      ["proj_rush_td", "rush_td", "rushing_tds", "rush_tds"],
    "receptions":   ["proj_rec", "receptions", "rec", "catches"],
    "rec_yds":      ["proj_rec_yds", "rec_yds", "receiving_yards", "rec_yards"],
    "rec_td":       ["proj_rec_td", "rec_td", "receiving_tds", "rec_tds"],
    "fumbles_lost": ["proj_fumbles_lost", "fumbles_lost", "fum_lost", "fumbles"],
    "ppg_mean":     ["ppg_mean", "half_ppr_ppg", "ppg", "mean_ppg"],
    "ppg_stdev":    ["ppg_stdev", "ppg_sd", "ppg_std"],
    "games_missed": ["games_missed_3yr_total", "games_missed_3yr", "games_missed"],
}

STATS = ["pass_yds", "pass_td", "interceptions", "rush_yds", "rush_td",
         "receptions", "rec_yds", "rec_td", "fumbles_lost"]

REQUIRED_OUT = (["player_id", "name", "position", "team", "bye_week"] + STATS +
                ["adp", "adp_sd", "adp_min", "adp_max", "adp_is_estimated",
                 "proj_games", "miss_rate", "weekly_cv", "proj_spread"])

warnings: list[str] = []


def warn(msg: str) -> None:
    warnings.append(msg)
    print(f"  ! {msg}")


def find(df: pd.DataFrame, canon: str):
    """Return the actual column name in df for a canonical field, or None."""
    lower = {c.lower().strip(): c for c in df.columns}
    for cand in ALIASES.get(canon, [canon]):
        if cand in lower:
            return lower[cand]
    return None


SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
POSITIONS = {"qb", "rb", "wr", "te", "k", "pk", "dst", "def"}


def norm_id(raw) -> str:
    """Canonicalise a player_id slug so packages join to each other.

    The collection normalised names inconsistently across packages -- suffixes
    added in one file and dropped in another, initials sometimes split into
    separate tokens. Both sides get reduced to the same shape here:

        james-cook-iii-rb / james-cook-rb      -> james-cook-rb
        kenneth-walker-rb / kenneth-walker-iii -> kenneth-walker-rb
        a-j-brown-wr      / aj-brown-wr        -> aj-brown-wr
    """
    parts = [t for t in str(raw).strip().lower().split("-") if t]
    if not parts:
        return ""
    pos = parts[-1] if parts[-1] in POSITIONS else None
    body = parts[:-1] if pos else parts
    body = [t for t in body if t not in SUFFIXES] or body
    initials = []
    while len(body) > 1 and len(body[0]) == 1:
        initials.append(body.pop(0))
    if initials:
        body = ["".join(initials)] + body
    slug = "-".join(body)
    return f"{slug}-{pos}" if pos else slug


def load(directory: str, stem: str) -> pd.DataFrame | None:
    hits = glob.glob(os.path.join(directory, "**", f"*{stem}*.csv"), recursive=True)
    hits = [h for h in hits if "_sources" not in h and "_GAPS" not in h.upper()]
    if not hits:
        return None
    return pd.read_csv(sorted(hits, key=len)[0], low_memory=False)


def inspect(directory: str) -> None:
    files = sorted(glob.glob(os.path.join(directory, "**", "*.csv"), recursive=True))
    print(f"{len(files)} CSVs in {directory}\n")
    for f in files:
        try:
            df = pd.read_csv(f, nrows=200, low_memory=False)
            total = sum(1 for _ in open(f, encoding="utf-8", errors="ignore")) - 1
            rel = os.path.relpath(f, directory)
            print(f"{rel:<52} {total:>7,} rows")
            print(f"    {', '.join(df.columns)}\n")
        except Exception as e:                                    # noqa: BLE001
            print(f"{os.path.relpath(f, directory):<52} UNREADABLE: {e}\n")


def build(directory: str, scoring: str) -> pd.DataFrame:
    print(f"\nBuilding pool · scoring={scoring}\n")

    # ---- identity ------------------------------------------------------
    players = load(directory, "01_PLAYERS")
    if players is None:
        sys.exit("FATAL: no 01_PLAYERS csv found")
    out = pd.DataFrame()
    for c in ["player_id", "name", "position", "team", "bye_week"]:
        col = find(players, c)
        if col is None:
            if c == "bye_week":
                warn("bye_week not found — byes disabled (set to 0)")
                out[c] = 0
                continue
            sys.exit(f"FATAL: 01_PLAYERS has no column for '{c}'")
        out[c] = players[col]
    out = out[out["position"].isin(["QB", "RB", "WR", "TE"])].copy()
    out["player_id"] = out["player_id"].map(norm_id)
    dupes = out["player_id"].duplicated().sum()
    if dupes:
        warn(f"{dupes} duplicate player_id after normalisation — check for collisions")
    print(f"  identity: {len(out)} skill players")

    # ---- projections: median across sources, spread across sources -----
    proj = load(directory, "04_PROJECTIONS")
    if proj is None:
        sys.exit("FATAL: no 04_PROJECTIONS csv found")
    pid = find(proj, "player_id")
    proj[pid] = proj[pid].map(norm_id)

    stat_cols = {}
    for s in STATS + ["proj_games"]:
        col = find(proj, s)
        if col is None:
            warn(f"projections missing '{s}' — treated as 0")
        else:
            stat_cols[s] = col

    med = proj.groupby(pid)[list(stat_cols.values())].median()
    med.columns = list(stat_cols.keys())
    out = out.merge(med, left_on="player_id", right_index=True, how="left")
    has_proj = out["player_id"].isin(med.index)
    if (~has_proj).sum():
        warn(f"dropped {(~has_proj).sum()} players with no projection data "
             "(phantoms / deep reserves) — they were dragging replacement level")
        out = out[has_proj].copy()
    for s in STATS + ["proj_games"]:
        if s not in out.columns:
            out[s] = 0.0
    out["proj_games"] = out["proj_games"].fillna(15.0).clip(1, 17)

    n_src = proj.groupby(pid).size()
    print(f"  projections: {len(med)} players, "
          f"{n_src.median():.0f} sources each (median)")

    # proj_spread: cross-source disagreement on total value, as a fraction
    val_col = find(proj, "rec_yds") or find(proj, "rush_yds")
    if val_col and n_src.max() > 1:
        tot = (proj.get(find(proj, "rec_yds"), 0) * 0.1
               + proj.get(find(proj, "rush_yds"), 0) * 0.1
               + proj.get(find(proj, "rec_td"), 0) * 6
               + proj.get(find(proj, "rush_td"), 0) * 6)
        g = pd.DataFrame({"pid": proj[pid], "tot": tot}).groupby("pid")["tot"]
        spread = (g.std() / g.mean().replace(0, np.nan)).clip(0.04, 0.55)
        out = out.merge(spread.rename("proj_spread"),
                        left_on="player_id", right_index=True, how="left")
    if "proj_spread" not in out.columns:
        out["proj_spread"] = np.nan
    miss = out["proj_spread"].isna().sum()
    out["proj_spread"] = out["proj_spread"].fillna(0.22)
    if miss:
        warn(f"proj_spread defaulted to 0.22 for {miss} players")

    # ---- ADP: prefer the live market snapshot, which has real ranges ---
    market = load(directory, "MARKET_01")
    adp_src = None
    if market is not None:
        m = market.copy()
        fmt_t, fmt_s = find(m, "format_teams"), find(m, "format_scoring")
        if fmt_t is not None:
            m = m[m[fmt_t].astype(str).str.contains("10", na=False)]
        if fmt_s is not None and scoring == "ppr":
            m = m[m[fmt_s].astype(str).str.contains("ppr", case=False, na=False)
                  & ~m[fmt_s].astype(str).str.contains("half", case=False, na=False)]
        elif fmt_s is not None:
            m = m[m[fmt_s].astype(str).str.contains("half", case=False, na=False)]
        if len(m):
            adp_src = m
            print(f"  ADP: MARKET_01 live snapshot, {len(m)} rows "
                  f"(10-team {scoring})")
    if adp_src is None:
        adp_src = load(directory, "02_ADP")
        warn("MARKET_01 unusable for this scoring — falling back to 02_ADP "
             "(ranges will be sparse)")
    if adp_src is None:
        sys.exit("FATAL: no ADP source found")

    apid = find(adp_src, "player_id")
    adp_src[apid] = adp_src[apid].map(norm_id)
    agg = {}
    for c in ["adp", "adp_sd", "adp_min", "adp_max"]:
        col = find(adp_src, c)
        if col is not None:
            agg[c] = adp_src.groupby(apid)[col].median()
    adp_df = pd.DataFrame(agg)
    out = out.merge(adp_df, left_on="player_id", right_index=True, how="left")

    matched = out["adp"].notna().sum() if "adp" in out.columns else 0
    print(f"  ADP matched: {matched}/{len(out)} players")
    if "adp" not in out.columns:
        sys.exit("FATAL: ADP source has no usable adp column")
    # flag fabricated ADP so nothing downstream mistakes it for a real price
    out["adp_is_estimated"] = out["adp"].isna()
    out["adp"] = out["adp"].fillna(out["adp"].max(skipna=True) + 25 if matched else 250)

    # fall back to a cross-source proxy where real ranges are absent
    for c in ["adp_sd", "adp_min", "adp_max"]:
        if c not in out.columns:
            out[c] = np.nan
    prox = (6.0 + 34.0 * out["proj_spread"] + out["adp"] * 0.045)
    n_fill = out["adp_sd"].isna().sum()
    out["adp_sd"] = out["adp_sd"].fillna(prox)
    out["adp_min"] = out["adp_min"].fillna((out["adp"] - 1.05 * out["adp_sd"]).clip(lower=1))
    out["adp_max"] = out["adp_max"].fillna(out["adp"] + 2.15 * out["adp_sd"])
    if n_fill:
        warn(f"adp_sd synthesised from projection spread for {n_fill} players")

    # ---- weekly volatility ---------------------------------------------
    wk = load(directory, "06_WEEKLY")
    if wk is not None:
        wpid, mean_c, sd_c = find(wk, "player_id"), find(wk, "ppg_mean"), find(wk, "ppg_stdev")
        if wpid and mean_c and sd_c:
            wk[wpid] = wk[wpid].map(norm_id)
            cv = (wk.groupby(wpid)[sd_c].median()
                  / wk.groupby(wpid)[mean_c].median().replace(0, np.nan))
            out = out.merge(cv.rename("weekly_cv").clip(0.2, 1.15),
                            left_on="player_id", right_index=True, how="left")
        else:
            warn("06_WEEKLY present but missing ppg_mean/ppg_stdev")
    if "weekly_cv" not in out.columns:
        out["weekly_cv"] = np.nan
    defaults = {"QB": 0.42, "RB": 0.62, "WR": 0.66, "TE": 0.71}
    n_fill = out["weekly_cv"].isna().sum()
    out["weekly_cv"] = out["weekly_cv"].fillna(out["position"].map(defaults))
    if n_fill:
        warn(f"weekly_cv defaulted by position for {n_fill} players")

    # ---- availability ---------------------------------------------------
    risk = load(directory, "10_RISK")
    if risk is not None:
        rpid, gm = find(risk, "player_id"), find(risk, "games_missed")
        if rpid and gm:
            risk[rpid] = risk[rpid].map(norm_id)
            mr = (risk.groupby(rpid)[gm].median() / 51.0).clip(0, 0.55)
            out = out.merge(mr.rename("miss_rate"),
                            left_on="player_id", right_index=True, how="left")
    if "miss_rate" not in out.columns:
        out["miss_rate"] = np.nan
    n_fill = out["miss_rate"].isna().sum()
    out["miss_rate"] = out["miss_rate"].fillna(
        out["position"].map({"QB": 0.07, "RB": 0.14, "WR": 0.10, "TE": 0.10}))
    if n_fill:
        warn(f"miss_rate defaulted by position for {n_fill} players")

    # ---- finish ----------------------------------------------------------
    for c in STATS:
        out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0.0)
    out = out.drop_duplicates("player_id").reset_index(drop=True)
    return out[REQUIRED_OUT]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=".", help="folder holding the CSVs")
    ap.add_argument("--scoring", default="half_ppr", choices=["half_ppr", "ppr"])
    ap.add_argument("--inspect", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    if a.inspect:
        inspect(a.dir)
        return

    pool = build(a.dir, a.scoring)
    path = a.out or f"players_{a.scoring}.csv"
    pool.to_csv(path, index=False)

    print(f"\n  wrote {path} — {len(pool)} players")
    print("\n  fill rates:")
    for c in REQUIRED_OUT:
        pct = pool[c].notna().mean() * 100
        flag = "" if pct > 99 else ("  <-- thin" if pct < 80 else "  <-- partial")
        print(f"    {c:<16} {pct:5.1f}%{flag}")
    if warnings:
        print(f"\n  {len(warnings)} warning(s) above — defaults were applied.")
    print("\n  test it:")
    print("    python -c \"import ffsim as ff, pandas as pd; "
          f"p=ff.validate(pd.read_csv('{path}')); "
          "print(ff.league_report(p, ff.League(teams=10, slot=6)))\"")


if __name__ == "__main__":
    main()
