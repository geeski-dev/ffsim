import type { PickChip } from '../api/types';

interface Props {
  picks: PickChip[];
  hedgeWindow: number;
  rounds: number;
  reservedSlots: number;
  totalRounds: number;
}

export default function DraftPosition({ picks, hedgeWindow, rounds, reservedSlots, totalRounds }: Props) {
  return (
    <div className="panel">
      <h2>Draft position</h2>
      <div className="stat">
        {rounds} skill rounds + {reservedSlots} reserved = {totalRounds} total
      </div>
      <div className="stat">Hedge window: <strong>{hedgeWindow}</strong></div>
      <div className="pick-chips">
        {picks.map((p) => (
          <div key={p.round} className="pick-chip">
            <div className="pick-chip-round">R{p.round}</div>
            <div className="pick-chip-overall">{p.overall_pick}</div>
            {p.gap_to_next !== null && <div className="pick-chip-gap">+{p.gap_to_next}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
