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
        <img src={logo} alt="Mispricing Engine logo" width={36} height={36} />
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
