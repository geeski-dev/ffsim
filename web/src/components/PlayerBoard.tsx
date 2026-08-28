import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { LineupSettings, ModelInfluence, PlayerRow, Variance } from '../api/types';

const BOARD_POSITIONS = ['All', 'QB', 'RB', 'WR', 'TE'] as const;
// Draft mode collapses the filter to a couple of presets on purpose -- fewer
// decisions during a live draft, not more. "Needed" is computed from mine +
// the league's own lineup requirements (see neededPositions below).
const DRAFT_POSITIONS = ['All', 'Needed'] as const;

export type SortKey = 'name' | 'position' | 'team' | 'adp' | 'expert_rank' | 'expert_rank_lo' | 'our_value' | 'our_range_lo' | 'bargain';
export type SortDirection = 'asc' | 'desc';
export type PositionFilter = (typeof BOARD_POSITIONS)[number] | (typeof DRAFT_POSITIONS)[number];

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
  mode: 'board' | 'draft';
  lineup: LineupSettings;
  goneSet: Set<string>;
  mineSet: Set<string>;
  onMarkGone: (playerId: string) => void;
  onMarkMine: (playerId: string) => void;
  onUndo: () => void;
  canUndo: boolean;
}

const FLEX_ELIGIBLE = ['RB', 'WR', 'TE'] as const;

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
  mode,
  lineup,
  goneSet,
  mineSet,
  onMarkGone,
  onMarkMine,
  onUndo,
  canUndo,
}: Props) {
  const { sortKey, sortDir, positionFilter } = boardState;
  const [reshuffle, setReshuffle] = useState<{ up: number; down: number; movers: string[] } | null>(null);

  // Entry speed is the whole design constraint here: search stays focused,
  // typing filters instantly, Enter marks the top (best-ranked) match gone
  // and hands focus straight back for the next name. Not persisted -- it's
  // a transient per-session typing buffer, not draft state.
  const [searchText, setSearchText] = useState('');
  const searchInputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (mode === 'draft') searchInputRef.current?.focus();
  }, [mode]);

  const neededPositions = useMemo(() => {
    const counts: Partial<Record<string, number>> = {};
    for (const p of players) {
      if (mineSet.has(p.player_id)) counts[p.position] = (counts[p.position] ?? 0) + 1;
    }
    const needed = new Set<string>();
    for (const pos of ['QB', 'RB', 'WR', 'TE'] as const) {
      if ((counts[pos] ?? 0) < (lineup[pos] ?? 0)) needed.add(pos);
    }
    const flexFilled = FLEX_ELIGIBLE.reduce((sum, pos) => sum + Math.max(0, (counts[pos] ?? 0) - (lineup[pos] ?? 0)), 0);
    if (flexFilled < (lineup.FLEX ?? 0)) FLEX_ELIGIBLE.forEach((pos) => needed.add(pos));
    return needed;
  }, [players, mineSet, lineup]);

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
    let filtered = players;
    if (positionFilter === 'Needed') {
      filtered = filtered.filter((p) => neededPositions.has(p.position));
    } else if (positionFilter !== 'All') {
      filtered = filtered.filter((p) => p.position === positionFilter);
    }
    if (mode === 'draft' && searchText.trim()) {
      const needle = searchText.trim().toLowerCase();
      filtered = filtered.filter((p) => p.name.toLowerCase().includes(needle));
    }
    return [...filtered].sort((a, b) => {
      const av = sortValue(a, sortKey);
      const bv = sortValue(b, sortKey);
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      const cmp = typeof av === 'string' ? av.localeCompare(bv as string) : (av as number) - (bv as number);
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [players, positionFilter, neededPositions, mode, searchText, sortKey, sortDir]);

  function markTopMatchGone() {
    const top = rows[0];
    if (!top) return;
    onMarkGone(top.player_id);
    setSearchText('');
    searchInputRef.current?.focus();
  }

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
      {mode === 'draft' && (
        <div className="draft-toolbar">
          <input
            ref={searchInputRef}
            type="text"
            className="draft-search"
            placeholder="Type a name, Enter marks the top match gone…"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                markTopMatchGone();
              } else if (e.key === 'Backspace' && searchText === '') {
                e.preventDefault();
                onUndo();
              }
            }}
          />
          <button type="button" className="undo-button" disabled={!canUndo} onClick={onUndo} title="Backspace on an empty search box does the same thing">
            Undo
          </button>
        </div>
      )}
      <div className="position-filter">
        {(mode === 'draft' ? DRAFT_POSITIONS : BOARD_POSITIONS).map((pos) => (
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
        <table className={mode === 'draft' ? 'draft-mode' : undefined}>
          <thead>
            <tr>
              {mode === 'draft' && <th className="mark-col">Mark</th>}
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
              const isGone = goneSet.has(p.player_id);
              const isMine = mineSet.has(p.player_id);
              const rowClass = mode === 'draft' ? (isMine ? 'row-mine' : isGone ? 'row-gone' : undefined) : undefined;
              return (
                <tr
                  key={p.player_id}
                  className={rowClass}
                  onClick={mode === 'draft' && !isGone ? () => onMarkGone(p.player_id) : undefined}
                  ref={(el) => {
                    if (el) rowRefs.current.set(p.player_id, el);
                    else rowRefs.current.delete(p.player_id);
                  }}
                >
                  {mode === 'draft' && (
                    <td className="mark-col">
                      {!isGone && (
                        <button
                          type="button"
                          className="mine-button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onMarkMine(p.player_id);
                          }}
                        >
                          Mine
                        </button>
                      )}
                    </td>
                  )}
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
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
