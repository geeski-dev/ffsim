# Mispricing Engine v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebrand the ffsim web UI to "Mispricing Engine" — switch the backend to real player data, fix two correctness bugs, and rework the player board around a Value/Bargain/Boom-Bust/Draft-Score vocabulary with a dark design system, while keeping everything local (no CORS/deploy changes).

**Architecture:** Backend gains two small correctness fixes (`ffsim/draft.py` one-line, `ffsim/valuation.py` already fixed last session — verify only), switches its player pool from the synthetic generator to the real CSVs built last session (`ffsim.load_csv`, one pool per scoring mode, cached at startup), and adds a `risk_profile` request field that drives a server-computed `draft_score` per player. Frontend gets a full dark-theme CSS token rewrite, branding (logo/favicon/title/tagline), an intro blurb, tooltipped/renamed player-board columns plus two new ones (Boom/Bust, Draft Score), a Risk Profile control that visibly re-sorts the board, updated simulator copy, and mobile table scrolling.

**Tech Stack:** No new dependencies. Native `title` attributes for tooltips (no tooltip library). CSS custom properties for the design system (no CSS-in-JS).

---

## Ground truth established during reconnaissance (do not re-derive)

- **Privacy check (P0 item 1) already passes**: `my_leagues.py` does not exist on disk, is not tracked (`git ls-files | grep my_leagues` → empty), and is not referenced in `web/` or `api/` (`grep -r "my_leagues" web/ api/` → empty). No action needed — just state this in the final report.
- **VOR floor (P0 item 2) is already implemented** from the previous session (commit `5698e32`): `ffsim/valuation.py`'s `add_valuation()` already has `vor_surplus = vor.clip(lower=0.0)` and fits/compares alpha on it. Confirmed still present by `grep -n "vor_surplus" ffsim/valuation.py`. No re-implementation needed — verify with `check_pool.py` and report the current numbers, don't redo the edit.
- **`data/players_half_ppr.csv` and `data/players_ppr.csv` already exist and are up to date** (rebuilt last session with the `adp_is_estimated` column present and correctly written). `ffsim.pool.load_csv(path)` returns `validate(pd.read_csv(path))` — exact signature confirmed in `ffsim/pool.py`.
- **No `data/players_standard.csv` exists**, and `build_pool.py`'s `--scoring` choices are only `half_ppr`/`ppr` — there is no real-data file for the "Standard" scoring option. The plan below reuses the half-PPR pool for `standard` scoring (component stats are scoring-format agnostic; only the ADP/market snapshot differs by format, and half-PPR's ADP is the more neutral of the two available). This is a judgment call filling a real gap in the spec — flag it in the final report.
- **`ffsim.PRESETS` ceiling_weight values** (confirmed in `ffsim/draft.py`): `safe=0.0`, `balanced=0.25`, `ceiling=0.75`, `max_ceiling=1.0`. These map directly to the four Risk Profile options.
- **`board` (the DataFrame from `ff.build_board`) already has `vor_p85` and `weekly_cv` columns** — confirmed present via earlier inspection. No `ffsim/` changes needed to expose them; only `api/main.py`/`api/models.py` need to surface them.
- **`weekly_cv` real-data distribution** (from `data/players_half_ppr.csv`): min 0.20, 33rd pct 0.588, median 0.660, 67th pct 0.710, max 1.15. Boom/Bust buckets use `< 0.55` Steady, `0.55–0.75` Balanced, `> 0.75` Volatile — roughly tercile splits on real data, rounded to clean numbers.
- **Logo and favicon files already exist** at `web/src/assets/logo.png` and `web/public/favicon.png` (placed by the user). `web/public/favicon.svg` was already deleted by the user. Nothing to create, only to wire in.
- **Simulator already has no cap on `n_sims`** (plain `<input type="number" min={1}>`, no `max`) — P0 item 10's "don't cap it" is already satisfied; only the note text needs updating to the new exact wording.
- **The Boom/Bust color spec was cut off mid-message** — no hex value was given for "steady" (cool blue). This plan uses `--steady: #5EC2E8` (a clean cool blue against the given dark palette) as a placeholder value. Flag this explicitly as a gap-fill in the final report, not a design decision made silently.

---

### Task 1: Backend — `ffsim/draft.py` max_ceiling fix (P0 item 4)

**Files:**
- Modify: `ffsim/draft.py:236`

- [ ] **Step 1: Change the one line**

```python
# OLD
    "max_ceiling": Strategy("max_ceiling", ceiling_weight=1.0, risk_penalty=-0.2, ev_cap=0.25),
# NEW
    "max_ceiling": Strategy("max_ceiling", ceiling_weight=1.0, risk_penalty=0.0, ev_cap=0.25),
```

- [ ] **Step 2: Verify**

