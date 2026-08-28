import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { ModelInfluence, PlayerRow, Variance } from '../api/types';

const POSITIONS = ['All', 'QB', 'RB', 'WR', 'TE'] as const;

export type SortKey = 'name' | 'position' | 'team' | 'adp' | 'expert_rank' | 'expert_rank_lo' | 'our_value' | 'our_range_lo' | 'bargain';
export type SortDirection = 'asc' | 'desc';
export type PositionFilter = (typeof POSITIONS)[number];

export interface BoardState {
  sortKey: SortKey;
  sortDir: SortDirection;
  positionFilter: PositionFilter;
}

interface Props {
  players: PlayerRow[];
  variance: Variance;
  modelInfluence: ModelInfluence;
  boardState: BoardState;
  onBoardStateChange: (next: BoardState) => void;
}

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
    key: 'expert_rank',
    label: 'Expert',
    title: 'Median overall rank across 12+ individual FantasyPros analysts (their own consensus aggregate excluded, so a panel of one voice doesn’t get double-counted).',
  },
  {
    key: 'expert_rank_lo',
    label: 'Expert Range',
    title: 'Where the highest and lowest of 12 analysts have him. A wide range means they don’t agree.',
  },
  {
    key: 'our_value',
    label: 'Our Value',
    title: 'Our own valuation at your current Variance and Model Influence settings — points above a freely-available replacement, blended toward the market by however much influence you’ve given the model.',
  },
  {
    key: 'our_range_lo',
    label: 'Our Range',
    title: 'Our own high and low estimate. Shown so you can judge our confidence the same way you judge theirs.',
  },
  {
    key: 'bargain',
    label: 'Bargain',
    title: 'How much better this player is than his draft price implies, scaled by Model Influence. At Off this reads 0.0 for everyone — we’re asserting nothing, you’re looking at consensus arithmetic. Blank means we don’t have a reliable price for him.',
  },
];

const EM_DASH = '—';

function formatSigned(value: number): string {
  const rounded = value.toFixed(1);
  return value >= 0 ? `+${rounded}` : rounded;
}

function formatRange(lo: number | null, hi: number | null, digits = 1): string {
  if (lo === null || hi === null) return EM_DASH;
  const loStr = lo.toFixed(digits);
  const hiStr = hi.toFixed(digits);
  return loStr === hiStr ? loStr : `${loStr}–${hiStr}`;
}

function sortValue(p: PlayerRow, key: SortKey): string | number | null {
  if (key === 'expert_rank_lo') return p.expert_rank_lo;
  if (key === 'our_range_lo') return p.our_range_lo;
  return p[key as keyof PlayerRow] as string | number | null;
}

const ANIMATE_MS = 420;

