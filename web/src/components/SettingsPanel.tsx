import { useState } from 'react';
import type { LeagueSettings, ModelInfluence, Variance } from '../api/types';
import Tooltip from './Tooltip';

interface Props {
  settings: LeagueSettings;
  onChange: (next: LeagueSettings) => void;
  onReset: () => void;
  draftMode: boolean;
  collapsed: boolean;
  onCollapsedChange: (collapsed: boolean) => void;
}

const SCORING_OPTIONS: { value: LeagueSettings['scoring']; label: string }[] = [
  { value: 'half_ppr', label: 'Half PPR' },
  { value: 'ppr', label: 'Full PPR' },
  { value: 'standard', label: 'Standard' },
];

const LINEUP_POSITIONS = ['QB', 'RB', 'WR', 'TE', 'FLEX'] as const;

const VARIANCE_OPTIONS: { value: Variance; label: string }[] = [
  { value: 'Low', label: 'Low' },
  { value: 'Medium', label: 'Medium' },
  { value: 'High', label: 'High' },
  { value: 'Extreme', label: 'Extreme' },
];

const MODEL_INFLUENCE_OPTIONS: { value: ModelInfluence; label: string }[] = [
  { value: 'Off', label: 'Off (consensus board)' },
  { value: 'Low', label: 'Low' },
  { value: 'Medium', label: 'Medium' },
  { value: 'High', label: 'High' },
  { value: 'Extreme', label: 'Extreme (our board)' },
];

export default function SettingsPanel({ settings, onChange, onReset, draftMode, collapsed, onCollapsedChange }: Props) {
  // Re-locks every time you enter draft mode -- state, not a ref (see
  // PlayerBoard's own comment on why: a ref mutated during render is not
  // safe under StrictMode's double-invoked render pass). Never auto-unlocks
  // itself; only the explicit checkbox below does that, on purpose --
  // "must not fumble a setting at pick 46."
  const [wasDraftMode, setWasDraftMode] = useState(draftMode);
  const [unlocked, setUnlocked] = useState(false);
  if (draftMode !== wasDraftMode) {
    setWasDraftMode(draftMode);
    if (draftMode) setUnlocked(false);
  }
  const knobsLocked = draftMode && !unlocked;

  function update(patch: Partial<LeagueSettings>) {
    const next = { ...settings, ...patch };
    if (next.slot > next.teams) next.slot = next.teams;
    onChange(next);
  }

  function updateLineup(pos: (typeof LINEUP_POSITIONS)[number], value: number) {
    onChange({ ...settings, lineup: { ...settings.lineup, [pos]: value } });
  }

  const teamOptions = Array.from({ length: 7 }, (_, i) => i + 8); // 8..14
  const slotOptions = Array.from({ length: settings.teams }, (_, i) => i + 1);

  return (
    <div className="panel settings-bar">
      <div className="panel-header">
        <h2>Settings</h2>
        <button
          type="button"
          className="collapse-toggle"
          aria-expanded={!collapsed}
          onClick={() => onCollapsedChange(!collapsed)}
        >
          {collapsed ? 'Expand' : 'Collapse'}
        </button>
      </div>

      {/* Row 1: the two knobs -- what the user actually touches, and the
          product's point of difference. They get their own row, on top,
          not buried under roster plumbing. */}
      <div className="settings-row settings-row-knobs">
        <div className="settings-field">
          <label htmlFor="variance-select">Variance</label>
          <Tooltip id="variance" />
          <select
            id="variance-select"
            value={settings.variance}
            disabled={knobsLocked}
            onChange={(e) => update({ variance: e.target.value as LeagueSettings['variance'] })}
          >
            {VARIANCE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        <div className="settings-field">
          <label htmlFor="model-influence-select">Model Influence</label>
          <Tooltip id="model-influence" />
          <select
            id="model-influence-select"
            value={settings.model_influence}
            disabled={knobsLocked}
            onChange={(e) => update({ model_influence: e.target.value as LeagueSettings['model_influence'] })}
          >
            {MODEL_INFLUENCE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        {draftMode && (
          <label className="knob-lock-toggle">
            <input type="checkbox" checked={unlocked} onChange={(e) => setUnlocked(e.target.checked)} />
            Unlock
          </label>
        )}

        <button type="button" className="reset-settings" onClick={onReset}>
          Reset settings
        </button>
      </div>

      {!collapsed && (
        <>
          {settings.model_influence === 'Off' && (
            <p className="settings-note">
              Off shows the consensus board. We aren't asserting we're right — that's the only
              setting whose behavior has actually been measured.
            </p>
          )}

          {/* Rows 2+3 share one wrapping flex container on purpose -- on wide
              viewports they read as a single continuous line, on narrow ones
              they wrap onto as many lines as they need. */}
          <div className="settings-row settings-row-league">
            <div className="settings-field">
              <label htmlFor="teams-select">Teams</label>
              <Tooltip id="teams" />
              <select id="teams-select" value={settings.teams} onChange={(e) => update({ teams: Number(e.target.value) })}>
                {teamOptions.map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>

            <div className="settings-field">
              <label htmlFor="scoring-select">Scoring</label>
              <Tooltip id="scoring" />
              <select
                id="scoring-select"
                value={settings.scoring}
                onChange={(e) => update({ scoring: e.target.value as LeagueSettings['scoring'] })}
              >
                {SCORING_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>

            <div className="settings-field">
              <label htmlFor="slot-select">Draft slot</label>
              <Tooltip id="draft-slot" />
              <select id="slot-select" value={settings.slot} onChange={(e) => update({ slot: Number(e.target.value) })}>
                {slotOptions.map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>

            <div className="settings-field">
              <label htmlFor="playoff-select">Playoff teams</label>
              <Tooltip id="playoff-teams" />
              <select
                id="playoff-select"
                value={settings.playoff_teams}
                onChange={(e) => update({ playoff_teams: Number(e.target.value) })}
              >
                {[2, 4, 6].map((n) => (
                  <option key={n} value={n}>{n}</option>
                ))}
              </select>
            </div>

            <div className="settings-field settings-field-narrow">
              <label htmlFor="bench-input">Bench</label>
              <Tooltip id="bench-size" />
              <input
                id="bench-input"
                type="number"
                min={0}
                value={settings.bench}
                onChange={(e) => update({ bench: Number(e.target.value) })}
              />
            </div>

            <div className="settings-field settings-field-narrow">
              <label htmlFor="reserved-input">K/DST</label>
              <Tooltip id="reserved-slots" />
              <input
                id="reserved-input"
                type="number"
                min={0}
                value={settings.reserved_slots}
                onChange={(e) => update({ reserved_slots: Number(e.target.value) })}
              />
            </div>

            <div className="settings-field lineup-field">
              <label>Lineup</label>
              <Tooltip id="starting-lineup" />
              <div className="lineup-steppers">
                {LINEUP_POSITIONS.map((pos) => (
                  <label key={pos} className="lineup-stepper">
                    <span>{pos}</span>
                    {pos === 'FLEX' && <Tooltip id="flex" />}
                    <input
                      type="number"
                      min={0}
                      value={settings.lineup[pos]}
                      onChange={(e) => updateLineup(pos, Number(e.target.value))}
                    />
                  </label>
                ))}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
