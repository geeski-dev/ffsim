import { useCallback, useEffect, useRef, useState } from 'react';
import type { LeagueSettings, LeagueResponse } from './api/types';
import { fetchLeague } from './api/client';
import logo from './assets/logo.png';
import SettingsPanel from './components/SettingsPanel';
import DraftPosition from './components/DraftPosition';
import ScarcityTable from './components/ScarcityTable';
import PlayerBoard, { type BoardState } from './components/PlayerBoard';
import NextPickPanel from './components/NextPickPanel';
import SimulationPanel from './components/SimulationPanel';
import AboutPage from './components/AboutPage';
import { readVersionedStorage, writeVersionedStorage } from './storage/versionedStorage';
import { useDraftState } from './hooks/useDraftState';
import './App.css';

const DEFAULT_SETTINGS: LeagueSettings = {
  teams: 10,
  slot: 6,
  scoring: 'half_ppr',
  bench: 6,
  lineup: { QB: 1, RB: 2, WR: 2, TE: 1, FLEX: 1 },
  playoff_teams: 4,
  reserved_slots: 2,
  variance: 'Medium',
  model_influence: 'Off',
};

const DEFAULT_BOARD_STATE: BoardState = {
  sortKey: 'our_value',
  sortDir: 'desc',
  positionFilter: 'All',
};

type AppMode = 'board' | 'draft';

interface PersistedAppState {
  settings: LeagueSettings;
  boardState: BoardState;
  mode: AppMode;
}

const STORAGE_KEY = 'ffsim.appState';
const STORAGE_VERSION = 1;
const DEFAULT_PERSISTED_STATE: PersistedAppState = {
  settings: DEFAULT_SETTINGS,
  boardState: DEFAULT_BOARD_STATE,
  mode: 'board',
};

const DEBOUNCE_MS = 300;

export default function App() {
  const [initialState] = useState<PersistedAppState>(() =>
    readVersionedStorage(STORAGE_KEY, STORAGE_VERSION, DEFAULT_PERSISTED_STATE),
  );
  const [settings, setSettings] = useState<LeagueSettings>(initialState.settings);
  const [boardState, setBoardState] = useState<BoardState>(initialState.boardState);
  const [mode, setMode] = useState<AppMode>(initialState.mode);
  const [league, setLeague] = useState<LeagueResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestIdRef = useRef(0);
  const draft = useDraftState();
  // No client-side router: /about is a real, separate page served by
  // Vite's own SPA fallback (and would need the same at a static host in
  // production). window.location.pathname only changes via an actual
  // navigation, which remounts the whole app anyway, so reading it once
  // here is sufficient -- no state, no popstate listener needed.
  const isAboutPage = window.location.pathname.replace(/\/+$/, '') === '/about';
  // Lifted out of NextPickPanel so a click on a round chip in DraftPosition
  // can set it directly -- same endpoint, same panel, just a different
  // target_pick (see the design note this was built against: "not
  // hardcoded... the user's next pick as the default").
  const [targetPick, setTargetPick] = useState<number | null>(null);
  const nextPickPanelRef = useRef<HTMLDivElement>(null);

  function selectPick(pick: number) {
    setTargetPick(pick);
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    nextPickPanelRef.current?.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
  }

  useEffect(() => {
    writeVersionedStorage(STORAGE_KEY, STORAGE_VERSION, { settings, boardState, mode });
  }, [boardState, mode, settings]);

  const handleBoardStateChange = useCallback((next: BoardState) => {
    setBoardState(next);
  }, []);

  function handleSettingsChange(next: LeagueSettings) {
    if (next.variance !== settings.variance || next.model_influence !== settings.model_influence) {
      setBoardState((current) => ({ ...current, sortKey: 'our_value', sortDir: 'desc' }));
    }
    setSettings(next);
  }

  function resetSettings() {
    setSettings(DEFAULT_SETTINGS);
    setBoardState(DEFAULT_BOARD_STATE);
    setMode('board');
  }

  // Separate from resetSettings on purpose, and lives in a different place
  // in the UI -- merging them is how someone tidying their settings at pick
  // 90 loses ninety picks.
  function resetDraft() {
    if (window.confirm('Reset the draft? This clears every pick you’ve marked. Settings are not affected.')) {
      draft.resetDraft();
    }
  }

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

  if (isAboutPage) {
    return (
      <div className="app">
        <div className="app-header">
          <img src={logo} alt="Mispricing Engine" width={1983} height={793} />
        </div>
        <AboutPage />
      </div>
    );
  }

  return (
    <div className="app">
      <div className="app-header">
        <img src={logo} alt="Mispricing Engine" width={1983} height={793} />
        <div className="mode-toggle">
          <button type="button" className={mode === 'board' ? 'active' : ''} onClick={() => setMode('board')}>
            Board
          </button>
          <button type="button" className={mode === 'draft' ? 'active' : ''} onClick={() => setMode('draft')}>
            Draft
          </button>
        </div>
        <a href="/about" className="about-link">About</a>
      </div>
      <p className="tagline">
        Find the <strong className="tagline-chase">mispriced</strong> players, not the{' '}
        <strong className="tagline-resist">good</strong> ones.
      </p>
      <p className="intro">
        Most draft tools rank players. This one prices them, and shows you both prices side by side.{' '}
        <strong>Expert</strong> is the analyst consensus; <strong>Our Value</strong> is how many points a
        player scores above a freely-available replacement at his position, at whatever Variance and Model
        Influence you've set; <strong>Bargain</strong> is how much cheaper he is than that value deserves.
      </p>
      <SettingsPanel
        settings={settings}
        onChange={handleSettingsChange}
        onReset={resetSettings}
        draftMode={mode === 'draft'}
      />
      {mode === 'draft' && (
        <div className="panel draft-status-bar">
          <span className="stat">Overall pick <strong>{draft.draftPosition}</strong></span>
          <span className="stat">{draft.mineSet.size} mine · {draft.goneSet.size} gone</span>
          <button type="button" className="reset-draft" onClick={resetDraft}>
            Reset draft
          </button>
        </div>
      )}
      <div className="board-area">
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
              selectedPick={mode === 'draft' ? targetPick : undefined}
              onSelectPick={mode === 'draft' ? selectPick : undefined}
            />
            <ScarcityTable rows={league.scarcity} />
            {mode === 'draft' && (
              <div ref={nextPickPanelRef}>
                <NextPickPanel
                  settings={settings}
                  gone={draft.gone}
                  mine={draft.mine}
                  currentPick={draft.draftPosition}
                  targetPick={targetPick}
                  onTargetPickChange={setTargetPick}
                />
              </div>
            )}
            <PlayerBoard
              players={league.players}
              variance={settings.variance}
              modelInfluence={settings.model_influence}
              boardState={boardState}
              onBoardStateChange={handleBoardStateChange}
              mode={mode}
              lineup={settings.lineup}
              goneSet={draft.goneSet}
              mineSet={draft.mineSet}
              onMarkGone={draft.markGone}
              onMarkMine={draft.markMine}
              onUndo={draft.undo}
              canUndo={draft.canUndo}
            />
          </>
        )}
      </div>
      <SimulationPanel settings={settings} />
    </div>
  );
}
