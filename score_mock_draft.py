#!/usr/bin/env python3
"""Score next-pick availability predictions against an ordered mock draft log."""
from __future__ import annotations

import argparse
import csv
import math
import re
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

import ffsim as ff
from build_pool import norm_id, slug_from_name


POOL_FILES = {
    "half_ppr": Path("data/players_half_ppr.csv"),
    "ppr": Path("data/players_ppr.csv"),
    "standard": Path("data/players_half_ppr.csv"),
}

SCORING = {
    "half_ppr": ff.Scoring.half_ppr,
    "ppr": ff.Scoring.ppr,
    "standard": ff.Scoring.standard,
}

BUCKETS = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0)]


def clean_name_key(name: str) -> str:
    cleaned = re.sub(r"[^a-z ]", "", name.lower()).strip()
    return norm_id("-".join(cleaned.split()))


def parse_log(path: Path) -> list[tuple[int | None, str]]:
    picks: list[tuple[int | None, str]] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            row = next(csv.reader([line]))
            pick_number: int | None = None
            name = ""
            if len(row) >= 2 and row[0].strip().isdigit():
                pick_number = int(row[0].strip())
                name = ",".join(row[1:]).strip()
            else:
                match = re.match(r"^\s*(\d+)\s*[,.)\-:]\s*(.+?)\s*$", line)
                if match:
                    pick_number = int(match.group(1))
                    name = match.group(2).strip()
                else:
                    name = line
            if not name:
                raise ValueError(f"{path}:{line_no}: empty player name")
            picks.append((pick_number, name))
    return picks


def build_name_index(board: pd.DataFrame) -> dict[str, dict[str, list[str]]]:
    by_exact: dict[str, list[str]] = defaultdict(list)
    by_name_pos: dict[str, list[str]] = defaultdict(list)
    by_name: dict[str, list[str]] = defaultdict(list)

    for row in board[["player_id", "name", "position"]].itertuples(index=False):
        player_id = str(row.player_id)
        by_exact[norm_id(player_id)].append(player_id)
        keyed = slug_from_name(row.name, row.position)
        by_name_pos[keyed].append(player_id)
        by_name[clean_name_key(str(row.name))].append(player_id)

    return {"exact": by_exact, "name_pos": by_name_pos, "name": by_name}


def unique_or_none(matches: list[str]) -> str | None:
    uniq = sorted(set(matches))
    return uniq[0] if len(uniq) == 1 else None


def match_name(name: str, board: pd.DataFrame, index: dict[str, dict[str, list[str]]]) -> str | None:
    exact = unique_or_none(index["exact"].get(norm_id(name), []))
    if exact is not None:
        return exact

    candidates: list[str] = []
    for pos in sorted(board["position"].dropna().unique()):
        candidates.extend(index["name_pos"].get(slug_from_name(name, pos), []))
    found = unique_or_none(candidates)
    if found is not None:
        return found

    return unique_or_none(index["name"].get(clean_name_key(name), []))


def load_board(teams: int, slot: int, scoring: str) -> tuple[ff.League, pd.DataFrame]:
    league = ff.League(teams=teams, slot=slot, scoring=SCORING[scoring]())
    pool = ff.load_csv(str(POOL_FILES[scoring]))
    board = ff.build_board(pool, league)
    return league, board


