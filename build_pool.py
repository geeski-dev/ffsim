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
                 "proj_games", "miss_rate", "weekly_cv", "proj_spread",
                 "up_spread", "down_spread"])

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


def slug_from_name(name, pos) -> str:
    """Derive a canonical slug from a source-published name and position.

    Some packages ship their own IDs that were never meant to match ours, so
    the raw name is the only usable key. Strip punctuation, hyphenate, append
    the position, then run it through the same normaliser everything else uses.
    """
    import re
    n = re.sub(r"[^a-z ]", "", str(name).lower()).strip()
    n = "-".join(n.split())
    return norm_id(f"{n}-{str(pos).strip().lower()}")


def load_all(directory: str, stems) -> pd.DataFrame | None:
    """Concatenate every matching file — used where one feed spans several."""
    frames = [f for f in (load(directory, st) for st in stems) if f is not None]
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True, sort=False)


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
    dy = find(players, "draft_year") or ("draft_year" if "draft_year" in players.columns else None)
    for c in ["player_id", "name", "position", "team", "bye_week"]:
        col = find(players, c)
        if col is None:
            if c == "bye_week":
                out[c] = np.nan
                continue
            sys.exit(f"FATAL: 01_PLAYERS has no column for '{c}'")
        out[c] = players[col]
    out["is_rookie"] = (players[dy] == 2026).fillna(False).values if dy else False
    out = out[out["position"].isin(["QB", "RB", "WR", "TE"])].copy()
    out["player_id"] = out["player_id"].map(norm_id)
    dupes = out["player_id"].duplicated().sum()
    if dupes:
        warn(f"{dupes} duplicate player_id after normalisation — check for collisions")
    if out["bye_week"].isna().all():
        byes = load(directory, "SCHEDULE_01")
        bt, bw = (find(byes, "team"), find(byes, "bye_week")) if byes is not None else (None, None)
        if bt and bw:
            mp = dict(zip(byes[bt].astype(str).str.upper(), byes[bw]))
            out["bye_week"] = out["team"].astype(str).str.upper().map(mp)
            n_ok = out["bye_week"].notna().sum()
            print(f"  bye weeks: joined {n_ok}/{len(out)} from SCHEDULE_01")
        else:
            warn("bye_week unavailable — byes disabled (set to 0)")
    out["bye_week"] = out["bye_week"].fillna(0).astype(int)
    print(f"  identity: {len(out)} skill players")

    # ---- projections: median across sources, spread across sources -----
    proj = load(directory, "04_PROJECTIONS")
    if proj is None:
        sys.exit("FATAL: no 04_PROJECTIONS csv found")
    pid = find(proj, "player_id")
    proj[pid] = proj[pid].map(norm_id)

    extra = load(directory, "PROJ_02")
    if extra is not None:
        en, ep = find(extra, "name"), find(extra, "position")
        if en is None and "source_player_name" in extra.columns:
            en = "source_player_name"
        if ep is None and "source_position" in extra.columns:
            ep = "source_position"
        if en and ep:
            extra = extra.copy()
            extra[pid] = [slug_from_name(n, p) for n, p in zip(extra[en], extra[ep])]
            hit = extra[pid].isin(set(proj[pid])).sum()
            print(f"  extra projections: {len(extra)} rows, {hit} match an existing player")
            proj = pd.concat([proj, extra], ignore_index=True, sort=False)
        else:
            warn("PROJ_02 present but has no usable name/position columns")

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
        # fewer than 3 independent sources cannot produce a credible dispersion
        spread = spread.where(n_src >= 3)
        out = out.merge(spread.rename("proj_spread"),
                        left_on="player_id", right_index=True, how="left")
    if "proj_spread" not in out.columns:
        out["proj_spread"] = np.nan
    miss = out["proj_spread"].isna().sum()
    # measured: rookie RBs carry ~3x the cross-source dispersion of veterans
    # (0.292 vs 0.095). 0.22 for veterans is deliberate ignorance, not a
    # measurement -- source agreement is a floor on true uncertainty, since
    # sources can be wrong together.
    rookie_default, vet_default = 0.29, 0.22
    out["proj_spread"] = out["proj_spread"].fillna(
        pd.Series(np.where(out["is_rookie"], rookie_default, vet_default),
                  index=out.index))
    if miss:
        n_rk = int((out["is_rookie"] & out["proj_spread"].eq(rookie_default)).sum())
        warn(f"proj_spread defaulted for {miss} players "
             f"({n_rk} rookies at {rookie_default}, rest at {vet_default})")

    # up_spread/down_spread: distinct upside/downside dispersion. Not yet
    # measured separately -- both default to proj_spread so today's p85/p15/
    # ceiling numbers are reproduced exactly. Age-based downside values are a
    # separate change (Change Ledger CL-003), landed only after this
    # mechanism is verified.
    out["up_spread"] = out["proj_spread"]
    out["down_spread"] = out["proj_spread"]

    # ---- ADP: prefer the live market snapshot, which has real ranges ---
    market = load_all(directory, ["MARKET_01", "MARKET_04"])
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
            srcs = sorted(m[find(m, "source")].dropna().unique()) if find(m, "source") else []
            print(f"  ADP: live market snapshot, {len(m)} rows (10-team {scoring})"
                  + (f" from {', '.join(map(str, srcs))}" if srcs else ""))
    if adp_src is None:
        adp_src = load(directory, "02_ADP")
        warn("no live market rows for this scoring — falling back to 02_ADP "
             "(ranges will be sparse)")
    if adp_src is None:
        sys.exit("FATAL: no ADP source found")

    # Every feed invents its own identifier. FFC ships ids like
    # "ffc-5672-10-ppr" that match nothing we have. The published name is the
    # only field all sources agree on, so build a key both ways and keep
    # whichever one actually lands on the pool.
    adp_src = adp_src.copy()
    known = set(out["player_id"])
    apid = find(adp_src, "player_id")
    by_id = adp_src[apid].map(norm_id) if apid else pd.Series(index=adp_src.index, dtype=object)

    an = ("source_player_name" if "source_player_name" in adp_src.columns
          else find(adp_src, "name"))
    ap = ("source_position" if "source_position" in adp_src.columns
          else find(adp_src, "position"))
    if an and ap:
        by_name = pd.Series([slug_from_name(n, q)
                             for n, q in zip(adp_src[an], adp_src[ap])],
                            index=adp_src.index)
        if by_name.isin(known).sum() > by_id.isin(known).sum():
            by_id = by_name

    adp_src["_key"] = by_id
    agg = {}
    for c in ["adp", "adp_sd", "adp_min", "adp_max"]:
        col = find(adp_src, c)
        if col is not None:
            agg[c] = adp_src.groupby("_key")[col].median()
    adp_df = pd.DataFrame(agg)
    out = out.merge(adp_df, left_on="player_id", right_index=True, how="left")

    matched = out["adp"].notna().sum() if "adp" in out.columns else 0
    print(f"  ADP matched: {matched}/{len(out)} players")
    if matched < len(out) * 0.25:
        warn("ADP join is failing — sample keys from each side")
        print(f"    adp keys : {list(adp_src['_key'].head(5))}")
        print(f"    pool keys: {list(out['player_id'].head(5))}")
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
