import { useCallback, useEffect, useRef, useState } from 'react';
import type { LeagueSettings, LeagueResponse } from './api/types';
import { fetchLeague } from './api/client';
import logo from './assets/logo.png';
import SettingsPanel from './components/SettingsPanel';
import DraftPosition from './components/DraftPosition';
import ScarcityTable from './components/ScarcityTable';
import PlayerBoard, { type BoardState } from './components/PlayerBoard';
import SimulationPanel from './components/SimulationPanel';
import { readVersionedStorage, writeVersionedStorage } from './storage/versionedStorage';
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
        <img src={logo} alt="Mispricing Engine logo" width={36} height={36} />
        <h1>Mispricing Engine</h1>
      </div>
      <p className="tagline">Find the mispriced players, not the good ones.</p>
      <p className="intro">
        Most draft tools rank players. This one prices them, and shows you both prices side by side.{' '}
        <strong>Expert</strong> is the analyst consensus; <strong>Our Value</strong> is how many points a
        player scores above a freely-available replacement at his position, at whatever Variance and Model
        Influence you've set; <strong>Bargain</strong> is how much cheaper he is than that value deserves.
      </p>
      <div className="columns">
        <div className="column-left">
          <SettingsPanel settings={settings} onChange={handleSettingsChange} onReset={resetSettings} />
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
              <PlayerBoard
                players={league.players}
                variance={settings.variance}
                modelInfluence={settings.model_influence}
                boardState={boardState}
                onBoardStateChange={handleBoardStateChange}
              />
            </>
          )}
        </div>
      </div>
      <SimulationPanel settings={settings} />
    </div>
  );
}
