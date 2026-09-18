// The position-filter chips the player board offers, and which of them each
// mode can actually display. Kept out of PlayerBoard.tsx so App can consult
// the rule without importing a non-component symbol from a component file.

export const BOARD_POSITIONS = ['All', 'QB', 'RB', 'WR', 'TE'] as const;
// Draft mode collapses the filter to a couple of presets on purpose -- fewer
// decisions during a live draft, not more. "Needed" is computed from mine +
// the league's own lineup requirements (see neededPositions in PlayerBoard).
export const DRAFT_POSITIONS = ['All', 'Needed'] as const;

export type PositionFilter = (typeof BOARD_POSITIONS)[number] | (typeof DRAFT_POSITIONS)[number];

// The two modes offer different chips, so a filter set in one mode can be
// unrepresentable in the other ("Needed" has no chip on the board; "RB" has
// none in draft mode). The filter itself still applies, so leaving it alone
// would silently narrow the table with no chip showing active -- and because
// boardState persists to localStorage, that would survive a reload. Callers
// switching mode use this to drop only a filter the incoming mode can't show.
export function positionFilterAppliesTo(
  mode: 'board' | 'draft',
  filter: PositionFilter,
): boolean {
  const chips: readonly PositionFilter[] = mode === 'draft' ? DRAFT_POSITIONS : BOARD_POSITIONS;
  return chips.includes(filter);
}