export default function PlayerBoard({
  players,
  variance,
  modelInfluence,
  boardState,
  onBoardStateChange,
}: Props) {
  const { sortKey, sortDir, positionFilter } = boardState;
  const [reshuffle, setReshuffle] = useState<{ up: number; down: number; movers: string[] } | null>(null);

  // Settings change the instant a dropdown fires; `players` only updates
  // later, once the debounced fetch resolves. So "did a knob change cause
  // this players update" has to be judged when PLAYERS changes, comparing
  // the knobs in effect now against the knobs recorded the last time players
  // changed -- not when the dropdown fires (that render still holds the OLD
  // players array, which makes any diff computed there vacuously zero).
  // State, not refs, throughout: mutating a ref during render is not safe
  // under StrictMode's double-invoked render pass (the first pass's mutation
  // is visible to the second pass, which then sees no change and silently
  // drops the update) -- mirrors the pre-existing prevRiskProfile pattern in
  // this file, which used state for exactly this reason.
  const [prevPlayers, setPrevPlayers] = useState(players);
  const [knobsAtLastPlayers, setKnobsAtLastPlayers] = useState({ variance, modelInfluence });
  // Lazy initializer -- captures the baseline from the FIRST players array
  // this component ever sees. Without this, the mount render trivially has
  // players === prevPlayers, the block below never runs for it, and the
  // baseline stays null until one change too late (it would then get set
  // FROM the first real change instead of before it, so that change's own
  // diff always comes up empty).
  const [prevCanonicalRank, setPrevCanonicalRank] = useState<Map<string, number> | null>(() =>
    players.length > 0
      ? new Map([...players].sort((a, b) => b.our_value - a.our_value).map((p, i) => [p.player_id, i]))
      : null,
  );
  const shouldAnimate = useRef(false);

  if (players !== prevPlayers) {
    const knobsChangedSincePriorPlayers =
      variance !== knobsAtLastPlayers.variance || modelInfluence !== knobsAtLastPlayers.modelInfluence;

    if (players.length > 0) {
      const canonical = [...players].sort((a, b) => b.our_value - a.our_value);
      const newRank = new Map(canonical.map((p, i) => [p.player_id, i]));

      if (knobsChangedSincePriorPlayers && prevCanonicalRank) {
        let up = 0;
        let down = 0;
        const deltas: { name: string; delta: number }[] = [];
        newRank.forEach((rank, id) => {
          const before = prevCanonicalRank.get(id);
          if (before === undefined) return;
          const delta = before - rank; // positive = moved up (toward rank 0)
          if (delta > 0) up += 1;
          else if (delta < 0) down += 1;
          if (delta !== 0) deltas.push({ name: canonical[rank].name, delta });
        });
        deltas.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta));
        const movers = deltas.slice(0, 3).map((d) => `${d.name} (${d.delta > 0 ? '↑' : '↓'}${Math.abs(d.delta)})`);
        setReshuffle(up || down ? { up, down, movers } : null);
        shouldAnimate.current = true;
      }
      setPrevCanonicalRank(newRank);
    }
    setKnobsAtLastPlayers({ variance, modelInfluence });
    setPrevPlayers(players);
  }

  const rows = useMemo(() => {
    const filtered = positionFilter === 'All' ? players : players.filter((p) => p.position === positionFilter);
    return [...filtered].sort((a, b) => {
      const av = sortValue(a, sortKey);
      const bv = sortValue(b, sortKey);
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      const cmp = typeof av === 'string' ? av.localeCompare(bv as string) : (av as number) - (bv as number);
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [players, positionFilter, sortKey, sortDir]);

  const rowRefs = useRef(new Map<string, HTMLTableRowElement>());
  const prevTops = useRef(new Map<string, number>());
  const reducedMotion = useMemo(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  );

  useLayoutEffect(() => {
    const nextTops = new Map<string, number>();
    rowRefs.current.forEach((el, id) => {
      nextTops.set(id, el.getBoundingClientRect().top);
    });

    if (shouldAnimate.current && !reducedMotion) {
      rowRefs.current.forEach((el, id) => {
        const before = prevTops.current.get(id);
        const after = nextTops.get(id);
        if (before === undefined || after === undefined || before === after) return;
        el.style.transition = 'none';
        el.style.transform = `translateY(${before - after}px)`;
        // eslint-disable-next-line @typescript-eslint/no-unused-expressions
        el.getBoundingClientRect(); // force reflow before releasing the transform
        el.style.transition = `transform ${ANIMATE_MS}ms ease`;
        el.style.transform = '';
      });
    }

    prevTops.current = nextTops;
    shouldAnimate.current = false;
  }, [rows, reducedMotion]);

  function toggleSort(key: SortKey) {
    shouldAnimate.current = false; // manual sort clicks re-order, but aren't "the reshuffle"
    if (key === sortKey) {
      onBoardStateChange({ ...boardState, sortDir: sortDir === 'asc' ? 'desc' : 'asc' });
    } else {
      onBoardStateChange({ ...boardState, sortKey: key, sortDir: 'desc' });
    }
  }

  return (
    <div className="panel">
      <h2>Player board</h2>
      {reshuffle && (
        <div className="reshuffle-banner" role="status">
          <strong>{reshuffle.up}</strong> players moved up, <strong>{reshuffle.down}</strong> moved down.
          {reshuffle.movers.length > 0 && <> Biggest movers: {reshuffle.movers.join(', ')}.</>}
        </div>
      )}
      <div className="position-filter">
        {POSITIONS.map((pos) => (
          <button
            key={pos}
            className={pos === positionFilter ? 'active' : ''}
            onClick={() => onBoardStateChange({ ...boardState, positionFilter: pos })}
          >
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
            {rows.map((p) => (
              <tr
                key={p.player_id}
                ref={(el) => {
                  if (el) rowRefs.current.set(p.player_id, el);
                  else rowRefs.current.delete(p.player_id);
                }}
              >
                <td>{p.name}</td>
                <td>{p.position}</td>
                <td>{p.team}</td>
                <td>{p.adp.toFixed(1)}</td>
                <td className={p.expert_rank === null ? 'bargain-null' : undefined}>
                  {p.expert_rank === null ? EM_DASH : p.expert_rank.toFixed(1)}
                </td>
                <td className={p.expert_rank_lo === null ? 'bargain-null' : undefined}>
                  {formatRange(p.expert_rank_lo, p.expert_rank_hi)}
                </td>
                <td>{p.our_value.toFixed(1)}</td>
                <td>{formatRange(p.our_range_lo, p.our_range_hi)}</td>
                <td className={p.bargain === null ? 'bargain-null' : p.bargain >= 0 ? 'bargain-positive' : 'bargain-negative'}>
                  {p.bargain === null ? EM_DASH : formatSigned(p.bargain)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