Run: `cd ~/Code/ffsim && source .venv/bin/activate && python -c "import ffsim as ff; print(ff.PRESETS['max_ceiling'])"`
Expected: `risk_penalty=0.0` in the printed `Strategy(...)`.

Run: `python validate.py` — must still exit 0.

- [ ] **Step 3: Commit**

```bash
git add ffsim/draft.py
git commit -m "Stop rewarding injury risk in the max_ceiling preset

risk_penalty=-0.2 rewarded drafting injury-prone players. Tolerating
risk and seeking it are different things; max_ceiling should still
prefer upside via ceiling_weight=1.0, not risk itself."
```

---

### Task 2: Backend — verify VOR floor still holds (P0 item 2, no code change)

**Files:** none modified — verification only.

- [ ] **Step 1: Confirm the fix is present**

Run: `cd ~/Code/ffsim && grep -n "vor_surplus" ffsim/valuation.py`
Expected: shows `out["vor_surplus"] = out["vor"].clip(lower=0.0)` and its use in the market-curve fit and alpha calc (already committed as `5698e32`).

- [ ] **Step 2: Re-run and record current numbers**

Run: `source .venv/bin/activate && python check_pool.py 2>&1 | sed -n '/^7\./,/^$/p'`
Record the positional alpha means shown (expected close to the last session's result: QB ~+2.9, RB ~+1.7, TE ~+8.8, WR ~-4.4 — small drift is fine since `data/players_half_ppr.csv` hasn't changed, exact match expected).

Note in the final report: this was already fixed last session, not redone here.

---

### Task 3: Backend — real data pools + risk_profile + draft_score + weekly_cv (P0 item 3, P1 items 6/7/8 backend half)

**Files:**
- Modify: `api/main.py`
- Modify: `api/models.py`

- [ ] **Step 1: Add `risk_profile` to the request model and `draft_score`/`weekly_cv` to `PlayerRow` in `api/models.py`**

```python
# In LeagueSettingsRequest, add after reserved_slots:
    reserved_slots: int = 2
    risk_profile: Literal["safe", "balanced", "ceiling", "max_ceiling"] = "balanced"
```

```python
# In PlayerRow, add draft_score and weekly_cv:
class PlayerRow(BaseModel):
    player_id: str
    name: str
    position: str
    team: str
    adp: float
    vor: float
    alpha: Optional[float] = None
    tier: int
    weekly_cv: float
    draft_score: float
```

- [ ] **Step 2: Replace the pool loading and add risk_profile → draft_score wiring in `api/main.py`**

Replace the imports/module-level section:

```python
# OLD
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI, HTTPException

import ffsim as ff
from ffsim.valuation import effective_starters, replacement_levels

from models import (
    LeagueResponse,
    LeagueSettingsRequest,
    PickChip,
    PlayerRow,
    PositionScarcityRow,
    SimulateRequest,
    SimulateResponse,
    StrategyResultRow,
)

app = FastAPI(title="ffsim API")

POOL = ff.make_pool()

SCORING_BUILDERS = {
    "half_ppr": ff.Scoring.half_ppr,
    "ppr": ff.Scoring.ppr,
    "standard": ff.Scoring.standard,
}
```

```python
# NEW
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fastapi import FastAPI, HTTPException

import ffsim as ff
from ffsim.valuation import effective_starters, replacement_levels

from models import (
    LeagueResponse,
    LeagueSettingsRequest,
    PickChip,
    PlayerRow,
    PositionScarcityRow,
    SimulateRequest,
    SimulateResponse,
    StrategyResultRow,
)

app = FastAPI(title="ffsim API")

# Real player pools, one per scoring format with a dedicated ADP/market
# snapshot. There is no "standard" market snapshot (build_pool.py only
# collects half_ppr/ppr), so standard scoring reuses the half_ppr pool --
# component stats are scoring-format agnostic, only the ADP differs, and
# half_ppr's ADP is the more neutral of the two available snapshots.
POOL_FILES = {
    "half_ppr": REPO_ROOT / "data" / "players_half_ppr.csv",
    "ppr": REPO_ROOT / "data" / "players_ppr.csv",
}
POOLS = {key: ff.load_csv(str(path)) for key, path in POOL_FILES.items()}
POOLS["standard"] = POOLS["half_ppr"]

SCORING_BUILDERS = {
    "half_ppr": ff.Scoring.half_ppr,
    "ppr": ff.Scoring.ppr,
    "standard": ff.Scoring.standard,
}
```

- [ ] **Step 3: Update `api_league` to use the per-scoring pool, compute `draft_score`, sort/select by it, and expose `weekly_cv`**

