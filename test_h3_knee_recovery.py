#!/usr/bin/env python3
"""H3 — do tight ends come back from major knee injuries better than backs?

Grant's question, prompted by Tucker Kraft: a torn ACL is catastrophic for a
player whose game is acceleration, but a tight end wins with size, hands and
leverage. Does the position change the recovery?

MEASUREMENT PROBLEM. The weekly injury reports never say "ACL" -- the league
publishes body parts, not diagnoses, so "Knee" covers everything from a bruise
to a reconstruction. The proxy used here is a SEASON-ENDING knee injury: the
player was reported Out with a knee, played no further games that season, and
had played at least four before it. That catches torn ACLs and it also catches
patellar tendons and grade-3 MCLs, so read every number below as "major knee
injury", never as "ACL".

SURVIVORSHIP. The most important outcome is the player who never appears again.
Dropping him would measure "recovery among those who recovered", which is how
this question usually gets answered wrong. He is counted here as a separate,
reported rate rather than silently excluded.
"""
from __future__ import annotations
import glob
import numpy as np
import pandas as pd

pd.set_option("display.width", 200)
HALF_PPR = dict(rec=0.5, rec_yds=0.1, rec_td=6.0, rush_yds=0.1, rush_td=6.0)


def hr(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def load():
    inj = pd.read_csv("data/raw/HIST_03_WEEKLY_INJURY_REPORTS_2009_2025.csv",
                      low_memory=False)
    prod = pd.read_csv(sorted(glob.glob("data/raw/**/*HIST_01*.csv",
                                        recursive=True), key=len)[0],
                       low_memory=False)
    prod = prod[prod["season_type"].astype(str).str.upper().eq("REG")].copy()
    prod["fp"] = sum(prod[c].fillna(0) * w for c, w in HALF_PPR.items())
    return inj, prod


def find_cases(inj, prod):
    """Season-ending knee injuries: Out with a knee, then never plays again
    that season, having already played 4+ games."""
    knee = inj[inj["report_primary_injury"].astype(str).str.contains("knee", case=False, na=False)
               & inj["report_status"].astype(str).str.contains("out", case=False, na=False)]
    played = (prod[prod["fp"].notna()]
              .groupby(["source_player_name", "source_position", "season"])["week"]
              .agg(first_wk="min", last_wk="max", games="size").reset_index())

    cases = []
    for (nm, ssn), g in knee.groupby(["source_player_name", "season"]):
        row = played[(played.source_player_name == nm) & (played.season == ssn)]
        if row.empty:
            continue
        row = row.iloc[0]
        if row.games < 4:
            continue
        first_out = g["week"].min()
        # the knee report must come at or after his last game, and the season
        # must have had real time left in it
        if first_out < row.last_wk or row.last_wk > 14:
            continue
        cases.append(dict(name=nm, pos=row.source_position, season=ssn,
                          games_before=row.games, last_wk=row.last_wk))
    return pd.DataFrame(cases).drop_duplicates(["name", "season"])


def main():
    inj, prod = load()
    hr("H3 — RETURNING FROM A MAJOR KNEE INJURY, BY POSITION")

    cases = find_cases(inj, prod)
    cases = cases[cases["pos"].isin(["RB", "WR", "TE"]) & cases["season"].between(2012, 2024)]
    print(f"  {len(cases)} season-ending knee injuries, 2012–2024")
    print(f"  {cases.pos.value_counts().to_dict()}\n")

    ppg = (prod.groupby(["source_player_name", "season"])
               .agg(pts=("fp", "sum"), g=("fp", "size")).reset_index())
    ppg["ppg"] = ppg["pts"] / ppg["g"]
    look = {(r.source_player_name, r.season): (r.ppg, r.g)
            for r in ppg.itertuples()}

    rows = []
    for c in cases.itertuples():
        before = look.get((c.name, c.season))          # partial year, pre-injury
        prior = look.get((c.name, c.season - 1))
        nxt = look.get((c.name, c.season + 1))
        nxt2 = look.get((c.name, c.season + 2))
        # baseline: the better-evidenced of the partial year and the full prior
        base = None
        if before and prior:
            base = (before[0] * before[1] + prior[0] * prior[1]) / (before[1] + prior[1])
        elif before:
            base = before[0]
        if not base or base <= 0:
            continue
        rows.append(dict(name=c.name, pos=c.pos, season=c.season, base=base,
                         y1=nxt[0] if nxt else np.nan,
                         y1_games=nxt[1] if nxt else 0,
                         y2=nxt2[0] if nxt2 else np.nan,
                         returned=bool(nxt and nxt[1] >= 4)))
    r = pd.DataFrame(rows)
    r["rec_y1"] = r["y1"] / r["base"]
    r["rec_y2"] = r["y2"] / r["base"]

    print("  DID HE COME BACK AT ALL?  (4+ games the following season)\n")
    t = r.groupby("pos").agg(n=("returned", "size"),
                             returned=("returned", "sum"))
    t["return_rate"] = (t["returned"] / t["n"] * 100).round(1)
    print(t.to_string())
    print("\n  This is the number that gets left out. A position can look great")
    print("  at recovering simply because its failures stopped being players.\n")

    back = r[r["returned"]]
    print("\n  AMONG THOSE WHO RETURNED — % of pre-injury points per game\n")
    t2 = back.groupby("pos").agg(
        n=("rec_y1", "size"),
        yr1_median=("rec_y1", "median"), yr1_mean=("rec_y1", "mean"),
        yr2_median=("rec_y2", "median"))
    print((t2.assign(**{c: (t2[c] * 100).round(1) for c in t2.columns if c != "n"})
             ).to_string())

    print("\n\n  UNCONDITIONAL — every case, non-returners counted as zero\n")
    r["uncond"] = np.where(r["returned"], r["rec_y1"], 0.0)
    t3 = r.groupby("pos").agg(n=("uncond", "size"), median=("uncond", "median"),
                              mean=("uncond", "mean"))
    print((t3.assign(median=(t3["median"] * 100).round(1),
                     mean=(t3["mean"] * 100).round(1))).to_string())
    print("\n  This is the number to draft on: it prices the chance he is finished")
    print("  together with how good he is if he isn't.\n")

    # ---- the contamination check ---------------------------------------
    hr("SAME QUESTION, FANTASY-RELEVANT PLAYERS ONLY")
    print("  The table above is driven by ratio noise. Tyler Kroft went from 3.2")
    print("  points a game to 6.9 and scores as 214% 'recovered'; four of the")
    print("  seven returning tight ends had baselines under 3.3 ppg. Dividing by")
    print("  a tiny denominator manufactures recovery. Restrict to players who")
    print("  were actually startable before the injury (6+ ppg) and re-ask.\n")
    rel = r[r["base"] >= 6.0]
    t4 = rel.groupby("pos").agg(n=("returned","size"), returned=("returned","sum"))
    t4["return_rate"] = (t4["returned"]/t4["n"]*100).round(1)
    print(t4.to_string())
    relb = rel[rel["returned"]]
    if len(relb):
        t5 = relb.groupby("pos").agg(n=("rec_y1","size"), yr1_median=("rec_y1","median"),
                                     yr1_mean=("rec_y1","mean"))
        print("\n  among those who returned, % of pre-injury ppg\n")
        print(t5.assign(yr1_median=(t5.yr1_median*100).round(1),
                        yr1_mean=(t5.yr1_mean*100).round(1)).to_string())
        for pos in ["RB","WR","TE"]:
            s2 = relb[relb.pos.eq(pos)]["rec_y1"]
            if len(s2) >= 2:
                se = s2.std(ddof=1)/np.sqrt(len(s2)) if len(s2) > 1 else float("nan")
                print(f"    {pos}: n={len(s2)}, mean {s2.mean()*100:.1f}% ± {se*100:.1f}")
        print("\n  cases:")
        print(relb.sort_values("rec_y1", ascending=False)[
            ["name","pos","season","base","y1","rec_y1"]].round(2).to_string(index=False))

    print("\n  THE CASES (year-1 recovery, sorted)\n")
    show = back.sort_values("rec_y1", ascending=False)[
        ["name", "pos", "season", "base", "y1", "rec_y1"]]
    print(show.head(12).round(2).to_string(index=False))
    print("  ...")
    print(show.tail(8).round(2).to_string(index=False))

    for pos in ["RB", "WR", "TE"]:
        s = back[back.pos.eq(pos)]["rec_y1"]
        if len(s) >= 3:
            se = s.std(ddof=1) / np.sqrt(len(s))
            print(f"\n  {pos}: n={len(s)}, mean {s.mean()*100:.1f}% ± {se*100:.1f} (1 se)")
    print("\n  Overlapping error bars mean the position difference is not")
    print("  established, however tidy the medians look.")


if __name__ == "__main__":
    main()
