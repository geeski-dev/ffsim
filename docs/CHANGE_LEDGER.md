# Change Ledger

The system of record for every adjustment made to the model, and for every
hypothesis tested against it.

Adjustments are made to named **terms** — `down_spread`, `replacement["QB"]`,
`miss_rate` — never to `proj_points` directly. A projection is the output of a
causal chain (`Targets = TeamPlays x PassRate x TargetShare`); moving the output
without naming which term moved is an opinion wearing a number's clothes.

Every entry states: the term, the size of the move, the evidence, and what
observation would prove it wrong. An entry with no falsifier is not an entry.

---

## Hypotheses tested

| id | claim | verdict | acted on |
|----|-------|---------|----------|
| H1 | Running backs decline with age faster than other positions, with a threshold | **CONFIRMED** | pending — CL-003 |
| H2 | A receiver who gets open but isn't targeted is a situation problem a QB change fixes | **REJECTED** | no — correctly not implemented |
| H3 | Tight ends recover from major knee injuries better than running backs | **UNANSWERABLE** | no |

### H1 — the aging cliff. CONFIRMED.
5,582 player-seasons, 2012-2025, measured as median % of a player's *own*
career peak so talent is controlled for. Running backs fall off a cliff at 28:

    age    RB    TE    WR
    27   73.8  72.3  79.8
    28   56.6  64.9  72.8      <- -17.2 in one year, against -7.0 for WR
    29   59.1  66.2  69.8
    30   65.1  62.0  63.7

Past 31 the curve is survivorship — backs who fell off are no longer in the
sample — so it must not be read as recovery. This is the sole evidential basis
for CL-003.

### H2 — the separation gap. REJECTED.
The original -0.25 correlation was measuring role, not opportunity: every name
in "open but not targeted" was a tight end or slot receiver, every name in
"targeted despite not getting open" an outside X. Rebuilt with position,
target depth and cushion residualised out, across 1,221 qualifying
player-seasons. Openness beyond role predicts next season's target growth at a
partial correlation of **+0.05** once current volume is held fixed, and at
**-0.01** among receivers whose team actually changed quarterbacks — the only
cut where the mechanism could be true. Not implemented, and "he's getting open,
he just needs a better quarterback" is not an admissible justification.
See `test_h2_separation.py`.

### H3 — knee-injury recovery by position. UNANSWERABLE.
The league publishes body parts, not diagnoses: there is no "ACL" anywhere in
30,939 injury reports, only "Knee". Proxy used was a season-ending knee injury.
Among players who were startable beforehand (6+ ppg), the sample is **three
tight ends, two of whom returned** (Ertz 64%, Hill 27%). No answer exists in
14 seasons of data. The first cut appeared to show TEs recovering to 121% of
prior production; that was ratio noise from four sub-3.3-ppg players.

Two findings did survive, and neither concerns tight ends:
- Running backs return almost always (10/10) but diminished — 67% of prior ppg.
- Receivers are binary: 55% return at all, but ~97% of prior production if they do.

**H3 produced no input to any model term.** It is unrelated to the
`up_spread`/`down_spread` mechanism, which came from the symmetric-spread bug
below. See `test_h3_knee_recovery.py`.

---

## Entries

### CL-000 — BUG: risk and upside were the same number. LANDED, verified.
Not an adjustment; a defect. `p85` and `p15` were both built from
`proj_spread`, symmetrically, while `draft.py` blends toward `vor_p85` as
`ceiling_weight` rises. Flagging a player as risky therefore made the model
want him **more** — backwards, on precisely the max-ceiling strategy this
system exists to run. `p15_points` was computed and never read by anything.

Fixed by splitting `up_spread` / `down_spread` through `pool.py`,
`valuation.py` (new `vor_p15`) and `draft.py` (new `downside_weight`, and a
`ceiling_guarded` preset at 0.35). Both default to `proj_spread`, so the board
is unchanged: verified `p85 == proj x (1 + 1.036 x proj_spread)`, Bowers alpha
42.8, Gibbs VOR 155.5 — identical to pre-change.

### CL-001 — McCaffrey's downside uncertainty. SUPERSEDED by CL-003.
Kept for the reasoning. Age 30, two years past the H1 cliff, yet holding the
*narrowest* `proj_spread` on the board at 0.04. The mean needs no correction —
projection sources already age-adjust — and `miss_rate` 0.24 already carries the
injury history. What was wrong was the confidence.

### CL-002 — QB replacement level. READY TO APPLY.
**Term:** `replacement["QB"]`. A league-structure term, so it moves every
quarterback at once rather than singling one out.
**Move:** 292.5 -> ~313-318.
**Evidence:** replacement is currently QB11's season total, which assumes a
single static quarterback all year. Holding two from the QB11-20 range and
starting the better one is worth **+2.1 pts/game**, ~+36 over a season,
measured 2021-2025 and averaged over all 45 pairs so no hindsight about which
two were held. Discounted to +20-25 because the QB11-20 set is itself chosen
with end-of-season hindsight.
**Effect:** Allen's alpha +27.7 -> roughly +2 to +8. Still positive; the elite-QB
edge is real, just a quarter the size the board claims.
**Falsified if:** the streamable pool is thinner in-season than history implies.

### CL-003 — Ageing backs: agreement is not confidence. BLOCKED -> now unblocked.
**Term:** `down_spread` for RB, scaling with age. `up_spread` unchanged.
**Evidence — H1, not H3.** The model is *more* certain about old backs than
young ones: median `proj_spread` for RBs 28+ is **0.051**, for RBs under 28
**0.063**. Backwards, and systematically so — projection sources agree most
about veterans because they have the longest track records, which places peak
agreement exactly where cliff risk is highest.