```python
# OLD
@app.post("/api/league", response_model=LeagueResponse)
def api_league(settings: LeagueSettingsRequest) -> LeagueResponse:
    league = build_league(settings)
    board = ff.build_board(POOL, league)
    repl = replacement_levels(board, league)
    starters = effective_starters(board, league)

    scarcity = [
        PositionScarcityRow(
            position=pos,
            effective_starters=starters.get(pos, 0),
            replacement_points=round(repl[pos], 1),
            top_vor=round(float(board.loc[board.position == pos, "vor"].max()), 1),
        )
        for pos in sorted(repl)
    ]

    top = board.sort_values("vor", ascending=False).head(150)
    players = [
        PlayerRow(
            player_id=row.player_id,
            name=row.name,
            position=row.position,
            team=row.team,
            adp=round(row.adp, 1),
            vor=round(row.vor, 1),
            alpha=None if math.isnan(row.alpha) else round(row.alpha, 1),
            tier=int(row.tier),
        )
        for row in top.itertuples()
    ]
```

```python
# NEW
@app.post("/api/league", response_model=LeagueResponse)
def api_league(settings: LeagueSettingsRequest) -> LeagueResponse:
    league = build_league(settings)
    pool = POOLS[settings.scoring]
    board = ff.build_board(pool, league)
    repl = replacement_levels(board, league)
    starters = effective_starters(board, league)

    scarcity = [
        PositionScarcityRow(
            position=pos,
            effective_starters=starters.get(pos, 0),
            replacement_points=round(repl[pos], 1),
            top_vor=round(float(board.loc[board.position == pos, "vor"].max()), 1),
        )
        for pos in sorted(repl)
    ]

    ceiling_weight = ff.PRESETS[settings.risk_profile].ceiling_weight
    board = board.copy()
    board["draft_score"] = (1 - ceiling_weight) * board["vor"] + ceiling_weight * board["vor_p85"]

    top = board.sort_values("draft_score", ascending=False).head(150)
    players = [
        PlayerRow(
            player_id=row.player_id,
            name=row.name,
            position=row.position,
            team=row.team,
            adp=round(row.adp, 1),
            vor=round(row.vor, 1),
            alpha=None if math.isnan(row.alpha) else round(row.alpha, 1),
            tier=int(row.tier),
            weekly_cv=round(row.weekly_cv, 3),
            draft_score=round(row.draft_score, 1),
        )
        for row in top.itertuples()
    ]
```

Note `board = board.copy()` before adding `draft_score` — `build_board` returns a fresh DataFrame each call already, but the explicit copy keeps the mutation local and obvious rather than relying on that.

