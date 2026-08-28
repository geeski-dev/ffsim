import type { LeagueSettings, ModelInfluence, Variance } from '../api/types';

interface Props {
  settings: LeagueSettings;
  onChange: (next: LeagueSettings) => void;
  onReset: () => void;
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

export default function SettingsPanel({ settings, onChange, onReset }: Props) {
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
    <div className="panel settings-panel">
      <h2>League settings</h2>

      <label>
        Teams
        <select value={settings.teams} onChange={(e) => update({ teams: Number(e.target.value) })}>
          {teamOptions.map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </label>

      <label>
        Scoring
        <select
          value={settings.scoring}
          onChange={(e) => update({ scoring: e.target.value as LeagueSettings['scoring'] })}
        >
          {SCORING_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </label>

      <label>
        Draft slot
        <select value={settings.slot} onChange={(e) => update({ slot: Number(e.target.value) })}>
          {slotOptions.map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </label>

      <label>
        Bench size
        <input
          type="number"
          min={0}
          value={settings.bench}
          onChange={(e) => update({ bench: Number(e.target.value) })}
        />
      </label>

      <fieldset>
        <legend>Starting lineup</legend>
        {LINEUP_POSITIONS.map((pos) => (
          <label key={pos} className="lineup-input">
            {pos}
            <input
              type="number"
              min={0}
              value={settings.lineup[pos]}
              onChange={(e) => updateLineup(pos, Number(e.target.value))}
            />
          </label>
        ))}
      </fieldset>

      <label>
        Playoff teams
        <select
          value={settings.playoff_teams}
          onChange={(e) => update({ playoff_teams: Number(e.target.value) })}
        >
          {[2, 4, 6].map((n) => (
            <option key={n} value={n}>{n}</option>
          ))}
        </select>
      </label>

      <label>
        Reserved slots (K/DST)
        <input
          type="number"
          min={0}
          value={settings.reserved_slots}
          onChange={(e) => update({ reserved_slots: Number(e.target.value) })}
        />
      </label>

      <label title="How much ceiling to chase in our own valuation, and how hard we penalize a steep floor collapse. Independent of Model Influence below — this shapes OUR number, not how much of it you see.">
        Variance
        <select
          value={settings.variance}
          onChange={(e) => update({ variance: e.target.value as LeagueSettings['variance'] })}
        >
          {VARIANCE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </label>

      <label title="How much of our own valuation to act on. At Off you're looking at the consensus board — the market's ordering, arranged for your league's roster and scoring.">
        Model Influence
        <select
          value={settings.model_influence}
          onChange={(e) => update({ model_influence: e.target.value as LeagueSettings['model_influence'] })}
        >
          {MODEL_INFLUENCE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </label>
      {settings.model_influence === 'Off' && (
        <p className="settings-note">
          Off shows the consensus board. We aren't asserting we're right — that's the only
          setting whose behavior has actually been measured.
        </p>
      )}

      <button type="button" className="reset-settings" onClick={onReset}>
        Reset settings
      </button>
    </div>
  );
}
