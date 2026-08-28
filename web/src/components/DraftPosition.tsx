import { useState } from 'react';
import type { PickChip } from '../api/types';
import Tooltip from './Tooltip';
import CollapseChevron from './CollapseChevron';

interface Props {
  picks: PickChip[];
  hedgeWindow: number;
  // Both optional: outside draft mode the chips stay the plain static
  // display they've always been. Provided, a chip click previews
  // availability at that pick in the next-pick panel -- "who can I
  // actually get in round 5", not just "what pick do I have."
  selectedPick?: number | null;
  onSelectPick?: (pick: number) => void;
}

export default function DraftPosition({
  picks, hedgeWindow, selectedPick, onSelectPick,
}: Props) {
  const [collapsed, setCollapsed] = useState(true);

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Draft position <Tooltip id="draft-position" /></h2>
        <button
          type="button"
          className="collapse-toggle"
          aria-expanded={!collapsed}
          aria-label={collapsed ? 'Expand draft position' : 'Collapse draft position'}
          onClick={() => setCollapsed(!collapsed)}
        >
          <CollapseChevron collapsed={collapsed} />
        </button>
      </div>
      {!collapsed && (
        <>
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
        </>
      )}
    </div>
  );
}