- [ ] **Step 4: Update `api_simulate` to use the per-scoring pool (it must NOT use `risk_profile` — that field only drives the board, per the spec's explicit warning that a risk control affecting only the simulator "will assume it's broken")**

```python
# OLD
@app.post("/api/simulate", response_model=SimulateResponse)
def api_simulate(req: SimulateRequest) -> SimulateResponse:
    league = build_league(req)
    unknown = [s for s in req.strategies if s not in ff.PRESETS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown strategies: {unknown}")

    summary, _detail = ff.evaluate(POOL, league, req.strategies, n_sims=req.n_sims, seed=0)
```

```python
# NEW
@app.post("/api/simulate", response_model=SimulateResponse)
def api_simulate(req: SimulateRequest) -> SimulateResponse:
    league = build_league(req)
    pool = POOLS[req.scoring]
    unknown = [s for s in req.strategies if s not in ff.PRESETS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown strategies: {unknown}")

    summary, _detail = ff.evaluate(pool, league, req.strategies, n_sims=req.n_sims, seed=0)
```

- [ ] **Step 5: Verify — start the server and check real data + draft_score + weekly_cv are wired**

```bash
cd ~/Code/ffsim && source .venv/bin/activate && uvicorn main:app --app-dir api --port 8000 &
sleep 2
curl -s localhost:8000/api/league -H 'Content-Type: application/json' \
  -d '{"teams":10,"slot":6,"scoring":"half_ppr","bench":6,"lineup":{"QB":1,"RB":2,"WR":2,"TE":1,"FLEX":1},"playoff_teams":4,"reserved_slots":2,"risk_profile":"balanced"}' \
  | python3 -c "
import json, sys
d = json.load(sys.stdin)
print('player count:', len(d['players']))
print('first player:', d['players'][0])
print('is real data (not \"WR05 Synthetic\"):', 'Synthetic' not in d['players'][0]['name'])
"
```
Expected: real player names (e.g. Jahmyr Gibbs / Bijan Robinson-shaped names), not `"WR05 Synthetic"`. `draft_score` and `weekly_cv` present and populated on every player.

Then verify risk_profile changes draft_score ordering:
```bash
curl -s localhost:8000/api/league -H 'Content-Type: application/json' \
  -d '{"teams":10,"slot":6,"scoring":"half_ppr","bench":6,"lineup":{"QB":1,"RB":2,"WR":2,"TE":1,"FLEX":1},"playoff_teams":4,"reserved_slots":2,"risk_profile":"safe"}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print([p['name'] for p in d['players'][:5]])"
curl -s localhost:8000/api/league -H 'Content-Type: application/json' \
  -d '{"teams":10,"slot":6,"scoring":"half_ppr","bench":6,"lineup":{"QB":1,"RB":2,"WR":2,"TE":1,"FLEX":1},"playoff_teams":4,"reserved_slots":2,"risk_profile":"max_ceiling"}' \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print([p['name'] for p in d['players'][:5]])"
```
Expected: the top-5 order differs between `safe` (cw=0.0, pure VOR) and `max_ceiling` (cw=1.0, pure vor_p85) — confirms `risk_profile` actually changes the board.

Kill the server: `lsof -ti :8000 | xargs -r kill`

- [ ] **Step 6: Commit**

```bash
git add api/main.py api/models.py
git commit -m "Switch to real player data and add risk-adjusted draft score

make_pool() (synthetic) is replaced by ffsim.load_csv() against the
real half_ppr/ppr pools built last session, cached at startup.
standard scoring reuses the half_ppr pool -- there is no dedicated
standard-scoring market snapshot.

Adds risk_profile to /api/league (one of ffsim.PRESETS' ceiling_weight
values) which drives a new draft_score = (1-cw)*vor + cw*vor_p85 per
player; the board is now selected and sorted by draft_score by
default. risk_profile deliberately does not touch /api/simulate."
```

---

### Task 4: Frontend — types, branding files, package name (P0 branding, P1 item 6/7/8 types)

**Files:**
- Modify: `web/src/api/types.ts`
- Modify: `web/package.json`
- Modify: `web/index.html`

- [ ] **Step 1: Update `web/src/api/types.ts`**

```typescript
// Add to LeagueSettings, after reserved_slots:
export type RiskProfile = 'safe' | 'balanced' | 'ceiling' | 'max_ceiling';

export interface LeagueSettings {
  teams: number;
  slot: number;
  scoring: ScoringMode;
  bench: number;
  lineup: LineupSettings;
  playoff_teams: number;
  reserved_slots: number;
  risk_profile: RiskProfile;
}
```

```typescript
// Update PlayerRow:
export interface PlayerRow {
  player_id: string;
  name: string;
  position: string;
  team: string;
  adp: number;
  vor: number;
  alpha: number | null;
  tier: number;
  weekly_cv: number;
  draft_score: number;
}
```

- [ ] **Step 2: Update `web/package.json` name**

```json
  "name": "mispricing-engine",
```//is the only line to change (keep everything else — `private`, `version`, `scripts`, `dependencies`, `devDependencies` — exactly as-is).

- [ ] **Step 3: Update `web/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/png" href="/favicon.png" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Mispricing Engine</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 4: Verify**

Run: `cd ~/Code/ffsim/web && npx tsc --noEmit` — expect errors right now, since `SettingsPanel`/`App`/`PlayerBoard` don't yet supply `risk_profile`/`weekly_cv`/`draft_score` — **this is expected at this point in the plan**; Tasks 5-6 fix it. Just confirm the errors are exactly about the new required fields being missing, not something else (e.g. a typo).

- [ ] **Step 5: Commit**

```bash
git add web/src/api/types.ts web/package.json web/index.html
git commit -m "Add risk_profile/draft_score/weekly_cv types; rebrand package/title/favicon"
```

---

### Task 5: Frontend — dark design system (P0 branding CSS, P1 items 6/11/12 styling)

**Files:**
- Modify: `web/src/index.css`
- Modify: `web/src/App.css`

- [ ] **Step 1: Replace `web/src/index.css` entirely**

```css
:root {
  --ground: #0A0C0A;
  --surface: #141815;
  --surface-alt: #1C211D;
  --ink: #E8EDE8;
  --ink-mute: #8A968C;
  --rule: #262C28;
  --primary: #3DD68C;
  --primary-dim: #1F8F5C;
  --tertiary: #E5A94E;
  --bargain-positive: #3DD68C;
  --bargain-negative: #E8654F;
  --steady: #5EC2E8;
}

body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: var(--ground);
  color: var(--ink);
}
```

- [ ] **Step 2: Replace `web/src/App.css` entirely**

```css
.app { max-width: 1400px; margin: 0 auto; padding: 24px; text-align: left; }

