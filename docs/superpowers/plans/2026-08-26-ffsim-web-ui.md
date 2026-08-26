# ffsim Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local single-page web UI on top of the existing `ffsim` package — a FastAPI backend that wraps the model and a Vite/React/TypeScript frontend with instant valuation feedback and on-demand simulation.

**Architecture:** Two new top-level directories, `api/` (FastAPI) and `web/` (Vite React TS), added alongside the untouched `ffsim/` package. `api/main.py` caches the deterministic player pool once at startup and exposes `POST /api/league` (sub-second valuation recompute) and `POST /api/simulate` (tens-of-seconds Monte Carlo run). The frontend holds all state in plain React `useState`, debounces settings changes into `/api/league` calls, and only calls `/api/simulate` on an explicit button click. All fetches go through one client module (`web/src/api/client.ts`) that reads `VITE_API_URL`, defaulting to relative paths so Vite's dev proxy (`/api` → `localhost:8000`) handles local dev with zero config.

This is almost entirely integration/plumbing code — request parsing, DataFrame-to-JSON shaping, and rendering — not algorithmic logic. There are no pure functions here worth isolating in unit tests; correctness is verified functionally, against known-correct numbers from `ffsim`'s own `validate.py`, via curl during backend development and via a real browser at the end. Each task below is scoped to one file (or one tightly-coupled file pair) rather than a red/green unit test cycle.

**Tech Stack:** FastAPI, uvicorn, pydantic (backend, in the existing `.venv`); Vite, React, TypeScript (frontend, own `npm` project in `web/`). No other dependencies — if a task seems to need one, stop and ask before adding it.

---

## Ground truth (verified against the live model before writing this plan)

```
hedge windows, 10 teams, slots 1-10:  [1, 3, 5, 7, 9, 9, 7, 5, 3, 1]
pick_numbers[:5], 10 teams, slot 2:   [2, 19, 22, 39, 42]
pick_numbers[:5], 10 teams, slot 6:   [6, 15, 26, 35, 46]

top VOR by position, 10 teams, half_ppr:  QB 80.3   RB 98.0   WR 124.3   TE 106.9
top VOR by position, 10 teams, full ppr:  QB 80.3   RB 102.7  WR 153.6   TE 130.6
top VOR by position, 12 teams, half_ppr:  QB 92.5   RB 116.1  WR 139.2   TE 115.8
```

QB VOR is scoring-invariant (component-scored, no reception term touches it). WR/TE/RB VOR rises with PPR. Every position's VOR rises going 10→12 teams. These are the acceptance numbers for Task 4 and Task 15.

## API surface confirmed by reading the source

- `ffsim/__init__.py` exports `League, Scoring, DEFAULT_LINEUP, Strategy, Personality, PRESETS, ARCHETYPES, default_field, run_draft, evaluate, objective, build_board, league_report, make_pool, load_csv, prepare, validate, simulate_season, play_league, add_valuation, replacement_levels, market_curve, availability`.
- **`effective_starters` is NOT in `ffsim/__init__.py`'s `__all__`.** It must be imported directly: `from ffsim.valuation import effective_starters`.
- `League` and `Scoring` are frozen dataclasses (`ffsim/config.py`) — construct fresh per request. `League.__post_init__` raises `ValueError` if `slot` is outside `1..teams` or `playoff_teams > teams`.
- `board = ff.build_board(pool, league)` returns a DataFrame with (among others) `player_id, name, position, team, adp, vor, alpha, tier` — all confirmed present, 230 rows for the default pool.
- `evaluate(pool, league, strategies, n_sims=100, seed=0)` returns `(summary_df, detail_df)`. `summary_df` columns are exactly: `strategy, champ_%, playoff_%, mean_pts, P10_pts, P85_pts, ceiling_CVaR, mean_wins` (note the literal `%` and mixed case — these must be accessed by exact string key, not attribute).
- `PRESETS` keys: `bpa, balanced, ceiling, max_ceiling, safe, zero_rb, hero_rb`.
- Installed in `.venv`: Python 3.14.4, numpy 2.5.2, pandas 3.0.5. No `docs/` or `api/`/`web/` directories exist yet.

---

### Task 1: Backend scaffold — `api/requirements.txt`

**Files:**
- Create: `api/requirements.txt`

- [ ] **Step 1: Create the requirements file**

```
fastapi
uvicorn[standard]
pydantic
```

- [ ] **Step 2: Install into the existing venv**

Run: `cd ~/Code/ffsim && source .venv/bin/activate && pip install -r api/requirements.txt`
Expected: fastapi, uvicorn, and pydantic (and their transitive deps: starlette, click, h11, etc.) install without error.

- [ ] **Step 3: Verify import works**

Run: `python -c "import fastapi, uvicorn, pydantic; print(fastapi.__version__, pydantic.__version__)"`
Expected: prints two version strings, no traceback.

- [ ] **Step 4: Commit**

```bash
cd ~/Code/ffsim && git status
```

