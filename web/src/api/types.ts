export interface LineupSettings {
  QB: number;
  RB: number;
  WR: number;
  TE: number;
  FLEX: number;
}

export type ScoringMode = 'half_ppr' | 'ppr' | 'standard';

export type Variance = 'Low' | 'Medium' | 'High' | 'Extreme';
export type ModelInfluence = 'Off' | 'Low' | 'Medium' | 'High' | 'Extreme';

export interface LeagueSettings {
  teams: number;
  slot: number;
  scoring: ScoringMode;
  bench: number;
  lineup: LineupSettings;
  playoff_teams: number;
  reserved_slots: number;
  variance: Variance;
  model_influence: ModelInfluence;
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
  expert_rank: number | null;
  expert_rank_lo: number | null;
  expert_rank_hi: number | null;
  our_value: number;
  our_range_lo: number;
  our_range_hi: number;
  bargain: number | null;
  alpha: number | null;
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

export interface NextPickRequest extends LeagueSettings {
  gone: string[];
  mine: string[];
  current_pick: number;
  // Which overall pick to preview availability for. Omit for "my own next
  // pick" (the default the header names); a future round-chip click passes
  // an explicit overall pick here instead -- same request shape, same panel.
  target_pick?: number;
}

export interface NextPickPlayerRow {
  player_id: string;
  name: string;
  position: string;
  team: string;
  our_value: number;
  availability: number;
}

export interface TierDepletionRow {
  position: string;
  tier: number;
  remaining: number;
}

export interface NextPickResponse {
  current_pick: number;
  next_pick: number | null;
  picks_away: number | null;
  target_pick: number | null;
  hedge_window: number;
  take_now: NextPickPlayerRow[];
  can_wait: NextPickPlayerRow[];
  tier_depletion: TierDepletionRow[];
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
