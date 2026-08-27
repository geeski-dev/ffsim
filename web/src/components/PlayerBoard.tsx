import { useMemo, useState } from 'react';
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
  // otherwise it looks like the control only affects the simulator. Adjusted
  // during render (not an Effect) so it lands in the same commit as the prop
  // change instead of triggering an extra render.
  const [prevRiskProfile, setPrevRiskProfile] = useState(riskProfile);
  if (riskProfile !== prevRiskProfile) {
    setPrevRiskProfile(riskProfile);
    setSortKey('draft_score');
    setSortDir('desc');
  }

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
