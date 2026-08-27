# Test Log

Every measurement taken, every diagnostic run, and what each one changed.

Ordered by category, not by date. The recurring lesson is at the bottom and it
is worth reading first: **most of these tests were run twice, because the first
version measured something other than what it claimed to.**

---

## 1. Hypotheses

### H1 — the aging cliff. CONFIRMED. Acted on (CL-003, pending backtest).
5,582 player-seasons, 2012–2025. Measured as median % of each player's **own**
career peak, which controls for talent — comparing raw production by age would
have measured survivorship instead.

    age    RB    TE    WR
    27   73.8  72.3  79.8
    28   56.6  64.9  72.8    <- -17.2 in one year, vs -7.0 for WR
    29   59.1  66.2  69.8

Caveat kept in the code: past 31 the curve turns upward, which is survivorship,
not recovery. Backs who fell off are no longer in the sample.

### H2 — the separation gap. REJECTED. Not implemented.
*Claim: a receiver who gets open but isn't targeted is a situation problem a QB
change fixes.*

- **v1 result: −0.25 correlation.** Discarded — it was measuring role. Every
  name in "open but not targeted" was a TE or slot receiver; every name in
  "targeted anyway" was an outside X.
- Two data defects found while rebuilding: NGS week-0 season aggregates were
  being mixed with weekly rows, and games were counted from NGS weekly rows
  (which only exist above a target threshold), inflating targets/game 3x —
  Tyler Lockett appeared at 18.3 per game.
- **v2 result:** residualised separation and targets against position, target
  depth and cushion. 1,221 player-seasons. Partial correlation with next
  season's target growth, holding current volume fixed: **+0.05**. Among
  receivers whose team actually changed quarterbacks — the only cut where the
  mechanism could be true — **−0.007**.
- Salvage attempt (is unearned volume more *fragile*?) also failed: collapse
  rate 29% vs 18% at n≈99, and the QB-change split inverts.

Consequence: "he's getting open, he just needs a better quarterback" is no
longer an admissible justification for moving a projection.

### H3 — do tight ends recover from ACLs better? UNANSWERABLE. Not implemented.
- There is no "ACL" anywhere in 30,939 injury reports — the league publishes
  body parts, not diagnoses. Proxy used: season-ending knee injury.
- **v1 result: TEs recover to 121% of prior production.** Discarded — ratio
  noise. Four of seven returning TEs had baselines under 3.3 ppg; Tyler Kroft
  going 3.2 → 6.9 scores as "214% recovered."
- **v2, restricted to startable players (6+ ppg): three tight ends, two
  returned.** Ertz 64%, Taysom Hill 27%. No answer exists in 14 seasons.

Two findings survived, neither about tight ends:
- **Backs always come back, diminished** — 10/10 returned, at 67% of prior ppg.
- **Receivers are binary** — 55% return at all, at ~97% if they do.

### Rookie volatility. MEASURED, corrected downward.
Naive CV ratio said rookie RBs are **1.51x** more volatile week to week. But
absolute standard deviation is *lower* (0.811 ratio) while the mean collapses
(0.506) — the ratio was inflated by its denominator. Paired within-player:
**1.135**. Season-level uncertainty genuinely is ~3x higher (0.292 vs 0.095).

Consequence: rookie upside is *which season you get*, not which week. Apply
~1.10 weekly, not 1.51.

---

## 2. Model logic defects found

| defect | symptom | fix |
|---|---|---|
| Market curve fit on raw points | every QB showed as a **+136** bargain | fit on VOR — points aren't comparable across positions |
| Negative VOR distorting the curve | TE mean alpha **+40** vs WR **−12.7** | `vor_surplus = vor.clip(lower=0)` — below-replacement value is zero, not negative. Result: QB +2.9, RB +1.6, TE +9.2, WR −4.5 |
| **CL-000: risk and upside were the same number** | `p85` and `p15` both built from `proj_spread`, while the drafter blends toward `p85` — so flagging a player as risky made the model want him **more** | split into `up_spread` / `down_spread`, add `vor_p15` and `downside_weight` |
| `p15_points` computed, never read | the model calculated a floor and discarded it; `risk_penalty` only docked for availability | wired through `downside_weight` |
| `max_ceiling` preset had `risk_penalty=-0.2` | rewarded injury risk | set to 0.0 |
| `n_sims` capped at 200 | would have blocked the 5,000-sim run needed to settle the aggression question | cap removed |

