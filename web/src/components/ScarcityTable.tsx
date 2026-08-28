import { useState } from 'react';
import type { PositionScarcityRow } from '../api/types';
import Tooltip from './Tooltip';

interface Props {
  rows: PositionScarcityRow[];
}

export default function ScarcityTable({ rows }: Props) {
  const [collapsed, setCollapsed] = useState(true);

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Positional scarcity <Tooltip id="positional-scarcity" /></h2>
        <button
          type="button"
          className="collapse-toggle"
          aria-expanded={!collapsed}
          aria-label={collapsed ? 'Expand positional scarcity' : 'Collapse positional scarcity'}
          onClick={() => setCollapsed(!collapsed)}
        >
          <span aria-hidden="true">{collapsed ? 'v' : '^'}</span>
        </button>
      </div>
      {!collapsed && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Position</th>
                <th>Effective starters <Tooltip id="effective-starters" /></th>
                <th>Replacement pts <Tooltip id="replacement-pts" /></th>
                <th>Top VOR <Tooltip id="top-vor" /></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.position}>
                  <td>{r.position}</td>
                  <td>{r.effective_starters}</td>
                  <td>{r.replacement_points.toFixed(1)}</td>
                  <td>{r.top_vor.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