(Skip commit if this directory is not a git repo — confirmed not one at session start. If the user has since run `git init`, commit with `git add api/requirements.txt && git commit -m "chore: add API requirements"`.)

---

### Task 2: Backend — `api/models.py` (pydantic request/response types)

**Files:**
- Create: `api/models.py`

- [ ] **Step 1: Write the full models file**

```python
"""Pydantic request/response shapes for the ffsim API.

These mirror ffsim's own domain types (League, Scoring, the board DataFrame,
the evaluate() summary) without depending on ffsim internals directly, so the
API's wire format stays stable even if ffsim's internal representation shifts.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel


class LineupSettings(BaseModel):
    QB: int = 1
    RB: int = 2
    WR: int = 2
    TE: int = 1
    FLEX: int = 1


class LeagueSettingsRequest(BaseModel):
    teams: int = 10
    slot: int = 6
    scoring: Literal["half_ppr", "ppr", "standard"] = "half_ppr"
    bench: int = 6
    lineup: LineupSettings = LineupSettings()
    playoff_teams: int = 4


class PickChip(BaseModel):
    round: int
    overall_pick: int
    gap_to_next: Optional[int] = None


class PositionScarcityRow(BaseModel):
    position: str
    effective_starters: int
    replacement_points: float
    top_vor: float


class PlayerRow(BaseModel):
    player_id: str
    name: str
    position: str
    team: str
    adp: float
    vor: float
    alpha: float
    tier: int


class LeagueResponse(BaseModel):
    pick_numbers: List[int]
    hedge_window: int
    rounds: int
    describe: str
    scarcity: List[PositionScarcityRow]
    players: List[PlayerRow]
    picks: List[PickChip]


class SimulateRequest(LeagueSettingsRequest):
    strategies: List[str] = ["bpa", "balanced", "ceiling"]
    n_sims: int = 100


class StrategyResultRow(BaseModel):
    strategy: str
    champ_pct: float
    playoff_pct: float
    mean_pts: float
    p10_pts: float
    p85_pts: float
    ceiling_cvar: float
    mean_wins: float


class SimulateResponse(BaseModel):
    results: List[StrategyResultRow]
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `cd ~/Code/ffsim && source .venv/bin/activate && python -c "import sys; sys.path.insert(0, 'api'); import models; print(models.LeagueSettingsRequest())"`
Expected: prints a `LeagueSettingsRequest` with the default field values, no traceback.

- [ ] **Step 3: Commit** (if in a git repo)

```bash
git add api/models.py && git commit -m "feat: add API pydantic models"
```

---

### Task 3: Backend — `api/main.py`, `/api/league` endpoint

**Files:**
- Create: `api/main.py`

- [ ] **Step 1: Write main.py with pool caching, the League builder, and `/api/league`**

```python
"""FastAPI service bridging the ffsim model to the web UI.

Two endpoints with very different cost profiles:
  POST /api/league    -- single-digit milliseconds, fires on every settings change
  POST /api/simulate   -- tens of seconds, fires only on explicit user action

The player pool is deterministic (make_pool() is seeded), so it is built once
at import time and reused across every request.
"""
import sys
from pathlib import Path

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


def build_league(settings: LeagueSettingsRequest) -> ff.League:
    scoring_fn = SCORING_BUILDERS[settings.scoring]
    lineup = settings.lineup.model_dump()
    try:
        return ff.League(
            teams=settings.teams,
            slot=settings.slot,
            lineup=lineup,
            flex_eligible=("RB", "WR", "TE"),
            bench=settings.bench,
            scoring=scoring_fn(),
            playoff_teams=settings.playoff_teams,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
            alpha=round(row.alpha, 1),
            tier=int(row.tier),
        )
        for row in top.itertuples()
    ]

    pick_numbers = league.pick_numbers()
    picks = [
        PickChip(
            round=i + 1,
            overall_pick=overall,
            gap_to_next=(pick_numbers[i + 1] - overall) if i + 1 < len(pick_numbers) else None,
        )
        for i, overall in enumerate(pick_numbers)
    ]

    return LeagueResponse(
        pick_numbers=pick_numbers,
        hedge_window=league.hedge_window(),
        rounds=league.rounds,
        describe=league.describe(),
        scarcity=scarcity,
        players=players,
        picks=picks,
    )
```

- [ ] **Step 2: Start the server and verify it boots**

Run: `cd ~/Code/ffsim && source .venv/bin/activate && uvicorn main:app --app-dir api --port 8000 &`
Expected: log line `Uvicorn running on http://127.0.0.1:8000`, no traceback.

- [ ] **Step 3: Verify `/api/league` returns real data**

Run:
```bash
curl -s localhost:8000/api/league -H 'Content-Type: application/json' \
  -d '{"teams":10,"slot":6,"scoring":"half_ppr","bench":6,"lineup":{"QB":1,"RB":2,"WR":2,"TE":1,"FLEX":1},"playoff_teams":4}' \
  | python -m json.tool | head -30
```
Expected: JSON with `pick_numbers` starting `[6, 15, 26, 35, 46, ...]`, `hedge_window: 9`, `players` containing 150 entries.