.app-header { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
.app-header img { height: 36px; width: 36px; }
.app-header h1 { margin: 0; font-size: 1.5rem; color: var(--ink); }
.tagline { margin: 0 0 20px; color: var(--ink-mute); font-size: 0.95rem; }

.intro { color: var(--ink-mute); font-size: 0.95rem; line-height: 1.5; max-width: 900px; margin: 0 0 24px; }
.intro strong { color: var(--ink); }

.columns { display: flex; gap: 24px; align-items: flex-start; }
.column-left { flex: 0 0 280px; }
.column-right { flex: 1; display: flex; flex-direction: column; gap: 24px; min-width: 0; }

.panel { background: var(--surface); border: 1px solid var(--rule); border-radius: 8px; padding: 16px; color: var(--ink); }
.panel h2 { margin-top: 0; font-size: 1.1rem; color: var(--ink); }

.settings-panel label { display: block; margin-bottom: 12px; font-size: 0.9rem; font-weight: 600; color: var(--ink); }
.settings-panel select, .settings-panel input[type="number"] {
  display: block; width: 100%; margin-top: 4px; padding: 6px; font-weight: normal;
  background: var(--surface-alt); color: var(--ink); border: 1px solid var(--rule); border-radius: 4px;
}
fieldset { border: 1px solid var(--rule); border-radius: 6px; margin-bottom: 12px; }
legend { color: var(--ink-mute); }
.lineup-input { display: inline-block; width: 30%; margin-right: 4px; }
.lineup-input input { width: 100%; }

.table-scroll { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--rule); white-space: nowrap; }
th { cursor: pointer; user-select: none; color: var(--ink-mute); font-weight: 600; }
th[title] { text-decoration: underline dotted var(--rule); text-underline-offset: 3px; }

.bargain-positive { color: var(--bargain-positive); font-weight: 600; }
.bargain-negative { color: var(--bargain-negative); font-weight: 600; }
.bargain-null { color: var(--ink-mute); }

.boom-bust { display: inline-flex; align-items: center; gap: 6px; }
.boom-bust-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.boom-bust-steady .boom-bust-dot { background: var(--steady); }
.boom-bust-balanced .boom-bust-dot { background: var(--ink-mute); }
.boom-bust-volatile .boom-bust-dot { background: var(--tertiary); }

.pick-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.pick-chip { border: 1px solid var(--rule); border-radius: 6px; padding: 6px 10px; text-align: center; min-width: 50px; background: var(--surface-alt); }
.pick-chip-round { font-size: 0.7rem; color: var(--ink-mute); }
.pick-chip-overall { font-size: 1.1rem; font-weight: 700; color: var(--ink); }
.pick-chip-gap { font-size: 0.7rem; color: var(--ink-mute); }

.stat { margin-bottom: 8px; font-size: 0.95rem; color: var(--ink); }

.position-filter { margin-bottom: 8px; }
.position-filter button {
  margin-right: 6px; padding: 4px 10px; border: 1px solid var(--rule);
  background: var(--surface-alt); color: var(--ink); border-radius: 4px; cursor: pointer;
}
.position-filter button.active { background: var(--primary); color: var(--ground); border-color: var(--primary); }

.strategy-checkboxes { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }
.strategy-checkboxes label { display: flex; align-items: center; gap: 4px; font-weight: normal; color: var(--ink); }

.run-row { display: flex; align-items: center; gap: 12px; margin: 12px 0; }
.run-row button {
  padding: 8px 16px; font-weight: 600; cursor: pointer;
  background: var(--primary); color: var(--ground); border: none; border-radius: 6px;
}
.run-row button:hover:not(:disabled) { background: var(--primary-dim); }
.run-row button:disabled { opacity: 0.5; cursor: not-allowed; }
.estimate { color: var(--ink-mute); font-size: 0.9rem; }

.error { color: var(--bargain-negative); padding: 8px 12px; background: rgba(232, 101, 79, 0.12); border: 1px solid var(--bargain-negative); border-radius: 6px; }

