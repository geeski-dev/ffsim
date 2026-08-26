import type { PositionScarcityRow } from '../api/types';

interface Props {
  rows: PositionScarcityRow[];
}

export default function ScarcityTable({ rows }: Props) {
  return (
    <div className="panel">
      <h2>Positional scarcity</h2>
      <table>
        <thead>
          <tr>
            <th>Position</th>
            <th>Effective starters</th>
            <th>Replacement pts</th>
            <th>Top VOR</th>
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
  );
}