- [ ] **Step 4: Stop the server, commit**

```bash
kill %1
git add api/main.py && git commit -m "feat: add /api/league endpoint"
```

---

### Task 4: Backend — `/api/simulate` endpoint and full curl verification

**Files:**
- Modify: `api/main.py` (append the endpoint)

- [ ] **Step 1: Append `/api/simulate` to `api/main.py`**

```python
@app.post("/api/simulate", response_model=SimulateResponse)
def api_simulate(req: SimulateRequest) -> SimulateResponse:
    league = build_league(req)
    unknown = [s for s in req.strategies if s not in ff.PRESETS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown strategies: {unknown}")

    summary, _detail = ff.evaluate(POOL, league, req.strategies, n_sims=req.n_sims, seed=0)

    results = [
        StrategyResultRow(
            strategy=row["strategy"],
            champ_pct=row["champ_%"],
            playoff_pct=row["playoff_%"],
            mean_pts=row["mean_pts"],
            p10_pts=row["P10_pts"],
            p85_pts=row["P85_pts"],
            ceiling_cvar=row["ceiling_CVaR"],
            mean_wins=row["mean_wins"],
        )
        for _, row in summary.iterrows()
    ]
    return SimulateResponse(results=results)
```

- [ ] **Step 2: Start the server**

Run: `cd ~/Code/ffsim && source .venv/bin/activate && uvicorn main:app --app-dir api --port 8000 &`

- [ ] **Step 3: Verify pick maps exactly (acceptance criterion 1)**

```bash
curl -s localhost:8000/api/league -H 'Content-Type: application/json' \
  -d '{"teams":10,"slot":2,"scoring":"half_ppr","bench":6,"lineup":{"QB":1,"RB":2,"WR":2,"TE":1,"FLEX":1},"playoff_teams":4}' \
  | python -c "import json,sys; d=json.load(sys.stdin); print(d['pick_numbers'][:5])"
```
Expected: `[2, 19, 22, 39, 42]`

Repeat with `"slot":6`. Expected: `[6, 15, 26, 35, 46]`

- [ ] **Step 4: Verify hedge window symmetry (acceptance criterion 2)**

```bash
for s in 1 2 3 4 5 6 7 8 9 10; do
  curl -s localhost:8000/api/league -H 'Content-Type: application/json' \
    -d "{\"teams\":10,\"slot\":$s,\"scoring\":\"half_ppr\",\"bench\":6,\"lineup\":{\"QB\":1,\"RB\":2,\"WR\":2,\"TE\":1,\"FLEX\":1},\"playoff_teams\":4}" \
    | python -c "import json,sys; print(json.load(sys.stdin)['hedge_window'])"
done
```
Expected output, one per line: `1 3 5 7 9 9 7 5 3 1`

- [ ] **Step 5: Verify the scoring knob (acceptance criterion 3)**

```bash
for sc in half_ppr ppr; do
  echo "== $sc =="
  curl -s localhost:8000/api/league -H 'Content-Type: application/json' \
    -d "{\"teams\":10,\"slot\":6,\"scoring\":\"$sc\",\"bench\":6,\"lineup\":{\"QB\":1,\"RB\":2,\"WR\":2,\"TE\":1,\"FLEX\":1},\"playoff_teams\":4}" \
    | python -c "import json,sys; d=json.load(sys.stdin); print({r['position']: r['top_vor'] for r in d['scarcity']})"
done
```
Expected: `half_ppr` → `QB 80.3, RB 98.0, WR 124.3, TE 106.9`; `ppr` → `QB 80.3` (unchanged), `RB 102.7, WR 153.6, TE 130.6` (all risen). If QB moves, or nothing moves, stop and debug before continuing — this means scoring isn't actually threading through.

- [ ] **Step 6: Verify league size sensitivity (acceptance criterion 4)**

```bash
for t in 10 12; do
  echo "== $t teams =="
  curl -s localhost:8000/api/league -H 'Content-Type: application/json' \
    -d "{\"teams\":$t,\"slot\":6,\"scoring\":\"half_ppr\",\"bench\":6,\"lineup\":{\"QB\":1,\"RB\":2,\"WR\":2,\"TE\":1,\"FLEX\":1},\"playoff_teams\":4}" \
    | python -c "import json,sys; d=json.load(sys.stdin); print({r['position']: r['top_vor'] for r in d['scarcity']})"
done
```
Expected: every position's `top_vor` at 12 teams exceeds its 10-team value (10-team: QB 80.3/RB 98.0/WR 124.3/TE 106.9 → 12-team: QB 92.5/RB 116.1/WR 139.2/TE 115.8).

- [ ] **Step 7: Verify `/api/simulate` runs end to end (acceptance criterion 5)**