.loading { display: flex; align-items: center; gap: 10px; color: var(--ink-mute); }
.spinner {
  width: 16px; height: 16px; border-radius: 50%;
  border: 2px solid var(--rule); border-top-color: var(--primary);
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.noise-note { font-size: 0.85rem; color: var(--ink-mute); margin-top: 8px; }

@media (max-width: 800px) {
  .columns { flex-direction: column; }
  .column-left { flex: 1 1 auto; width: 100%; }
}
```

- [ ] **Step 3: Verify**

Run: `cd ~/Code/ffsim/web && npx tsc --noEmit` — CSS changes don't affect type-checking; this should show the same (expected, pre-existing) errors as Task 4 Step 4, nothing new.

- [ ] **Step 4: Commit**

```bash
git add web/src/index.css web/src/App.css
git commit -m "Add dark design system: tokens, spinner, mobile table scroll, boom/bust dots"
```

---

### Task 6: Frontend — `PlayerBoard.tsx` rewrite (P1 items 6/7)

**Files:**
- Modify: `web/src/components/PlayerBoard.tsx`

- [ ] **Step 1: Replace the file entirely**

```tsx
import { useEffect, useMemo, useState } from 'react';
import type { PlayerRow, RiskProfile } from '../api/types';

interface Props {
  players: PlayerRow[];
  riskProfile: RiskProfile;
}

type SortKey = 'name' | 'position' | 'team' | 'adp' | 'vor' | 'alpha' | 'tier' | 'weekly_cv' | 'draft_score';

const POSITIONS = ['All', 'QB', 'RB', 'WR', 'TE'] as const;

const COLUMNS: { key: SortKey; label: string; title?: string }[] = [
  { key: 'name', label: 'Name' },
  { key: 'position', label: 'Pos' },
  { key: 'team', label: 'Team' },
  {
    key: 'adp',
    label: 'ADP',
    title: 'Average draft position — roughly where this player gets picked in real drafts.',
  },
  {
    key: 'vor',
    label: 'Value',
    title:
      'Points above a freely-available replacement at the same position. This is why an elite RB is worth more than a WR who scores the same total.',
  },
  {
    key: 'alpha',
    label: 'Bargain',
    title:
      "How much better this player is than his draft price implies. Positive means underpriced. Blank means we don't have a reliable price for him.",
  },
  {
    key: 'weekly_cv',
    label: 'Boom/Bust',
    title:
      'How much a player swings week to week. Steady players win the weeks you should win. Volatile players win weeks you shouldn’t — and lose weeks you should. Neither is better; it depends on your strategy.',
  },
  {
    key: 'draft_score',
    label: 'Draft Score',
    title:
      'Value adjusted for your risk setting. This is the value half of a strategy — during a live draft the model also weighs roster needs and how much it will overpay early.',
  },
  {
    key: 'tier',
    label: 'Tier',
    title:
      'Players in a tier are close in value. The gap to the next tier is where the real dropoff happens — that’s the moment to act.',
  },
];

function formatSigned(value: number): string {
  const rounded = value.toFixed(1);
  return value >= 0 ? `+${rounded}` : rounded;
}

function boomBustBucket(weeklyCv: number): { label: string; className: string } {
  if (weeklyCv < 0.55) return { label: 'Steady', className: 'boom-bust-steady' };
  if (weeklyCv > 0.75) return { label: 'Volatile', className: 'boom-bust-volatile' };
  return { label: 'Balanced', className: 'boom-bust-balanced' };
}

export default function PlayerBoard({ players, riskProfile }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('draft_score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [positionFilter, setPositionFilter] = useState<(typeof POSITIONS)[number]>('All');

  // Changing the risk profile must visibly re-sort the board by Draft Score --
  // otherwise it looks like the control only affects the simulator.
  useEffect(() => {
    setSortKey('draft_score');
    setSortDir('desc');
  }, [riskProfile]);

  const rows = useMemo(() => {
    const filtered = positionFilter === 'All' ? players : players.filter((p) => p.position === positionFilter);
    return [...filtered].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      const cmp = typeof av === 'string' ? av.localeCompare(bv as string) : (av as number) - (bv as number);
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [players, positionFilter, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  }

  return (
    <div className="panel">
      <h2>Player board</h2>
      <div className="position-filter">
        {POSITIONS.map((pos) => (
          <button key={pos} className={pos === positionFilter ? 'active' : ''} onClick={() => setPositionFilter(pos)}>
            {pos}
          </button>
        ))}
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              {COLUMNS.map((col) => (
                <th key={col.key} title={col.title} onClick={() => toggleSort(col.key)}>
                  {col.label}
                  {sortKey === col.key ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const boomBust = boomBustBucket(p.weekly_cv);
              return (
                <tr key={p.player_id}>
                  <td>{p.name}</td>
                  <td>{p.position}</td>
                  <td>{p.team}</td>
                  <td>{p.adp.toFixed(1)}</td>
                  <td>{p.vor.toFixed(1)}</td>
                  <td className={p.alpha === null ? 'bargain-null' : p.alpha >= 0 ? 'bargain-positive' : 'bargain-negative'}>
                    {p.alpha === null ? '—' : formatSigned(p.alpha)}
                  </td>
                  <td>
                    <span className={`boom-bust ${boomBust.className}`}>
                      <span className="boom-bust-dot" />
                      {boomBust.label}
                    </span>
                  </td>
                  <td>{p.draft_score.toFixed(1)}</td>
                  <td>{p.tier}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify**

Run: `cd ~/Code/ffsim/web && npx tsc --noEmit` — expect errors only about `App.tsx` not yet passing `riskProfile` to `PlayerBoard` (fixed in Task 7) and `SettingsPanel`/`App` not yet handling `risk_profile` in settings (also Task 7). No errors should originate from `PlayerBoard.tsx` itself.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/PlayerBoard.tsx
git commit -m "Rework player board: Value/Bargain labels, tooltips, Boom/Bust and Draft Score columns"
```

---

### Task 7: Frontend — Risk Profile control, App wiring, branding, intro (P0 branding, P1 items 8/9/11)

**Files:**
- Modify: `web/src/components/SettingsPanel.tsx`
- Modify: `web/src/App.tsx`

- [ ] **Step 1: Add the Risk Profile control to `SettingsPanel.tsx`**

```tsx
// Add to imports:
import type { LeagueSettings, RiskProfile } from '../api/types';

// Add alongside SCORING_OPTIONS:
const RISK_PROFILE_OPTIONS: { value: RiskProfile; label: string }[] = [
  { value: 'safe', label: 'Play it safe' },
  { value: 'balanced', label: 'Balanced' },
  { value: 'ceiling', label: 'Chase upside' },
  { value: 'max_ceiling', label: 'Full send' },
];
```

Add this block right after the "Reserved slots" `<label>` (before the closing `</div>` of the component):

```tsx
      <label>
        Risk profile
        <select
          value={settings.risk_profile}
          onChange={(e) => update({ risk_profile: e.target.value as LeagueSettings['risk_profile'] })}
        >
          {RISK_PROFILE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </label>
```

- [ ] **Step 2: Rewrite `web/src/App.tsx` entirely**

```tsx
import { useEffect, useRef, useState } from 'react';
import type { LeagueSettings, LeagueResponse } from './api/types';
import { fetchLeague } from './api/client';
import logo from './assets/logo.png';
import SettingsPanel from './components/SettingsPanel';
import DraftPosition from './components/DraftPosition';
import ScarcityTable from './components/ScarcityTable';
import PlayerBoard from './components/PlayerBoard';
import SimulationPanel from './components/SimulationPanel';
import './App.css';

const DEFAULT_SETTINGS: LeagueSettings = {
  teams: 10,
  slot: 6,
  scoring: 'half_ppr',
  bench: 6,
  lineup: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1 },
  playoff_teams: 4,
  reserved_slots: 2,
  risk_profile: 'balanced',
};

const DEBOUNCE_MS = 300;

export default function App() {
  const [settings, setSettings] = useState<LeagueSettings>(DEFAULT_SETTINGS);
  const [league, setLeague] = useState<LeagueResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const requestId = ++requestIdRef.current;
      fetchLeague(settings)
        .then((res) => {
          if (requestIdRef.current !== requestId) return;
          setLeague(res);
          setError(null);
        })
        .catch((e) => {
          if (requestIdRef.current !== requestId) return;
          setError(e instanceof Error ? e.message : String(e));
        });
    }, DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [settings]);

  return (
    <div className="app">
      <div className="app-header">
        <img src={logo} alt="Mispricing Engine logo" />
        <h1>Mispricing Engine</h1>
      </div>
      <p className="tagline">Find the mispriced players, not the good ones.</p>
      <p className="intro">
        Most draft tools rank players. This one prices them. <strong>Value</strong> is how many points a
        player scores above a freely-available replacement at his position; <strong>Bargain</strong> is how
        much cheaper he is than that value deserves.
      </p>
      <div className="columns">
        <div className="column-left">
          <SettingsPanel settings={settings} onChange={setSettings} />
        </div>
        <div className="column-right">
          {error && <div className="error">Could not reach the API: {error}</div>}
          {!error && !league && (
            <div className="loading">
              <span className="spinner" />
              Loading...
            </div>
          )}
          {!error && league && (
            <>
              <DraftPosition
                picks={league.picks}
                hedgeWindow={league.hedge_window}
                rounds={league.rounds}
                reservedSlots={league.reserved_slots}
                totalRounds={league.total_rounds}
              />
              <ScarcityTable rows={league.scarcity} />
              <PlayerBoard players={league.players} riskProfile={settings.risk_profile} />
            </>
          )}
        </div>
      </div>
      <SimulationPanel settings={settings} />
    </div>
  );
}
```

- [ ] **Step 3: Verify**

Run: `cd ~/Code/ffsim/web && npx tsc --noEmit` — expect **zero errors** now (this is the task that closes out all the type errors seeded since Task 4).

- [ ] **Step 4: Commit**

```bash
git add web/src/components/SettingsPanel.tsx web/src/App.tsx
git commit -m "Add Risk Profile control, logo/tagline/intro, and loading spinner to App"
```

---

### Task 8: Frontend — simulator copy update (P0 item 10 wording)

**Files:**
- Modify: `web/src/components/SimulationPanel.tsx`

- [ ] **Step 1: Update the noise-note text**

```tsx
// OLD
          <p className="noise-note">
            With fewer than ~1000 simulations, differences of a few percentage points between strategies are within noise.
          </p>
// NEW
          <p className="noise-note">
            Differences under a few percentage points are noise below ~1000 sims.
          </p>
```

(The estimated-runtime display and the lack of an `n_sims` cap are both already correct — confirmed in reconnaissance — no other changes needed in this file.)

- [ ] **Step 2: Verify**

Run: `cd ~/Code/ffsim/web && npx tsc --noEmit` — still zero errors.

- [ ] **Step 3: Commit**

```bash
git add web/src/components/SimulationPanel.tsx
git commit -m "Update simulator noise disclaimer to exact v1 copy"
```

---

### Task 9: End-to-end verification (all P0/P1 items, browser-driven)

**Files:** none — verification only.

- [ ] **Step 1: Full backend verification**

```bash
cd ~/Code/ffsim && source .venv/bin/activate
python validate.py   # must exit 0 -- ffsim/ package itself still correct
python check_pool.py 2>&1 | sed -n '/^7\./,/^$/p'   # record positional alpha means, confirm still collapsed
```

- [ ] **Step 2: Full frontend build verification**

```bash
cd ~/Code/ffsim/web
npx tsc --noEmit   # zero errors
npm run build-dev      # succeeds, dist/ produced
```

- [ ] **Step 3: Start the app and drive it in a real browser**

```bash
cd ~/Code/ffsim && make dev &
```

Navigate to `http://localhost:5173` and confirm, item by item:

- **Branding**: tab title is "Mispricing Engine", favicon shows the logo image, header shows the logo image + "Mispricing Engine" + tagline "Find the mispriced players, not the good ones.", intro paragraph is present and readable.
- **Dark theme**: page background is near-black, panels are a lighter dark surface, primary green accents on buttons/active states — not the old light theme.
- **Real data**: player board shows real NFL player names, not "WR05 Synthetic" etc.
- **Column rename + tooltips**: headers read Name/Pos/Team/ADP/Value/Bargain/Boom-Bust/Draft Score/Tier; hovering ADP/Value/Bargain/Boom-Bust/Draft-Score/Tier headers shows the specified tooltip text (native browser tooltip via `title`).
- **Bargain formatting**: positive values show a leading `+` (e.g. `+33.4`), negative show `-` (e.g. `-12.7`), null shows `—` in muted grey, colors are green/red/muted per the design tokens.
- **Boom/Bust**: every row shows a colored dot + word (Steady/Balanced/Volatile) — never just a bare color.
- **Draft Score default sort**: board loads sorted by Draft Score descending (▼ on that header).
- **Risk Profile control**: change it in Settings; confirm (a) the board's Draft Score column values change, (b) the board visibly re-sorts (still sorted by Draft Score, new order) even if you'd previously clicked a different column header to sort.
- **Max ceiling / safe** risk profile top-5 differ from each other (already confirmed via curl in Task 3, spot check visually here too).
- **Simulator**: run a small simulation (e.g. 20 sims), confirm the estimate-seconds text and the exact new noise-note wording appear, confirm no `max` cap prevents typing e.g. 5000 into the count field.
- **Loading state**: reload the page, briefly see the spinner (may be very fast — check the code path is exercised, not necessarily eyeball it at 5173's typical <50ms response).
- **Error state**: stop the backend only, change a setting, confirm the explicit error panel appears and no stale/placeholder player data remains visible.
- **Mobile**: resize the browser viewport to ~375px wide (or use a device emulation mode); confirm the two-column layout stacks to one column and the player table scrolls horizontally inside its own container without the page body scrolling sideways.

- [ ] **Step 4: Tear down**

```bash
lsof -ti :8000 | xargs -r kill
lsof -ti :5173 | xargs -r kill
```
Confirm both ports free afterward.

---

## Self-review notes

- **Spec coverage**: all 12 numbered items (P0 1-4, P1 5-12) plus the header/branding preamble are each covered by a task above. Item 1 (privacy) and item 2 (VOR floor) required no code change — verification only, explicitly called out so the executor doesn't waste time re-implementing already-done work.
- **Placeholder scan**: no TBD/TODO; every step has literal, complete code. The one deliberately-flagged gap (Boom/Bust "steady" color, and the standard-scoring pool fallback) are explicit judgment calls with stated rationale, not silent placeholders.
- **Type consistency**: `RiskProfile` type flows consistently from `web/src/api/types.ts` → `SettingsPanel.tsx` → `App.tsx` → `PlayerBoard.tsx`; `draft_score`/`weekly_cv` flow consistently from `api/models.py` → `api/main.py` → `web/src/api/types.ts` → `PlayerBoard.tsx`. Field names match exactly at every hop (snake_case throughout, matching the existing project convention).
- **Scope discipline**: no new dependencies introduced (no tooltip library, no CSS-in-JS, no charting library). CORS/VITE_API_URL explicitly untouched per the request. `api_simulate` explicitly does NOT receive `risk_profile` semantics beyond what it already ignores (it receives the full `SimulateRequest` which extends `LeagueSettingsRequest` and therefore includes `risk_profile` on the wire, but the handler never reads `req.risk_profile` — confirmed in Task 3 Step 4's diff).