The three largest positive alphas among 28+ backs sit in the narrowest band on
the board: McCaffrey (30) +14.2 at 0.04, Jacobs (28) +14.0 at 0.04, Barkley
(29) +12.4 at 0.06.

This is a rule, not three patches: **for running backs 28 and older,
cross-source agreement is anti-correlated with true uncertainty.** Implement as
an age-scaled floor on `down_spread`, not hand-entered per-player values.
**Blocked by:** CL-000 — now landed and verified, so this is ready.
**Falsified if:** 28+ backs as a cohort hit their projections at the same rate
as under-28 backs. Testable directly once historical ADP lands.

### CL-004 — `swing_picks` should relax `ev_cap`, not double `ceiling_weight`. READY.
**Term:** `ev_cap`, at the picks named in `swing_picks`.
**The defect:** `swing_picks` currently doubles `ceiling_weight` at named picks.
At Extreme variance `ceiling_weight` is already 1.0, so doubling-then-capping
is a mathematical no-op — the parameter does nothing at exactly the setting it
exists for. Found by Claude while wiring the Variance knob, flagged rather than
silently patched.
**The fix is a redesign, not a patch.** A swing pick does not mean "chase more
ceiling" — it means **"accept a worse median for a shot at upside,"** and that
is `ev_cap`'s job. `ev_cap` governs how far below the best available median you
may reach; relaxing it at named picks is exactly the intended behaviour.
**Falsified if:** relaxing `ev_cap` at swing picks produces no change in the
drafted roster.

---

## OPEN PROBLEM — we have no projectable indicator of a high ceiling

**This is the deepest open problem in the system and it must not be quietly
dropped.** The entire ceiling-seeking strategy — the Variance knob,
`ceiling_weight`, `vor_p85`, the case for aggression — rests on being able to
identify which players have high upside *before* the season. We currently
cannot.

### What has been tested, and failed

Every candidate measures some kind of uncertainty. Each is scored on whether it
predicts a player's realised ceiling (best game, P90) the following season,
**controlling for how good the player is** — because without that control every
measure is just re-measuring quality.

| candidate | source | persists yr/yr | predicts next ceiling, controlling for level |
|---|---|---|---|
| `weekly_cv` — in-season variance | HIST_01, n=1,743 | 0.362 | **+0.082** |
| `top3_share` — concentration | HIST_01, n=1,743 | 0.317 | **+0.062** |
| skew `(mean−median)/mean` | HIST_01, n=1,743 | 0.178 | not tested — doesn't persist |
| spike rate, `% weeks > 1.5× own mean` | HIST_01, n=1,743 | 0.129 | not tested — noise |
| `ecr_sd` — expert disagreement | HIST_05, n=608 | — | **+0.124** |

For scale: **level itself predicts next season's best game at +0.49 to +0.52.**

Three independent measures, three different data sources, three different kinds
of uncertainty — all collapse to roughly +0.1 once level is controlled for.

### Two traps this search keeps falling into

1. **Raw correlations are negative.** `weekly_cv` correlates −0.274 with next
   season's best game. That is not "variance hurts upside" — high CV mostly
   means a low mean, and low-mean players have low ceilings. The denominator
   trap, again.
2. **`top3_share` and `weekly_cv` correlate at 0.857.** Measures that look
   conceptually different are often the same number wearing a different name.
   Check redundancy before adding a second one.

### The uncomfortable implication

**The best available predictor of a player's ceiling is how good he is.** If
that is the whole truth, then `vor_p85` adds nothing over `vor`, the Variance
knob is largely cosmetic, and "chase upside" reduces to "draft better players".

That may be the answer. It is not yet established, because one path remains
untested.

### What has NOT been tested

- **`proj_spread` (cross-source projection disagreement)** — the quantity
  `vor_p85` is actually built from. Untestable historically: no archived
  projections exist. The closest analogue (`ecr_sd`) scored +0.124.
- **Situation-based upside** — vacated volume, role change, a QB upgrade, an
  injury ahead of a player on the depth chart. This is the most promising
  remaining direction precisely because it is *not* a variance measure. It asks
  "what could change" rather than "how much has he bounced around."
  `08_VACATED_VOLUME.csv` and `CONTEXT_01_TEAM_CHANGES_2026` exist and neither
  has been used.
- **Age and breakout-window effects** — whether upside concentrates in specific
  career years.

### Consequences while it stays open

- The Variance knob's tooltip must describe what it does **mechanically**
  ("shifts your valuation from a player's median outcome toward his high one")
  and must not imply that chasing ceiling is established to win.
- No entry may claim to identify upside until something clears the level
  control by a meaningful margin.
- **Do not re-propose "use skew instead of variance."** It was tested on
  1,743 player-seasons and it does not persist. Re-run the table above before
  proposing any new uncertainty measure.

---

## Open

- `proj_spread` itself is the wrong estimator. Cross-source agreement measures
  how similar three feeds are, not how predictable an outcome is. Replace with
  realised year-over-year outcome dispersion from `HIST_01`, or with
  FantasyPros expert dispersion (`ecr_sd`) now that
  `HIST_05_FP_ECR_PRESEASON_2021_2025.csv` is on disk.
- No entry may move a real player's number until the backtest exists.