```bash
curl -s localhost:8000/api/simulate -H 'Content-Type: application/json' \
  -d '{"teams":10,"slot":6,"scoring":"half_ppr","bench":6,"lineup":{"QB":1,"RB":2,"WR":2,"TE":1,"FLEX":1},"playoff_teams":4,"strategies":["bpa","balanced","ceiling"],"n_sims":20}' \
  | python -m json.tool
```
Expected: a JSON object with `results`, a list of 3 objects each with `strategy, champ_pct, playoff_pct, mean_pts, p10_pts, p85_pts, ceiling_cvar, mean_wins` populated with plausible non-zero numbers. Should return within a few seconds (20 sims × 3 strategies × ~0.07s ≈ 4s).

- [ ] **Step 8: Stop the server, commit**

```bash
kill %1
git add api/main.py && git commit -m "feat: add /api/simulate endpoint"
```

---

### Task 5: Frontend scaffold — Vite + React + TypeScript project

**Files:**
- Create: `web/` (via `npm create vite`)
- Create: `web/.env.example`
- Modify: `web/vite.config.ts`

- [ ] **Step 1: Scaffold the project**

Run: `cd ~/Code/ffsim && npm create vite@latest web -- --template react-ts`
Expected: `web/` created with a standard Vite React TS layout (`package.json`, `src/App.tsx`, `src/main.tsx`, `vite.config.ts`, `index.html`, `tsconfig.json`).

- [ ] **Step 2: Install dependencies**

Run: `cd ~/Code/ffsim/web && npm install`
Expected: completes without error, creates `node_modules/` and `package-lock.json`.

- [ ] **Step 3: Configure the dev proxy in `web/vite.config.ts`**

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
```

- [ ] **Step 4: Add `web/.env.example`**

```
# Leave unset for local dev — requests go to relative /api paths and
# Vite's dev proxy (see vite.config.ts) forwards them to localhost:8000.
# To point a built frontend at a hosted API, set this to its full URL.
VITE_API_URL=
```

- [ ] **Step 5: Verify the dev server boots**

Run: `cd ~/Code/ffsim/web && npm run dev &` then `curl -sI localhost:5173 | head -1`
Expected: `HTTP/1.1 200 OK`. Then `kill %1`.

- [ ] **Step 6: Commit**

```bash
cd ~/Code/ffsim && git add web/.gitignore web/package.json web/package-lock.json web/vite.config.ts web/tsconfig*.json web/index.html web/.env.example web/src web/public 2>/dev/null; git commit -m "chore: scaffold Vite React TS frontend"
```

---

### Task 6: Frontend — `web/src/api/types.ts`

**Files:**
- Create: `web/src/api/types.ts`

- [ ] **Step 1: Write TypeScript interfaces mirroring the pydantic models**

```typescript
export interface LineupSettings {
  QB: number;
  RB: number;
  WR: number;
  TE: number;
  FLEX: number;
}

export type ScoringMode = 'half_ppr' | 'ppr' | 'standard';

export interface LeagueSettings {
  teams: number;
  slot: number;
  scoring: ScoringMode;
  bench: number;
  lineup: LineupSettings;
  playoff_teams: number;
}

export interface PickChip {
  round: number;
  overall_pick: number;
  gap_to_next: number | null;
}

export interface PositionScarcityRow {
  position: string;
  effective_starters: number;
  replacement_points: number;
  top_vor: number;
}

export interface PlayerRow {
  player_id: string;
  name: string;
  position: string;
  team: string;
  adp: number;
  vor: number;
  alpha: number;
  tier: number;
}

export interface LeagueResponse {
  pick_numbers: number[];
  hedge_window: number;
  rounds: number;
  describe: string;
  scarcity: PositionScarcityRow[];
  players: PlayerRow[];
  picks: PickChip[];
}

export interface SimulateRequest extends LeagueSettings {
  strategies: string[];
  n_sims: number;
}

export interface StrategyResultRow {
  strategy: string;
  champ_pct: number;
  playoff_pct: number;
  mean_pts: number;
  p10_pts: number;
  p85_pts: number;
  ceiling_cvar: number;
  mean_wins: number;
}

export interface SimulateResponse {
  results: StrategyResultRow[];
}
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd ~/Code/ffsim/web && npx tsc --noEmit`
Expected: no errors (the default Vite template's `App.tsx` still compiles against the untouched starter code at this point).

---

### Task 7: Frontend — `web/src/api/client.ts`

**Files:**
- Create: `web/src/api/client.ts`

- [ ] **Step 1: Write the single fetch client**

```typescript
import type {
  LeagueSettings,
  LeagueResponse,
  SimulateRequest,
  SimulateResponse,
} from './types';

const BASE_URL = import.meta.env.VITE_API_URL ?? '';

async function post<TResponse>(path: string, body: unknown): Promise<TResponse> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${path} failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<TResponse>;
}

export function fetchLeague(settings: LeagueSettings): Promise<LeagueResponse> {
  return post<LeagueResponse>('/api/league', settings);
}

