export interface LineupSettings {
  QB: number;
  RB: number;
  WR: number;
  TE: number;
  FLEX: number;
}

export type ScoringMode = 'half_ppr' | 'ppr' | 'standard';

export type RiskProfile = 'safe' | 'balanced' | 'ceiling' | 'max_ceiling';

export interface LeagueSettings {
  teams: number;
  slot: number;
  scoring: ScoringMode;
  bench: number;
  lineup: LineupSettings;
  playoff_teams: number;
  reserved_slots: number;
  risk_profile: RiskProfile;
}

export interface PickChip {
  round: number;
  overall_pick: number;
  gap_to_next: number | null;
}

export interface PositionScarcityRow {
  position: string;
  effective_starters: number;
  replacement_points: number;
  top_vor: number;
}

export interface PlayerRow {
  player_id: string;
  name: string;
  position: string;
  team: string;
  adp: number;
  vor: number;
  alpha: number | null;
  tier: number;
  weekly_cv: number;
  draft_score: number;
}

export interface LeagueResponse {
  pick_numbers: number[];
  hedge_window: number;
  rounds: number;
  reserved_slots: number;
  total_rounds: number;
  describe: string;
  scarcity: PositionScarcityRow[];
  players: PlayerRow[];
  picks: PickChip[];
}

export interface SimulateRequest extends LeagueSettings {
  strategies: string[];
  n_sims: number;
}

export interface StrategyResultRow {
  strategy: string;
  champ_pct: number;
  playoff_pct: number;
  mean_pts: number;
  p10_pts: number;
  p85_pts: number;
  ceiling_cvar: number;
  mean_wins: number;
}

export interface SimulateResponse {
  results: StrategyResultRow[];
}
