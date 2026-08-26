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
