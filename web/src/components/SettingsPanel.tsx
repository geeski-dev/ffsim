import type { LeagueSettings, RiskProfile } from '../api/types';

interface Props {
  settings: LeagueSettings;
  onChange: (next: LeagueSettings) => void;
}

const SCORING_OPTIONS: { value: LeagueSettings['scoring']; label: string }[] = [
  { value: 'half_ppr', label: 'Half PPR' },
  { value: 'ppr', label: 'Full PPR' },
  { value: 'standard', label: 'Standard' },
];

const LINEUP_POSITIONS = ['QB', 'RB', 'WR', 'TE', 'FLEX'] as const;

const RISK_PROFILE_OPTIONS: { value: RiskProfile; label: string }[] = [
  { value: 'safe', label: 'Play it safe' },
  { value: 'balanced', label: 'Balanced' },
  { value: 'ceiling', label: 'Chase upside' },
  { value: 'max_ceiling', label: 'Full send' },
];

export default function SettingsPanel({ settings, onChange }: Props) {
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

      <label>
        Risk profile
        <select
          value={settings.risk_profile}
          onChange={(e) => update({ risk_profile: e.target.value as LeagueSettings['risk_profile'] })}
        >
          {RISK_PROFILE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </label>
    </div>
  );
}
