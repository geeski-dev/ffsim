import { useEffect, useRef, useState } from 'react';
import type { LeagueSettings, NextPickResponse } from '../api/types';
import { fetchNextPick } from '../api/client';
import Tooltip from './Tooltip';

interface Props {
  settings: LeagueSettings;
  gone: string[];
  mine: string[];
  currentPick: number;
  // Not hardcoded to "my next pick" -- a parameter with my next pick as the
  // default (null), controlled from App so a click on a round chip in
  // DraftPosition can set it directly. Same endpoint, same component --
  // the chip click and the manual "Preview pick" input both just set this.
  targetPick: number | null;
  onTargetPickChange: (pick: number | null) => void;
}

const DEBOUNCE_MS = 200;

export default function NextPickPanel({ settings, gone, mine, currentPick, targetPick, onTargetPickChange }: Props) {
  const [resp, setResp] = useState<NextPickResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const requestIdRef = useRef(0);

  const lineupSlots = settings.lineup.QB + settings.lineup.RB + settings.lineup.WR + settings.lineup.TE + settings.lineup.FLEX;
  const maxPreviewPick = settings.teams * (lineupSlots + settings.bench + settings.reserved_slots);
  const minPreviewPick = Math.min(currentPick + 1, maxPreviewPick);
  const parsedOverride = targetPick === null || !Number.isFinite(targetPick)
    ? undefined
    : Math.min(maxPreviewPick, Math.max(minPreviewPick, targetPick));

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const requestId = ++requestIdRef.current;
      fetchNextPick({
        ...settings,
        gone,
        mine,
        current_pick: currentPick,
        target_pick: parsedOverride,
      })
        .then((res) => {
          if (requestIdRef.current !== requestId) return;
          setResp(res);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings, gone, mine, currentPick, parsedOverride]);

  return (
    <div className="panel">
      <h2>Next pick</h2>
      {error && <div className="error">Could not reach the API: {error}</div>}
      {!error && !resp && <div className="loading"><span className="spinner" />Loading...</div>}
      {!error && resp && (
        <>
          <div className="next-pick-header">
            {resp.next_pick !== null ? (
              <span>
                Pick <strong>{resp.current_pick}</strong> → your next is{' '}
                <strong>{resp.next_pick}</strong> ({resp.picks_away} away)
              </span>
            ) : (
              <span>No more picks left for you this draft.</span>
            )}
            <span className="hedge-window-note">Hedge window: {resp.hedge_window}</span>
          </div>

          <label className="preview-pick-input" title="Preview availability at a different pick than your own next one -- or click a round chip above.">
            Preview pick
            <input
              type="number"
              min={minPreviewPick}
              max={maxPreviewPick}
              placeholder={resp.next_pick !== null ? String(resp.next_pick) : '—'}
              value={targetPick === null ? '' : String(targetPick)}
              onChange={(e) => onTargetPickChange(e.target.value.trim() === '' ? null : Number(e.target.value))}
              onBlur={() => {
                if (targetPick !== null && parsedOverride !== undefined && targetPick !== parsedOverride) {
                  onTargetPickChange(parsedOverride);
                }
              }}
            />
            {targetPick !== null && (
              <button type="button" onClick={() => onTargetPickChange(null)}>
                Reset to my next pick
              </button>
            )}
          </label>

          {resp.target_pick !== null && resp.target_pick !== resp.next_pick && (
            <p className="settings-note">Showing availability at pick {resp.target_pick}.</p>
          )}

          <div className="next-pick-columns">
            <div>
              <h3 className="take-now-heading">Take now</h3>
              <p className="next-pick-subhead">He will not be there.</p>
              <NextPickTable rows={resp.take_now} />
            </div>
            <div>
              <h3 className="can-wait-heading">Can wait</h3>
              <p className="next-pick-subhead">Take someone else first.</p>
              <NextPickTable rows={resp.can_wait} />
            </div>
          </div>

          {resp.tier_depletion.length > 0 && (
            <div className="tier-depletion">
              <h3>Tier depletion <Tooltip id="tier" /></h3>
              <ul>
                {resp.tier_depletion.map((t) => (
                  <li key={t.position}>
                    {t.position} tier {t.tier}: <strong>{t.remaining}</strong> left
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function NextPickTable({ rows }: { rows: NextPickResponse['take_now'] }) {
  if (rows.length === 0) return <p className="next-pick-empty">—</p>;
  return (
    <table className="next-pick-table">
      <thead>
        <tr>
          <th>Player</th>
          <th>Value</th>
          <th>P(available)</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.player_id}>
            <td>{r.name} <span className="next-pick-pos">{r.position}</span></td>
            <td>{r.our_value.toFixed(1)}</td>
            <td>{(r.availability * 100).toFixed(0)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
