#!/usr/bin/env python3
"""Acceptance tests for POST /api/next-pick (stage B).

    python test_next_pick.py

Calls api.main.api_next_pick directly (no HTTP layer) against the real
player pools the API actually loads -- same spirit as test_pool_columns.py:
verify against what's actually shipped, not a mock.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "api"))

import main as api_main  # noqa: E402
from models import NextPickRequest  # noqa: E402

FAILURES = 0


def check(label: str, condition: bool) -> None:
    global FAILURES
    status = "PASS" if condition else "FAIL"
    if not condition:
        FAILURES += 1
    print(f"  [{status}] {label}")


def test_next_pick_skips_current_pick_and_only_your_own_slots():
    print("\nnext_pick is the next of MY OWN pick numbers strictly after current_pick")
    req = NextPickRequest(teams=10, slot=6, current_pick=1)
    league = api_main.build_league(req)
    resp = api_main.api_next_pick(req)
    pick_numbers = league.pick_numbers()
    check("next_pick is a member of my own pick_numbers", resp.next_pick in pick_numbers)
    check("next_pick > current_pick", resp.next_pick > req.current_pick)
    check("next_pick is the smallest such pick", resp.next_pick == min(p for p in pick_numbers if p > 1))
    check("picks_away == next_pick - current_pick", resp.picks_away == resp.next_pick - req.current_pick)

    req2 = NextPickRequest(teams=10, slot=6, current_pick=pick_numbers[0])
    resp2 = api_main.api_next_pick(req2)
    check("at my own turn, next_pick skips past THIS pick to the one after",
          resp2.next_pick == pick_numbers[1])


def test_next_pick_none_after_last_pick():
    print("\nnext_pick is None once every one of my own picks is behind current_pick")
    req = NextPickRequest(teams=10, slot=6)
    league = api_main.build_league(req)
    last = league.pick_numbers()[-1]
    req = NextPickRequest(teams=10, slot=6, current_pick=last)
    resp = api_main.api_next_pick(req)
    check("next_pick is None", resp.next_pick is None)
    check("picks_away is None", resp.picks_away is None)
    check("take_now/can_wait still populated (availability defaults to 1.0 -- no next pick to be unavailable for)",
          len(resp.take_now) + len(resp.can_wait) > 0)
    check("with no next pick, nobody is flagged take-now (all treated as available)",
          len(resp.take_now) == 0)


def test_take_now_can_wait_split_at_50_percent():
    print("\ntake_now/can_wait split exactly on the 0.5 availability threshold")
    req = NextPickRequest(teams=10, slot=6, current_pick=1)
    resp = api_main.api_next_pick(req)
    check("every take_now row has availability < 0.5", all(p.availability < 0.5 for p in resp.take_now))
    check("every can_wait row has availability >= 0.5", all(p.availability >= 0.5 for p in resp.can_wait))
    check("at most 15 players total", len(resp.take_now) + len(resp.can_wait) <= 15)
    check("take_now + can_wait non-empty", len(resp.take_now) + len(resp.can_wait) > 0)
    values = [p.our_value for p in resp.take_now] + [p.our_value for p in resp.can_wait]
    check("combined list is sorted by our_value descending (board order)",
          values == sorted(values, reverse=True))


def test_gone_players_excluded():
    print("\ngone players never appear in take_now/can_wait or count toward tier depletion")
    req = NextPickRequest(teams=10, slot=6, current_pick=1)
    resp = req and api_main.api_next_pick(req)
    first_player_id = (resp.take_now + resp.can_wait)[0].player_id

    req2 = NextPickRequest(teams=10, slot=6, current_pick=1, gone=[first_player_id])
    resp2 = api_main.api_next_pick(req2)
    ids2 = {p.player_id for p in resp2.take_now + resp2.can_wait}
    check("previously-top player is gone from the new ranked list", first_player_id not in ids2)


def test_tier_depletion_only_for_needed_positions_and_reflects_gone():
    print("\ntier_depletion only lists positions still needed, and remaining count excludes gone players")
    req = NextPickRequest(teams=10, slot=6, current_pick=1)
    resp = api_main.api_next_pick(req)
    positions_listed = {row.position for row in resp.tier_depletion}
    check("QB (1 required, 0 drafted) shows up as needed", "QB" in positions_listed)
    check("every tier_depletion row has remaining > 0", all(row.remaining > 0 for row in resp.tier_depletion))

    # Fill the single QB slot with a real QB from the board and confirm QB
    # drops out of tier_depletion (no longer "needed").
    league = api_main.build_league(req)
    pool = api_main.POOLS[req.scoring]
    board = api_main.ff.build_board(pool, league)
    a_qb = board.loc[board["position"] == "QB", "player_id"].iloc[0]
    req2 = NextPickRequest(teams=10, slot=6, current_pick=1, mine=[a_qb], gone=[a_qb])
    resp2 = api_main.api_next_pick(req2)
    positions_listed2 = {row.position for row in resp2.tier_depletion}
    check("QB no longer needed once the lineup's 1 QB slot is filled", "QB" not in positions_listed2)

    # Now mark every remaining QB as gone (not mine) -- QB tier depletion
    # must vanish (not needed=False here since we didn't draft one, so it's
    # still needed, but there's nothing left to report on).
    all_qbs = board.loc[board["position"] == "QB", "player_id"].tolist()
    req3 = NextPickRequest(teams=10, slot=6, current_pick=1, gone=all_qbs)
    resp3 = api_main.api_next_pick(req3)
    check("no QB tier_depletion row when every QB is gone (nothing left to report)",
          "QB" not in {row.position for row in resp3.tier_depletion})


def test_target_pick_overrides_the_default_next_pick():
    print("\ntarget_pick lets the caller preview availability at an arbitrary pick, "
          "independent of next_pick -- the hook a future round-chip click will use")
    req_default = NextPickRequest(teams=10, slot=6, current_pick=1)
    resp_default = api_main.api_next_pick(req_default)
    check("with no target_pick, target_pick defaults to next_pick",
          resp_default.target_pick == resp_default.next_pick)

    league = api_main.build_league(req_default)
    my_picks = league.pick_numbers()
    far_future_pick = my_picks[3]  # a later round pick, not my very next one
    req_override = NextPickRequest(teams=10, slot=6, current_pick=1, target_pick=far_future_pick)
    resp_override = api_main.api_next_pick(req_override)
    check("next_pick (the header's own framing) is unaffected by target_pick",
          resp_override.next_pick == resp_default.next_pick)
    check("target_pick echoes back the requested override", resp_override.target_pick == far_future_pick)
    check("picks_away still measures the gap to next_pick, not target_pick",
          resp_override.picks_away == resp_override.next_pick - req_override.current_pick)

    # far_future_pick is a LATER pick than the default next_pick, and
    # availability(df, pick) is monotonically decreasing in pick (more picks
    # have happened, less likely a good player survives) -- so shared
    # players must be no MORE available at the later target, not more.
    by_id_default = {p.player_id: p.availability for p in resp_default.take_now + resp_default.can_wait}
    by_id_override = {p.player_id: p.availability for p in resp_override.take_now + resp_override.can_wait}
    shared = set(by_id_default) & set(by_id_override)
    check("shared players are no more available at the later target pick",
          all(by_id_override[pid] <= by_id_default[pid] + 1e-9 for pid in shared))
    check("at least one player is shared between the two views", len(shared) > 0)


def test_hedge_window_matches_league():
    print("\nhedge_window in the response matches League.hedge_window()")
    req = NextPickRequest(teams=12, slot=1, current_pick=1)
    league = api_main.build_league(req)
    resp = api_main.api_next_pick(req)
    check("hedge_window matches", resp.hedge_window == league.hedge_window())


def test_replacement_and_vor_do_not_move_as_players_leave():
    print("\nOur Value for a fixed player is identical whether or not OTHER players are gone "
          "-- the core modelling requirement: replacement/VOR are season-long facts, not "
          "recomputed from the remaining pool")
    req = NextPickRequest(teams=10, slot=6, current_pick=1)
    league = api_main.build_league(req)
    pool = api_main.POOLS[req.scoring]
    board = api_main.ff.build_board(pool, league)
    strategy = api_main.build_strategy(req, league)
    comp = strategy.value_components(board)
    board = board.assign(our_value=comp["score"])

    # take the 50th-best player by our_value as the fixed reference, and
    # mark the top 30 RBs gone (simulating a run) -- his own our_value must
    # not move even though half the RB pool just vanished.
    ranked = board.sort_values("our_value", ascending=False).reset_index(drop=True)
    reference_id = ranked.loc[49, "player_id"]
    reference_before = ranked.loc[49, "our_value"]
    top_rbs_gone = ranked.loc[ranked["position"] == "RB", "player_id"].head(30).tolist()

    req2 = NextPickRequest(teams=10, slot=6, current_pick=1, gone=top_rbs_gone)
    resp2 = api_main.api_next_pick(req2)
    all_rows2 = {p.player_id: p.our_value for p in (resp2.take_now + resp2.can_wait)}
    # the reference player may not be in the top-15 shown; recompute directly
    # against the same board/strategy the endpoint itself would build
    league2 = api_main.build_league(req2)
    board2 = api_main.ff.build_board(api_main.POOLS[req2.scoring], league2)
    strategy2 = api_main.build_strategy(req2, league2)
    comp2 = strategy2.value_components(board2)
    board2 = board2.assign(our_value=comp2["score"])
    reference_after = board2.loc[board2["player_id"] == reference_id, "our_value"].iloc[0]
    check("reference player's our_value unchanged after a simulated RB run",
          abs(reference_before - reference_after) < 1e-9)
    del all_rows2  # not needed beyond sanity that the endpoint ran


if __name__ == "__main__":
    test_next_pick_skips_current_pick_and_only_your_own_slots()
    test_next_pick_none_after_last_pick()
    test_take_now_can_wait_split_at_50_percent()
    test_gone_players_excluded()
    test_tier_depletion_only_for_needed_positions_and_reflects_gone()
    test_target_pick_overrides_the_default_next_pick()
    test_hedge_window_matches_league()
    test_replacement_and_vor_do_not_move_as_players_leave()
    print()
    if FAILURES:
        print(f"{FAILURES} check(s) FAILED")
        raise SystemExit(1)
    print("all checks passed")
