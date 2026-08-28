import { useCallback, useEffect, useRef, useState } from 'react';
import type { LeagueSettings, LeagueResponse } from './api/types';
import { fetchLeague } from './api/client';
import Banner from './components/Banner';
import SettingsPanel from './components/SettingsPanel';
import DraftPosition from './components/DraftPosition';
import ScarcityTable from './components/ScarcityTable';
import PlayerBoard, { type BoardState } from './components/PlayerBoard';
import NextPickPanel from './components/NextPickPanel';
import SimulationPanel from './components/SimulationPanel';
import AboutPage from './components/AboutPage';
import { readVersionedStorage, writeVersionedStorage } from './storage/versionedStorage';
import { useDraftState } from './hooks/useDraftState';
import { AboutNavigationContext } from './aboutNavigation';
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

type AppMode = 'board' | 'draft' | 'simulate' | 'about';
type PersistedMode = Exclude<AppMode, 'about'>;

interface PersistedAppState {
  settings: LeagueSettings;
  boardState: BoardState;
  mode: PersistedMode;
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
  const [initialMode] = useState<AppMode>(() => {
    const path = window.location.pathname.replace(/\/+$/, '');
    if (path === '/about') return 'about';
    return ['board', 'draft', 'simulate'].includes(initialState.mode) ? initialState.mode : 'board';
  });
  const [settings, setSettings] = useState<LeagueSettings>(initialState.settings);
  const [boardState, setBoardState] = useState<BoardState>(initialState.boardState);
  const [mode, setMode] = useState<AppMode>(initialMode);
  const [pendingAboutAnchor, setPendingAboutAnchor] = useState<string | null>(() =>
    initialMode === 'about' ? window.location.hash.slice(1) || null : null,
  );
  const [league, setLeague] = useState<LeagueResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [settingsCollapsed, setSettingsCollapsed] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestIdRef = useRef(0);
  const draft = useDraftState();
  const previousModeRef = useRef<AppMode>(initialMode);
  // Lifted out of NextPickPanel so a click on a round chip in DraftPosition
  // can set it directly -- same endpoint, same panel, just a different
  // target_pick (see the design note this was built against: "not
  // hardcoded... the user's next pick as the default").
  const [targetPick, setTargetPick] = useState<number | null>(null);
  const boardAreaRef = useRef<HTMLDivElement>(null);
  const nextPickPanelRef = useRef<HTMLDivElement>(null);

  function selectPick(pick: number) {
    setTargetPick(pick);
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    nextPickPanelRef.current?.scrollIntoView({ behavior: reducedMotion ? 'auto' : 'smooth', block: 'start' });
  }

  useEffect(() => {
    const persistedMode: PersistedMode = mode === 'about' ? 'board' : mode;
    writeVersionedStorage(STORAGE_KEY, STORAGE_VERSION, { settings, boardState, mode: persistedMode });
  }, [boardState, mode, settings]);

  useEffect(() => {
    const wasAbout = previousModeRef.current === 'about';
    if (mode === 'about') {
      const anchor = pendingAboutAnchor ?? window.location.hash.slice(1);
      if (anchor) {
        const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        document.getElementById(anchor)?.scrollIntoView({
          behavior: reducedMotion ? 'auto' : 'smooth',
          block: 'start',
        });
      } else if (!wasAbout) {
        window.scrollTo({ top: 0, behavior: 'auto' });
      }
      setPendingAboutAnchor(null);
    } else if (wasAbout) {
      window.scrollTo({ top: 0, behavior: 'auto' });
    }
    previousModeRef.current = mode;
  }, [mode, pendingAboutAnchor]);

  const navigateToAbout = useCallback((anchor?: string) => {
    setPendingAboutAnchor(anchor ?? null);
    setMode('about');
  }, []);

  useEffect(() => {
    if (mode === 'about') return;
    function collapseAfterBoardScroll() {
      const boardTop = boardAreaRef.current?.getBoundingClientRect().top;
      if (boardTop !== undefined && boardTop < window.innerHeight * 0.35) {
        setSettingsCollapsed(true);
      }
    }
    window.addEventListener('scroll', collapseAfterBoardScroll, { passive: true });
    return () => window.removeEventListener('scroll', collapseAfterBoardScroll);
  }, [mode]);

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
    setSettingsCollapsed(false);
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

  return (
    <AboutNavigationContext.Provider value={{ navigateToAbout }}>
      <div className="root">
        <Banner collapsed={mode === 'draft'} />
        <div className="app">
          {mode !== 'about' && (
            <p className="tagline">
              Find the <strong className="tagline-chase">mispriced</strong> players, not the{' '}
              <strong className="tagline-resist">good</strong> ones.
            </p>
          )}

          <nav className="nav-tabs" aria-label="Primary">
            <button type="button" className={mode === 'board' ? 'active' : ''} onClick={() => setMode('board')}>
              Board
            </button>
            <button type="button" className={mode === 'draft' ? 'active' : ''} onClick={() => setMode('draft')}>
              Draft
            </button>
            <button type="button" className={mode === 'simulate' ? 'active' : ''} onClick={() => setMode('simulate')}>
              Simulate
            </button>
            <button type="button" className={mode === 'about' ? 'active' : ''} onClick={() => navigateToAbout()}>
              About
            </button>
          </nav>

        {mode !== 'about' && (
          <>
            <SettingsPanel
              settings={settings}
              onChange={handleSettingsChange}
              onReset={resetSettings}
              draftMode={mode === 'draft'}
              collapsed={settingsCollapsed}
              onCollapsedChange={setSettingsCollapsed}
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
          </>
        )}

        <div className="board-area" ref={boardAreaRef}>
          {mode === 'about' && (
            <div className="panel">
              <AboutPage />
            </div>
          )}
          {mode === 'simulate' && <SimulationPanel settings={settings} />}
          {(mode === 'board' || mode === 'draft') && (
            <>
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
            </>
          )}
          </div>
        </div>
      </div>
    </AboutNavigationContext.Provider>
  );
}