---

## 3. Data integrity — diagnostics run in terminal

| check | result | consequence |
|---|---|---|
| Slug collisions across feeds | `james-cook-iii-rb` vs `james-cook-rb`, `a-j-brown-wr` vs `aj-brown-wr` | wrote `norm_id()`; fabricated ADP in top 100 went to 0 |
| PPR ADP join | **0 / 304** | FFC ships its own IDs (`ffc-5672-10-ppr`) matching nothing. Added name-derived fallback → **210 / 304** |
| `grep -c "ADP join is failing" build_pool.py` | returned **0** | proved a stale local copy was running, not the patched file |
| `adp_is_estimated` present in output? | **absent** | computed then dropped by `return out[REQUIRED_OUT]`. The isotonic curve had been fitting on ~100 players holding a fabricated ADP |
| `check_pool.py` fabricated-ADP audit | reported **0/100**, a pass | false — `top.get(col, default)` returns zeros for a missing column. A check that could not fail |
| Bye-week join | **312 / 313** | `SCHEDULE_01` had never been wired in |
| Unused source files | `SCHEDULE_01`, `MARKET_04`, `PROJ_02` | all three joined; extra projections matched 107/114 |
| ECR ↔ production join | 85–90% raw, **94.4% inside top 50** | misses are suffix spellings plus genuine zero-production seasons (Dobbins' 2021 ACL). "Robby/Robbie Anderson" unresolved |
| Historical ADP, all 5 files | 157–249 rows, all `teams == 12`, all windows on draft weekend, no dupes, no null ADP | round cap = 157 // 12 = **13 rounds** |

---

## 4. Measurements that became model inputs

### QB streaming premium → CL-002
Replacement was QB11's season total, which assumes one static quarterback all
year. Measured what streaming is actually worth — hold two from the QB11–20
range, start the better one, 2021–2025:

    static QB11  17.0   |   hold one  16.2   |   hold two, start better  19.1

**+2.1 pts/game, ~+36 per season** — and that is an upper bound, since QB11–20
is chosen with end-of-season hindsight. First attempt was buggy: the "best of
two" lambda took the max across all ten, making it identical to perfect
foresight. Fixed by averaging over all 45 pairs. Effect: Josh Allen's alpha
+27.7 → roughly **+2 to +8**.

### RB age vs projection confidence → CL-003
    median proj_spread, RB 28+ : 0.051
    median proj_spread, RB <28 : 0.063

The model is **more** confident about old backs than young ones. Sources agree
most about veterans because they have the longest track records, placing peak
agreement exactly where cliff risk is highest.

### League size changes the positional edge
    10-team:  RB replacement 172.9  TE 132.1  |  Bowers alpha +42.8  RB mean alpha +1.6
    12-team:  RB replacement 154.7  TE 126.8  |  Bowers alpha +37.1  RB mean alpha +4.4

Not "tight ends are worth less in 12-team leagues." Every replacement level
drops when twelve teams dig deeper into every pool, so *every* player's VOR
rises — Bowers' VOR goes **up**, 72.9 -> 78.2.

What falls is his **alpha**, 42.8 -> 37.1, because alpha is relative. RB
replacement drops 18.2 against TE's 5.3, since real production still sits at
RB25-30 while the TE curve went flat around TE4. Backs gain three times as much
value, the market curve at Bowers' price rises past him, and he stops looking
cheap. He didn't get worse; his competition got better. (TE *mean* alpha
actually rises slightly, 9.2 -> 10.0 — it is the elite TEs specifically that
lose bargain status.)