def score_log(log_path: Path, teams: int, slot: int, scoring: str, top_n: int = 15) -> dict[str, object]:
    league, board = load_board(teams, slot, scoring)
    raw_picks = parse_log(log_path)
    index = build_name_index(board)

    pick_to_player: dict[int, str] = {}
    unmatched: list[tuple[int, str]] = []
    for sequential_pick, (explicit_pick, name) in enumerate(raw_picks, start=1):
        pick_number = explicit_pick if explicit_pick is not None else sequential_pick
        player_id = match_name(name, board, index)
        if player_id is None:
            unmatched.append((pick_number, name))
            continue
        pick_to_player[pick_number] = player_id

    picked_at = {player_id: pick for pick, player_id in pick_to_player.items()}
    user_picks = league.pick_numbers()
    records: list[dict[str, object]] = []
    gone: set[str] = set()
    max_pick = max(pick_to_player) if pick_to_player else 0

    for pick in range(1, max_pick + 1):
        if pick in user_picks:
            next_pick = next((p for p in user_picks if p > pick), None)
            if next_pick is not None:
                available = board[~board["player_id"].isin(gone)].copy()
                available["availability"] = ff.availability(available, next_pick)
                ranked = available.sort_values("vor", ascending=False).head(top_n)
                for row in ranked.itertuples():
                    survived = row.player_id not in picked_at or picked_at[row.player_id] >= next_pick
                    records.append({
                        "pick": pick,
                        "next_pick": next_pick,
                        "player_id": row.player_id,
                        "player": row.name,
                        "position": row.position,
                        "prob_available": float(row.availability),
                        "survived": bool(survived),
                    })
        selected = pick_to_player.get(pick)
        if selected is not None:
            gone.add(selected)

    predictions = pd.DataFrame(records)
    return {
        "league": league,
        "board": board,
        "predictions": predictions,
        "unmatched": unmatched,
    }


def calibration_table(predictions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for lo, hi in BUCKETS:
        if hi == 1.0:
            mask = (predictions["prob_available"] >= lo) & (predictions["prob_available"] <= hi)
        else:
            mask = (predictions["prob_available"] >= lo) & (predictions["prob_available"] < hi)
        bucket = predictions.loc[mask]
        rows.append({
            "bucket": f"{lo:.1f}-{hi:.1f}",
            "n": len(bucket),
            "avg_pred": bucket["prob_available"].mean() if len(bucket) else math.nan,
            "actual_survival": bucket["survived"].mean() if len(bucket) else math.nan,
        })
    return pd.DataFrame(rows)


def print_report(result: dict[str, object]) -> None:
    predictions = result["predictions"]
    unmatched = result["unmatched"]
    if not isinstance(predictions, pd.DataFrame):
        raise TypeError("predictions must be a DataFrame")

    print("Mock draft availability score")
    print(result["league"].describe())
    print()
    print(f"Predictions scored: {len(predictions)}")
    print(f"Unmatched picks: {len(unmatched)}")
    for pick, name in unmatched[:25]:
        print(f"  pick {pick}: {name}")
    if len(unmatched) > 25:
        print(f"  ... {len(unmatched) - 25} more")

    if predictions.empty:
        print("\nNo predictions to score.")
        return

    calib = calibration_table(predictions)
    print("\nCalibration")
    print(calib.to_string(index=False, formatters={
        "avg_pred": lambda x: "" if pd.isna(x) else f"{x:.3f}",
        "actual_survival": lambda x: "" if pd.isna(x) else f"{x:.3f}",
    }))

    prob = predictions["prob_available"].to_numpy()
    actual = predictions["survived"].astype(float).to_numpy()
    brier = float(np.mean((prob - actual) ** 2))
    can_wait = predictions[predictions["prob_available"] >= 0.5]
    take_now = predictions[predictions["prob_available"] < 0.5]
    can_wait_acc = can_wait["survived"].mean() if len(can_wait) else math.nan
    take_now_acc = (~take_now["survived"]).mean() if len(take_now) else math.nan

    print()
    print(f"Brier score: {brier:.4f}")
    print(f"Can-wait accuracy (P >= 0.5 and survived): {can_wait_acc:.3f} ({len(can_wait)} cases)")
    print(f"Take-now accuracy (P < 0.5 and gone): {take_now_acc:.3f} ({len(take_now)} cases)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path, help="Ordered mock draft log.")
    parser.add_argument("--slot", required=True, type=int, help="Your draft slot, 1-indexed.")
    parser.add_argument("--teams", required=True, type=int, help="Number of teams.")
    parser.add_argument(
        "--scoring",
        required=True,
        choices=sorted(POOL_FILES),
        help="Scoring format; standard reuses the half-PPR market pool.",
    )
    parser.add_argument("--top", default=15, type=int, help="How many top available board players to score.")
    args = parser.parse_args()

    result = score_log(args.log, args.teams, args.slot, args.scoring, top_n=args.top)
    print_report(result)


if __name__ == "__main__":
    main()
