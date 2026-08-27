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

---

## Open

- `proj_spread` itself is the wrong estimator. Cross-source agreement measures
  how similar three feeds are, not how predictable an outcome is. Replace with
  realised year-over-year outcome dispersion from `HIST_01`, or with
  FantasyPros expert dispersion (`ecr_sd`) now that
  `HIST_05_FP_ECR_PRESEASON_2021_2025.csv` is on disk.
- No entry may move a real player's number until the backtest exists.