export function runSimulation(req: SimulateRequest): Promise<SimulateResponse> {
  return post<SimulateResponse>('/api/simulate', req);
}
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd ~/Code/ffsim/web && npx tsc --noEmit`
Expected: no errors.

---

### Task 8: Frontend — `web/src/components/SettingsPanel.tsx`

**Files:**
- Create: `web/src/components/SettingsPanel.tsx`

- [ ] **Step 1: Write the component**

```tsx
import type { LeagueSettings } from '../api/types';

interface Props {
  settings: LeagueSettings;
  onChange: (next: LeagueSettings) => void;
}

const SCORING_OPTIONS: { value: LeagueSettings['scoring']; label: string }[] = [
  { value: 'half_ppr', label: 'Half PPR' },
  { value: 'ppr', label: 'Full PPR' },
  { value: 'standard', label: 'Standard' },
];

const LINEUP_POSITIONS = ['QB', 'RB', 'WR', 'TE', 'FLEX'] as const;

export default function SettingsPanel({ settings, onChange }: Props) {
  function update(patch: Partial<LeagueSettings>) {
    const next = { ...settings, ...patch };
    if (next.slot > next.teams) next.slot = next.teams;
    onChange(next);
  }

  function updateLineup(pos: (typeof LINEUP_POSITIONS)[number], value: number) {
    onChange({ ...settings, lineup: { ...settings.lineup, [pos]: value } });
  }

  const teamOptions = Array.from({ length: 7 }, (_, i) => i + 8); // 8..14
  const slotOptions = Array.from({ length: settings.teams }, (_, i) => i + 1);

  return (
    <div className="panel settings-panel">
      <h2>League settings</h2>

      <label>
        Teams
        <select value={settings.teams} onChange={(e) => update({ teams: Number(e.target.value) })}>
          {teamOptions.map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </label>

      <label>
        Scoring
        <select
          value={settings.scoring}
          onChange={(e) => update({ scoring: e.target.value as LeagueSettings['scoring'] })}
        >
          {SCORING_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </label>

      <label>
        Draft slot
        <select value={settings.slot} onChange={(e) => update({ slot: Number(e.target.value) })}>
          {slotOptions.map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </label>

      <label>
        Bench size
        <input
          type="number"
          min={0}
          value={settings.bench}
          onChange={(e) => update({ bench: Number(e.target.value) })}
        />
      </label>

      <fieldset>
        <legend>Starting lineup</legend>
        {LINEUP_POSITIONS.map((pos) => (
          <label key={pos} className="lineup-input">
            {pos}
            <input
              type="number"
              min={0}
              value={settings.lineup[pos]}
              onChange={(e) => updateLineup(pos, Number(e.target.value))}
            />
          </label>
        ))}
      </fieldset>

      <label>
        Playoff teams
        <select
          value={settings.playoff_teams}
          onChange={(e) => update({ playoff_teams: Number(e.target.value) })}
        >
          {[2, 4, 6].map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </label>
    </div>
  );
}
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd ~/Code/ffsim/web && npx tsc --noEmit`
Expected: no new errors from this file (App.tsx not yet wired, so it won't be referenced/compiled into the app bundle yet, but `tsc --noEmit` type-checks the whole project including unreferenced files under `include`, so it must be clean on its own).

---

### Task 9: Frontend — `web/src/components/DraftPosition.tsx`

**Files:**
- Create: `web/src/components/DraftPosition.tsx`

- [ ] **Step 1: Write the component**

```tsx
import type { PickChip } from '../api/types';

interface Props {
  picks: PickChip[];
  hedgeWindow: number;
}

export default function DraftPosition({ picks, hedgeWindow }: Props) {
  return (
    <div className="panel">
      <h2>Draft position</h2>
      <div className="stat">Hedge window: <strong>{hedgeWindow}</strong></div>
      <div className="pick-chips">
        {picks.map((p) => (
          <div key={p.round} className="pick-chip">
            <div className="pick-chip-round">R{p.round}</div>
            <div className="pick-chip-overall">{p.overall_pick}</div>
            {p.gap_to_next !== null && <div className="pick-chip-gap">+{p.gap_to_next}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd ~/Code/ffsim/web && npx tsc --noEmit`
Expected: no errors.

---

### Task 10: Frontend — `web/src/components/ScarcityTable.tsx`

**Files:**
- Create: `web/src/components/ScarcityTable.tsx`

- [ ] **Step 1: Write the component**

```tsx
import type { PositionScarcityRow } from '../api/types';

interface Props {
  rows: PositionScarcityRow[];
}

export default function ScarcityTable({ rows }: Props) {
  return (
    <div className="panel">
      <h2>Positional scarcity</h2>
      <table>
        <thead>
          <tr>
            <th>Position</th>
            <th>Effective starters</th>
            <th>Replacement pts</th>
            <th>Top VOR</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.position}>
              <td>{r.position}</td>
              <td>{r.effective_starters}</td>
              <td>{r.replacement_points.toFixed(1)}</td>
              <td>{r.top_vor.toFixed(1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd ~/Code/ffsim/web && npx tsc --noEmit`
Expected: no errors.

---

### Task 11: Frontend — `web/src/components/PlayerBoard.tsx`

**Files:**
- Create: `web/src/components/PlayerBoard.tsx`

- [ ] **Step 1: Write the component**

```tsx
import { useMemo, useState } from 'react';
import type { PlayerRow } from '../api/types';

interface Props {
  players: PlayerRow[];
}

type SortKey = 'name' | 'position' | 'team' | 'adp' | 'vor' | 'alpha' | 'tier';

const POSITIONS = ['All', 'QB', 'RB', 'WR', 'TE'] as const;

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: 'name', label: 'Name' },
  { key: 'position', label: 'Pos' },
  { key: 'team', label: 'Team' },
  { key: 'adp', label: 'ADP' },
  { key: 'vor', label: 'VOR' },
  { key: 'alpha', label: 'Alpha' },
  { key: 'tier', label: 'Tier' },
];

export default function PlayerBoard({ players }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>('vor');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [positionFilter, setPositionFilter] = useState<(typeof POSITIONS)[number]>('All');

  const rows = useMemo(() => {
    const filtered = positionFilter === 'All' ? players : players.filter((p) => p.position === positionFilter);
    return [...filtered].sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
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
      <table>
        <thead>
          <tr>
            {COLUMNS.map((col) => (
              <th key={col.key} onClick={() => toggleSort(col.key)}>
                {col.label}{sortKey === col.key ? (sortDir === 'asc' ? ' ▲' : ' ▼') : ''}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.player_id}>
              <td>{p.name}</td>
              <td>{p.position}</td>
              <td>{p.team}</td>
              <td>{p.adp.toFixed(1)}</td>
              <td>{p.vor.toFixed(1)}</td>
              <td className={p.alpha >= 0 ? 'alpha-positive' : 'alpha-negative'}>{p.alpha.toFixed(1)}</td>
              <td>{p.tier}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd ~/Code/ffsim/web && npx tsc --noEmit`
Expected: no errors.

---

### Task 12: Frontend — `web/src/components/SimulationPanel.tsx`

**Files:**
- Create: `web/src/components/SimulationPanel.tsx`

- [ ] **Step 1: Write the component**

```tsx
import { useState } from 'react';
import type { LeagueSettings, StrategyResultRow } from '../api/types';
import { runSimulation } from '../api/client';

interface Props {
  settings: LeagueSettings;
}

const STRATEGIES = ['bpa', 'balanced', 'ceiling', 'max_ceiling', 'safe', 'zero_rb', 'hero_rb'];
const SECONDS_PER_SIM_STRATEGY = 0.07;

export default function SimulationPanel({ settings }: Props) {
  const [selected, setSelected] = useState<string[]>(['bpa', 'balanced', 'ceiling']);
  const [nSims, setNSims] = useState(100);
  const [results, setResults] = useState<StrategyResultRow[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleStrategy(name: string) {
    setSelected((prev) => (prev.includes(name) ? prev.filter((s) => s !== name) : [...prev, name]));
  }

  const estimatedSeconds = Math.round(selected.length * nSims * SECONDS_PER_SIM_STRATEGY);

  async function runSim() {
    setLoading(true);
    setError(null);
    try {
      const res = await runSimulation({ ...settings, strategies: selected, n_sims: nSims });
      setResults([...res.results].sort((a, b) => b.champ_pct - a.champ_pct));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="panel">
      <h2>Simulation</h2>
      <div className="strategy-checkboxes">
        {STRATEGIES.map((name) => (
          <label key={name}>
            <input type="checkbox" checked={selected.includes(name)} onChange={() => toggleStrategy(name)} />
            {name}
          </label>
        ))}
      </div>
      <label>
        Simulation count
        <input type="number" min={1} value={nSims} onChange={(e) => setNSims(Number(e.target.value))} />
      </label>
      <div className="run-row">
        <button onClick={runSim} disabled={loading || selected.length === 0}>
          {loading ? 'Running...' : 'Run simulation'}
        </button>
        <span className="estimate">~{estimatedSeconds}s estimated</span>
      </div>
      {error && <div className="error">Simulation failed: {error}</div>}
      {results && (
        <>
          <table>
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Champ %</th>
                <th>Playoff %</th>
                <th>Mean pts</th>
                <th>P10 pts</th>
                <th>P85 pts</th>
                <th>Ceiling CVaR</th>
                <th>Mean wins</th>
              </tr>
            </thead>
            <tbody>
              {results.map((r) => (
                <tr key={r.strategy}>
                  <td>{r.strategy}</td>
                  <td>{r.champ_pct.toFixed(2)}</td>
                  <td>{r.playoff_pct.toFixed(1)}</td>
                  <td>{r.mean_pts.toFixed(1)}</td>
                  <td>{r.p10_pts.toFixed(1)}</td>
                  <td>{r.p85_pts.toFixed(1)}</td>
                  <td>{r.ceiling_cvar.toFixed(1)}</td>
                  <td>{r.mean_wins.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="noise-note">
            With fewer than ~1000 simulations, differences of a few percentage points between strategies are within noise.
          </p>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd ~/Code/ffsim/web && npx tsc --noEmit`
Expected: no errors.

---

### Task 13: Frontend — wire up `App.tsx` and `App.css`

**Files:**
- Modify: `web/src/App.tsx` (replace entire contents)
- Modify: `web/src/App.css` (replace entire contents)
- Modify: `web/src/index.css` (clear default Vite styling that conflicts with layout)

- [ ] **Step 1: Replace `web/src/App.tsx` entirely**

```tsx
import { useEffect, useRef, useState } from 'react';
import type { LeagueSettings, LeagueResponse } from './api/types';
import { fetchLeague } from './api/client';
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
};

const DEBOUNCE_MS = 300;

export default function App() {
  const [settings, setSettings] = useState<LeagueSettings>(DEFAULT_SETTINGS);
  const [league, setLeague] = useState<LeagueResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchLeague(settings)
        .then((res) => {
          setLeague(res);
          setError(null);
        })
        .catch((e) => setError(e instanceof Error ? e.message : String(e)));
    }, DEBOUNCE_MS);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [settings]);

  return (
    <div className="app">
      <h1>ffsim</h1>
      <div className="columns">
        <div className="column-left">
          <SettingsPanel settings={settings} onChange={setSettings} />
        </div>
        <div className="column-right">
          {error && <div className="error">Could not reach the API: {error}</div>}
          {!error && !league && <div className="loading">Loading...</div>}
          {league && (
            <>
              <DraftPosition picks={league.picks} hedgeWindow={league.hedge_window} />
              <ScarcityTable rows={league.scarcity} />
              <PlayerBoard players={league.players} />
            </>
          )}
        </div>
      </div>
      <SimulationPanel settings={settings} />
    </div>
  );
}
```

- [ ] **Step 2: Replace `web/src/App.css` entirely**

```css
.app { max-width: 1400px; margin: 0 auto; padding: 24px; text-align: left; }
h1 { margin-top: 0; }
.columns { display: flex; gap: 24px; align-items: flex-start; }
.column-left { flex: 0 0 280px; }
.column-right { flex: 1; display: flex; flex-direction: column; gap: 24px; min-width: 0; }
.panel { background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 16px; color: #1a1a1a; }
.panel h2 { margin-top: 0; font-size: 1.1rem; }
.settings-panel label { display: block; margin-bottom: 12px; font-size: 0.9rem; font-weight: 600; color: #1a1a1a; }
.settings-panel select, .settings-panel input[type="number"] { display: block; width: 100%; margin-top: 4px; padding: 6px; font-weight: normal; }
fieldset { border: 1px solid #ddd; border-radius: 6px; margin-bottom: 12px; }
.lineup-input { display: inline-block; width: 30%; margin-right: 4px; }
.lineup-input input { width: 100%; }
table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid #eee; }
th { cursor: pointer; user-select: none; color: #555; font-weight: 600; }
.alpha-positive { color: #1a7f37; font-weight: 600; }
.alpha-negative { color: #cf222e; font-weight: 600; }
.pick-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.pick-chip { border: 1px solid #ddd; border-radius: 6px; padding: 6px 10px; text-align: center; min-width: 50px; }
.pick-chip-round { font-size: 0.7rem; color: #888; }
.pick-chip-overall { font-size: 1.1rem; font-weight: 700; }
.pick-chip-gap { font-size: 0.7rem; color: #888; }
.stat { margin-bottom: 8px; font-size: 0.95rem; }
.position-filter { margin-bottom: 8px; }
.position-filter button { margin-right: 6px; padding: 4px 10px; border: 1px solid #ddd; background: #fff; color: #1a1a1a; border-radius: 4px; cursor: pointer; }
.position-filter button.active { background: #1a1a1a; color: #fff; border-color: #1a1a1a; }
.strategy-checkboxes { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 12px; }
.strategy-checkboxes label { display: flex; align-items: center; gap: 4px; font-weight: normal; }
.run-row { display: flex; align-items: center; gap: 12px; margin: 12px 0; }
.run-row button { padding: 8px 16px; font-weight: 600; cursor: pointer; }
.run-row button:disabled { opacity: 0.6; cursor: not-allowed; }
.estimate { color: #666; font-size: 0.9rem; }
.error { color: #cf222e; padding: 8px; background: #fff0f0; border-radius: 4px; }
.loading { color: #666; }
.noise-note { font-size: 0.85rem; color: #666; margin-top: 8px; }
```

- [ ] **Step 3: Replace `web/src/index.css` entirely**

```css
body {
  margin: 0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  background: #f5f5f5;
  color: #1a1a1a;
}
```

- [ ] **Step 4: Delete unused default Vite assets**

Run: `cd ~/Code/ffsim/web && rm -f src/assets/react.svg public/vite.svg`

- [ ] **Step 5: Set the page title**

Modify `web/index.html`: change `<title>Vite + React + TS</title>` to `<title>ffsim</title>`.

- [ ] **Step 6: Verify full type-check**

Run: `cd ~/Code/ffsim/web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 7: Verify production build succeeds**

Run: `cd ~/Code/ffsim/web && npm run build`
Expected: `dist/` produced, no errors.

---

### Task 14: Root dev script — `dev.sh`

**Files:**
- Create: `dev.sh` (repo root)

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

cleanup() {
  jobs -p | xargs -r kill 2>/dev/null
}
trap cleanup EXIT INT TERM

source .venv/bin/activate
uvicorn main:app --app-dir api --reload --port 8000 &
(cd web && npm run dev) &
wait
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x ~/Code/ffsim/dev.sh`

- [ ] **Step 3: Verify it starts both processes**

Run: `cd ~/Code/ffsim && ./dev.sh &`
Then: `sleep 3 && curl -sI localhost:8000/docs | head -1 && curl -sI localhost:5173 | head -1`
Expected: two `200 OK` (or `HTTP/1.1 200 OK`) responses.
Then: `kill %1` (kills the `dev.sh` process group via the trap).

---

### Task 15: End-to-end browser verification

Use the Playwright browser tools to drive the real running app — this is the "test the golden path in a browser" step, since type-checks and curl checks so far only prove the wiring, not the UI.

- [ ] **Step 1: Start both processes**

Run: `cd ~/Code/ffsim && ./dev.sh &` and wait ~3s for both to be up.

- [ ] **Step 2: Navigate and confirm initial load**

Open `http://localhost:5173` in the browser tool. Confirm: settings panel on the left with defaults (10 teams, Half PPR, slot 6, bench 6, lineup 1/2/2/1/1, playoff teams 4); right column shows draft position (pick chips starting 6, 15, 26, 35, 46...; hedge window 9), positional scarcity table, and a 150-row player board.

- [ ] **Step 3: Verify the scoring knob visibly moves numbers**

Change the Scoring dropdown to "Full PPR". Confirm the positional scarcity table's WR top VOR rises from ~124.3 to ~153.6, TE from ~106.9 to ~131.6, and QB stays at ~80.3.

- [ ] **Step 4: Verify draft slot re-clamping and pick map**

Set Teams to 8, then check the Draft slot dropdown only offers 1-8. Set Teams back to 10, set Draft slot to 2. Confirm pick chips read 2, 19, 22, 39, 42, ... and hedge window is 1.

- [ ] **Step 5: Verify the player board sorting, filtering, and alpha coloring**

Click the "Alpha" column header — confirm it sorts. Click the "QB" filter button — confirm only QBs show. Confirm positive alpha values render green and negative render red.

- [ ] **Step 6: Run a simulation**

Leave default strategies checked (bpa, balanced, ceiling), set simulation count to 30, click "Run simulation". Confirm a spinner/disabled state shows while running, and a results table appears afterward sorted by Champ % descending, followed by the noise disclaimer text.

- [ ] **Step 7: Verify the error state**

Stop the API process only (`kill` the uvicorn job, leave `npm run dev` running), then change a setting. Confirm the UI shows an explicit "Could not reach the API" error — not stale or placeholder data.

- [ ] **Step 8: Tear down**

Run: `kill %1` (or locate and kill the `dev.sh` process group) to stop both servers.

- [ ] **Step 9: Final commit** (if in a git repo)

```bash
cd ~/Code/ffsim && git add -A && git status
git commit -m "feat: add ffsim web UI (FastAPI backend + Vite/React frontend)"
```

---

## Self-review notes

- **Spec coverage:** every UI element (settings panel controls, draft position chips + gaps + hedge window, scarcity table, sortable/filterable/colored player board, simulation panel with estimate/spinner/noise note), both endpoints, the single dev command, the `.env.example` + `VITE_API_URL` wiring, and all five numbered verification criteria from the spec are each covered by a task above.
- **`effective_starters` import:** flagged explicitly in Task 3 — it's not in `ffsim`'s top-level `__all__`, so `from ffsim.valuation import effective_starters` is required, not `ff.effective_starters`.
- **Frozen dataclasses:** `build_league()` constructs a fresh `League`/`Scoring` per request; nothing is mutated or cached across requests except the pool itself.
- **Tuples:** `flex_eligible` is passed as a literal tuple constant (not user-configurable in this UI); `lineup` is converted from the pydantic model to a plain dict via `.model_dump()` before constructing `League`.
- **Type consistency:** `PlayerRow`, `PositionScarcityRow`, `PickChip`, `StrategyResultRow` field names match exactly between `api/models.py` and `web/src/api/types.ts` (both plain snake_case, since FastAPI serializes pydantic field names as-is).
