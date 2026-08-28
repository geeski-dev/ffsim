import type { PickChip } from '../api/types';
import Tooltip from './Tooltip';

interface Props {
  picks: PickChip[];
  hedgeWindow: number;
  rounds: number;
  reservedSlots: number;
  totalRounds: number;
  // Both optional: outside draft mode the chips stay the plain static
  // display they've always been. Provided, a chip click previews
  // availability at that pick in the next-pick panel -- "who can I
  // actually get in round 5", not just "what pick do I have."
  selectedPick?: number | null;
  onSelectPick?: (pick: number) => void;
}

export default function DraftPosition({
  picks, hedgeWindow, rounds, reservedSlots, totalRounds, selectedPick, onSelectPick,
}: Props) {
  return (
    <div className="panel">
      <h2>Draft position <Tooltip id="draft-position" /></h2>
      <div className="stat">
        {rounds} skill rounds + {reservedSlots} reserved = {totalRounds} total
      </div>
      <div className="stat">Hedge window: <strong>{hedgeWindow}</strong> <Tooltip id="hedge-window" /></div>
      <div className="pick-chips">
        {picks.map((p) => {
          const isSelected = selectedPick === p.overall_pick;
          return (
            <button
              key={p.round}
              type="button"
              disabled={!onSelectPick}
              className={`pick-chip${isSelected ? ' selected' : ''}${onSelectPick ? ' pick-chip-clickable' : ''}`}
              onClick={onSelectPick ? () => onSelectPick(p.overall_pick) : undefined}
              title={onSelectPick ? `Preview who's available at pick ${p.overall_pick}` : undefined}
            >
              <div className="pick-chip-round">R{p.round}</div>
              <div className="pick-chip-overall">{p.overall_pick}</div>
              {p.gap_to_next !== null && <div className="pick-chip-gap">+{p.gap_to_next}</div>}
            </button>
          );
        })}
      </div>
    </div>
  );
}
