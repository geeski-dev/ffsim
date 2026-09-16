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
        <input type="number" min={1} max={5000} value={nSims} onChange={(e) => setNSims(Number(e.target.value))} />
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
          <div className="table-scroll">
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
          </div>
          <p className="noise-note">
            Differences under a few percentage points are noise below ~1000 sims.
          </p>
        </>
      )}
    </div>
  );
}