**In a 12-team league tight ends are worth more and priced more fairly. In a
10-team league they are worth slightly less and priced more wrongly.** The
mispricing is what you draft on, so the elite-TE edge is largest in exactly the
league where Sunday's draft happens — and the backtest, which runs 12-team, is
measuring it at its weakest.

---

## 5. External data verified before use

| claim | how tested | result |
|---|---|---|
| FFC has 10-team historical ADP | fetched `/adp/half-ppr/10-team/all/2019` | returns **12-team data** — Barkley 1.3, Kamara 2.7 identical to the 12-team URL |
| Maybe the JSON API honours `teams` | requested 2022 at both sizes | both report `teams: 12`; differ only in the cosmetic `adp_formatted` field. **10-team historical ADP does not exist** |
| FantasyPros archive is usable | downloaded and scanned 1.53M rows | **PPR only** — no half-PPR or standard board exists. Five preseason August snapshots, 2021–2025 |
| Fourth projection source available | ChatGPT swept free sources | only WalterFootball, too narrow. **Abandoned deliberately** — and CL-003 shows cross-source agreement is the wrong estimator anyway |

---

## 6. Agent output verified rather than trusted

Four times an agent reported work it had not done. Each was caught by checking
rather than reading.

| report | reality |
|---|---|
| Codex: historical ADP collected, changelog updated | CSVs contained a header row and no data |
| ChatGPT: junk files deleted | **eleven** still in Drive, each exactly 152 bytes — one named a single underscore away from a real file |
| Claude Code: "H3 → asymmetric spread; H1 measured but no clean signal" | H3 produced no model input; H1 was **confirmed**. Reconstructed from file timestamps with no transcript — coherent, confident, false |
| Claude Code: spread mechanism landed | true, and verified independently: `p85` still matches the old formula, Bowers 42.8, Gibbs 155.5 |

Consequence: the Change Ledger is now a file in the repo (`docs/CHANGE_LEDGER.md`),
because an agent that cannot read the reasoning will invent it.

---

## 7. Decisions this testing produced

- **Calibrate by draft slot, not buy-in.** Money doesn't change the board.
- **Backtest before deploy.** Shipping to friends first gets feedback on the UI
  of something that might be wrong.
- **Backtest in 12-team PPR** — the only configuration where historical ADP and
  expert rankings both exist. Covers two of the four real leagues.
- **Drop 2021 from the REAL run.** No prior-season ECR to fit the rank→points
  curve from. Four honestly-built seasons beat five where one differs.
- **Use the `bpa` preset in the backtest.** Isolates "does VOR beat rank order"
  from risk parameters that were tuned against the synthetic simulator and
  never tested.
- **Opponents never see the model's board**, even in the perfect-foresight run —
  otherwise the field gets smarter alongside the model and the edge is
  understated.
- **Nothing moves a real player's number until the backtest exists.**
  An unvalidated correction is worse than none.

---

## The recurring lesson

Three hypotheses, three data-integrity audits, and one streaming measurement all
produced a confident wrong answer on the first pass:

- Rookie volatility **1.51x** → really **1.135x** (ratio inflated by its denominator)
- Separation gap **−0.25** → really **+0.05** (measuring role, not opportunity)
- TE knee recovery **121%** → really unanswerable (ratio noise on tiny baselines)
- Streaming premium **+9.3/gm** → really **+2.1** (lambda took the max of all ten)
- Fabricated-ADP audit **0/100, pass** → the column did not exist
- H1 aging curve **rises after 31** → survivorship, not recovery

In every case the naive measurement was contaminated by something structural —
a denominator, a role, a survivor set, a missing column — and the controlled
version reversed or dissolved the finding.

**A validation that cannot fail is not a validation.** Any result that arrives
without a row count, a sample size, or a stated control is unverified.
