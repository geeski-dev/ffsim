"""H2 rebuilt with a within-role control, plus the test that actually matters.

The first version measured a -0.25 correlation between getting open and getting
targeted and called it a finding. It wasn't. Every name in the "open but not
targeted" column was a tight end or a slot receiver, and every name in the
"targeted despite not getting open" column was an outside X. The test was
measuring role, not opportunity: a receiver running nine-yard option routes is
open by construction, a receiver running go routes into press coverage is not.

So: residualise separation against what the role already implies (position,
target depth, and the cushion the defense hands over), residualise targets
against the same, and ask whether the LEFTOVER openness predicts the LEFTOVER
targets. Then -- the part the first version skipped entirely -- check whether
this season's gap predicts next season's change in targets. A cross-sectional
oddity that doesn't forecast anything is not a signal, it's a description.
"""
from __future__ import annotations
import glob
import numpy as np
import pandas as pd

pd.set_option("display.width", 220)


def hr(t):
    print("\n" + "=" * 78 + f"\n{t}\n" + "=" * 78)


def resid(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return y - X @ beta


def load():
    f = sorted(glob.glob("data/raw/**/*HIST_04*.csv", recursive=True), key=len)[0]
    d = pd.read_csv(f, low_memory=False)
    d = d[d["stat_type"].eq("receiving")]

    # NGS publishes week 0 as the season aggregate. Weekly rows are separate;
    # mixing them double-counts every player.
    ssn = d[d["week"] == 0].copy()

    # Games must come from the box score, not from NGS weekly rows -- NGS only
    # publishes a weekly row when the player cleared that week's target
    # threshold, so counting them turns a quiet ten-game season into a
    # three-game one and inflates targets/game by 3x. That artefact put Tyler
    # Lockett at 18 targets a game.
    g = sorted(glob.glob("data/raw/**/*HIST_01*.csv", recursive=True), key=len)[0]
    box = pd.read_csv(g, low_memory=False,
                      usecols=["source_player_name", "season", "season_type",
                               "week", "targets"])
    box = box[box["season_type"].astype(str).str.upper().eq("REG")]
    games = (box[box["targets"].fillna(0) > 0]
             .groupby(["source_player_name", "season"]).size().rename("games"))
    ssn = ssn.merge(games, left_on=["source_player_name", "season"],
                    right_index=True, how="left")
    ssn = ssn.dropna(subset=["games"])
    ssn["games"] = ssn["games"].clip(1, 17)
    ssn["tgt_pg"] = ssn["targets"] / ssn["games"]
    ssn = ssn.dropna(subset=["avg_separation", "avg_intended_air_yards",
                             "avg_cushion", "tgt_pg"])
    return ssn


def design(df: pd.DataFrame, with_cushion: bool) -> np.ndarray:
    a = df["avg_intended_air_yards"].to_numpy(float)
    cols = [np.ones(len(df)),
            df["source_position"].eq("TE").to_numpy(float),
            a, a ** 2]
    if with_cushion:
        cols.append(df["avg_cushion"].to_numpy(float))
    # season fixed effects: league-wide separation drifts with scheme trends
    for s in sorted(df["season"].unique())[1:]:
        cols.append(df["season"].eq(s).to_numpy(float))
    return np.column_stack(cols)


def main():
    ssn = load()
    hr("H2 v2 — THE SEPARATION GAP, WITH ROLE CONTROLLED")
    print(f"  {len(ssn):,} qualifying player-seasons, "
          f"{int(ssn.season.min())}–{int(ssn.season.max())}")
    print(f"  {ssn.source_position.value_counts().to_dict()}")
    print("\n  NGS only publishes receivers with 43+ targets, so the truly")
    print("  ignored tail is missing by construction. Read every number below")
    print("  as 'among receivers who already had a role'.\n")

    # ---- the naive version, for comparison ------------------------------
    raw_r = ssn["avg_separation"].corr(ssn["tgt_pg"])
    print(f"  naive corr(separation, targets/game)          : {raw_r:+.3f}")

    # ---- residualise both sides against role ----------------------------
    ssn["sep_r"] = resid(ssn["avg_separation"].to_numpy(float), design(ssn, True))
    ssn["tgt_r"] = resid(ssn["tgt_pg"].to_numpy(float), design(ssn, False))
    ctl_r = np.corrcoef(ssn["sep_r"], ssn["tgt_r"])[0, 1]
    print(f"  role-controlled corr(sep resid, targets resid): {ctl_r:+.3f}")
    print("\n  If the controlled number is near zero, separation and targets are")
    print("  genuinely independent gates once role is stripped out, and the gap")
    print("  is real information. If it goes strongly positive, the naive")
    print("  negative was pure role composition and there is nothing here.")

    ssn["gap"] = (ssn["sep_r"].rank(pct=True) - ssn["tgt_r"].rank(pct=True)) * 100

    # ---- does the gap forecast anything? --------------------------------
    hr("DOES THE GAP PREDICT NEXT SEASON'S TARGETS?")
    nxt = ssn[["source_player_name", "season", "tgt_pg"]].copy()
    nxt["season"] -= 1
    nxt = nxt.rename(columns={"tgt_pg": "tgt_pg_next"})
    j = ssn.merge(nxt, on=["source_player_name", "season"], how="inner")
    j["d_tgt"] = j["tgt_pg_next"] - j["tgt_pg"]
    print(f"  {len(j):,} player-seasons with a following season\n")

    r_gap = np.corrcoef(j["gap"], j["d_tgt"])[0, 1]
    r_sep = np.corrcoef(j["sep_r"], j["d_tgt"])[0, 1]
    r_base = np.corrcoef(j["tgt_pg"], j["d_tgt"])[0, 1]
    print(f"  corr(gap,            Δ targets/game) : {r_gap:+.3f}")
    print(f"  corr(sep residual,   Δ targets/game) : {r_sep:+.3f}")
    print(f"  corr(this yr tgt/gm, Δ targets/game) : {r_base:+.3f}   "
          "<- mean reversion, the null to beat")

    j["q"] = pd.qcut(j["gap"], 5, labels=["Q1 least open\n  for targets",
                                          "Q2", "Q3", "Q4",
                                          "Q5 most open\n  for targets"])
    t = j.groupby("q", observed=True).agg(
        n=("d_tgt", "size"),
        tgt_pg_now=("tgt_pg", "mean"),
        d_targets=("d_tgt", "mean"),
        pct_gaining=("d_tgt", lambda s: (s > 0).mean() * 100)).round(2)
    print("\n  BY GAP QUINTILE\n")
    print(t.to_string())

    # ---- beat the null ---------------------------------------------------
    hr("DOES OPENNESS ADD ANYTHING BEYOND MEAN REVERSION?")
    print("  The gap is built partly out of MINUS targets, so a positive")
    print("  correlation with next year's target GROWTH is half-guaranteed --")
    print("  low-volume receivers grow because they started low. Q5 above")
    print("  averages 4.0 targets a game and Q1 averages 7.7; that spread alone")
    print("  produces most of the +0.35. The only question worth asking is")
    print("  whether openness survives once volume is held fixed.\n")

    def partial(y, x, z):
        """corr(x, y) after regressing both on z (with an intercept)."""
        Z = np.column_stack([np.ones(len(z)), z])
        return float(np.corrcoef(resid(x, Z), resid(y, Z))[0, 1])

    y = j["d_tgt"].to_numpy(float)
    vol = j["tgt_pg"].to_numpy(float)
    pr_sep = partial(y, j["sep_r"].to_numpy(float), vol)
    pr_gap = partial(y, j["gap"].to_numpy(float), vol)
    print(f"  partial corr(sep residual, Δ targets | volume) : {pr_sep:+.3f}")
    print(f"  partial corr(gap,          Δ targets | volume) : {pr_gap:+.3f}")

    print("\n  Δ TARGETS/GAME BY OPENNESS TERCILE, WITHIN VOLUME TERCILE")
    print("  (rows = how busy he already was, cols = how open for his role)\n")
    j["vol3"] = pd.qcut(j["tgt_pg"], 3, labels=["low vol", "mid vol", "high vol"])
    j["sep3"] = pd.qcut(j["sep_r"], 3, labels=["covered", "average", "open"])
    piv = j.pivot_table(index="vol3", columns="sep3", values="d_tgt",
                        aggfunc="mean", observed=True).round(2)
    cnt = j.pivot_table(index="vol3", columns="sep3", values="d_tgt",
                        aggfunc="size", observed=True)
    print(piv.to_string())
    print("\n  n per cell:")
    print(cnt.to_string())
    print("\n  Read across each row. If 'open' beats 'covered' at the same")
    print("  volume, openness carries information the target count does not.")

    # ---- the mechanism the hypothesis actually named ---------------------
    hr("SPLIT BY WHETHER THE QUARTERBACK ACTUALLY CHANGED")
    print("  The claim was never 'open receivers get more targets eventually'.")
    print("  It was 'an open receiver is a SITUATION problem, and a situation")
    print("  problem resolves when the situation changes'. So the test has to")
    print("  condition on the change. Primary passer = most attempts for that")
    print("  team that season.\n")

    g = sorted(glob.glob("data/raw/**/*HIST_01*.csv", recursive=True), key=len)[0]
    pas = pd.read_csv(g, low_memory=False,
                      usecols=["source_player_name", "source_team", "season",
                               "season_type", "pass_attempts"])
    pas = pas[pas["season_type"].astype(str).str.upper().eq("REG")]
    qb = (pas.groupby(["source_team", "season", "source_player_name"])
             ["pass_attempts"].sum().reset_index()
             .sort_values("pass_attempts", ascending=False)
             .drop_duplicates(["source_team", "season"])
             .rename(columns={"source_player_name": "qb"}))

    k = j.merge(qb[["source_team", "season", "qb"]],
                left_on=["source_team", "season"],
                right_on=["source_team", "season"], how="left")
    nq = qb.copy(); nq["season"] -= 1
    k = k.merge(nq[["source_team", "season", "qb"]].rename(columns={"qb": "qb_next"}),
                on=["source_team", "season"], how="left")
    k = k.dropna(subset=["qb", "qb_next"])
    k["qb_changed"] = k["qb"] != k["qb_next"]
    print(f"  {len(k):,} player-seasons with both quarterbacks identified; "
          f"{int(k.qb_changed.sum())} saw a new primary passer\n")

    for changed, lab in [(False, "SAME quarterback"), (True, "NEW quarterback")]:
        sub = k[k["qb_changed"] == changed]
        if len(sub) < 40:
            continue
        pc = partial(sub["d_tgt"].to_numpy(float),
                     sub["sep_r"].to_numpy(float),
                     sub["tgt_pg"].to_numpy(float))
        sub = sub.copy()
        sub["sep3"] = pd.qcut(sub["sep_r"], 3,
                              labels=["covered", "average", "open"])
        row = sub.groupby("sep3", observed=True)["d_tgt"].mean().round(2)
        n = sub.groupby("sep3", observed=True).size()
        print(f"  {lab}  (n={len(sub)})")
        print(f"    partial corr(openness, Δ targets | volume) : {pc:+.3f}")
        print(f"    mean Δ targets/game  {dict(row)}")
        print(f"    n                    {dict(n)}\n")
    print("  This is the only cut where the hypothesis has a right to be true.")
    print("  If openness pays no better under a new quarterback than under the")
    print("  same one, the mechanism the story rests on is not there.")

    # ---- who it flags right now -----------------------------------------
    hr("2025 — OPEN FOR THEIR ROLE, NOT YET TARGETED FOR IT")
    cur = ssn[ssn["season"] == ssn["season"].max()]
    cols = {"source_player_name": "name", "source_position": "pos",
            "source_team": "team", "avg_separation": "sep",
            "avg_intended_air_yards": "aDOT", "tgt_pg": "tgt/gm",
            "sep_r": "sep+", "tgt_r": "tgt+", "gap": "gap"}
    show = cur.rename(columns=cols)[list(cols.values())]
    print(show.nlargest(15, "gap").round(2).to_string(index=False))
    print("\n  TARGETED WELL BEYOND WHAT THEIR SEPARATION EARNS\n")
    print(show.nsmallest(12, "gap").round(2).to_string(index=False))


if __name__ == "__main__":
    main()
