import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { LineupSettings, ModelInfluence, PlayerRow, Variance } from '../api/types';
import Tooltip from './Tooltip';
import type { TooltipId } from '../tooltips';

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

const COLUMNS: { key: SortKey; label: string; tooltip?: TooltipId }[] = [
  { key: 'name', label: 'Name' },
  { key: 'position', label: 'Pos' },
  { key: 'team', label: 'Team' },
  { key: 'adp', label: 'ADP', tooltip: 'adp' },
  { key: 'expert_rank', label: 'Expert', tooltip: 'expert' },
  { key: 'expert_rank_lo', label: 'Expert Range', tooltip: 'expert-range' },
  { key: 'our_value', label: 'Value', tooltip: 'our-value' },
  { key: 'our_range_lo', label: 'Value Range', tooltip: 'our-range' },
  { key: 'bargain', label: 'Bargain', tooltip: 'bargain' },
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

function sortValue(p: PlayerRow, key: SortKey, modelInfluence: ModelInfluence): string | number | null {
  if (key === 'expert_rank_lo') return p.expert_rank_lo;
  if (key === 'our_range_lo') return p.our_range_lo;
  // At Off, Bargain displays raw alpha (see the column render below) --
  // sort by what's actually shown, not by the always-0.0 applied bargain.
  if (key === 'bargain' && modelInfluence === 'Off') return p.alpha;
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
  // Counts genuine reshuffle events. Used only as a React `key` on the
  // banner (see render below) so a new event forces a fresh DOM node,
  // which is what (re)starts the CSS flash animation -- no setTimeout/
  // setState-in-an-effect needed to turn the flash off again; the CSS
  // animation (see .reshuffle-banner in App.css) does that on its own.
  const [flashKey, setFlashKey] = useState(0);
  const reducedMotion = useMemo(
    () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    [],
  );

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
        if (up || down) {
          setReshuffle({ up, down, movers });
          setFlashKey((k) => k + 1);
        } else {
          setReshuffle(null);
        }
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
      const av = sortValue(a, sortKey, modelInfluence);
      const bv = sortValue(b, sortKey, modelInfluence);
      if (av === null && bv === null) return 0;
      if (av === null) return 1;
      if (bv === null) return -1;
      const cmp = typeof av === 'string' ? av.localeCompare(bv as string) : (av as number) - (bv as number);
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [players, positionFilter, neededPositions, mode, searchText, sortKey, sortDir, modelInfluence]);

  function markTopMatchGone() {
    const top = rows[0];
    if (!top) return;
    onMarkGone(top.player_id);
    setSearchText('');
    searchInputRef.current?.focus();
  }

  const rowRefs = useRef(new Map<string, HTMLTableRowElement>());
  const prevTops = useRef(new Map<string, number>());

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

  function sortedColumnClass(key: SortKey, extra?: string): string | undefined {
    return [sortKey === key && 'sorted-column', extra].filter(Boolean).join(' ') || undefined;
  }

  return (
    <div className="panel">
      <h2>Player board</h2>
      {reshuffle && (
        <div key={flashKey} className="reshuffle-banner" role="status">
          <span>
            <strong>{reshuffle.up}</strong> players moved up, <strong>{reshuffle.down}</strong> moved down.
            {reshuffle.movers.length > 0 && <> Biggest movers: {reshuffle.movers.join(', ')}.</>}
          </span>
          <Tooltip id="reshuffle-banner" />
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
                <th key={col.key} className={sortedColumnClass(col.key)} onClick={() => toggleSort(col.key)}>
                  {col.label}
                  {col.tooltip && <Tooltip id={col.tooltip} />}
                  {col.key === 'bargain' && modelInfluence === 'Off' && (
                    <span className="inactive-marker"> (not applied)</span>
                  )}
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
                  <td className={sortedColumnClass('name')}>{p.name}</td>
                  <td className={sortedColumnClass('position')}>{p.position}</td>
                  <td className={sortedColumnClass('team')}>{p.team}</td>
                  <td className={sortedColumnClass('adp')}>{p.adp.toFixed(1)}</td>
                  <td className={sortedColumnClass('expert_rank', p.expert_rank === null ? 'bargain-null' : undefined)}>
                    {p.expert_rank === null ? EM_DASH : p.expert_rank.toFixed(1)}
                  </td>
                  <td className={sortedColumnClass('expert_rank_lo', p.expert_rank_lo === null ? 'bargain-null' : undefined)}>
                    {formatRange(p.expert_rank_lo, p.expert_rank_hi)}
                  </td>
                  <td className={sortedColumnClass('our_value')}>{p.our_value.toFixed(1)}</td>
                  <td className={sortedColumnClass('our_range_lo')}>{formatRange(p.our_range_lo, p.our_range_hi)}</td>
                  {modelInfluence === 'Off' ? (
                    <td className={sortedColumnClass('bargain', 'bargain-inactive')}>
                      {p.alpha === null ? EM_DASH : formatSigned(p.alpha)}
                    </td>
                  ) : (
                    <td className={sortedColumnClass('bargain', p.bargain === null ? 'bargain-null' : p.bargain >= 0 ? 'bargain-positive' : 'bargain-negative')}>
                      {p.bargain === null ? EM_DASH : formatSigned(p.bargain)}
                    </td>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
