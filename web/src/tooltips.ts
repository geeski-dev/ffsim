// Single source of truth for every tooltip in the app. Components reference
// a key here; they never inline copy. Adding a term is one entry in this
// file plus a <Tooltip id="..." /> where it belongs -- nothing else to wire.
//
// `anchor` is the id of the heading on /about this term's "Learn more" link
// jumps to. Six ids point at a full narrative section (the concepts with
// real explanations: market pricing, Our Value, Bargain, the two knobs,
// replacement level); everything else points at its own entry in the
// glossary section, which is generated FROM this same table -- so every
// term is guaranteed a working anchor without a second copy of the list.

export interface TooltipEntry {
  label: string;
  short: string;
  anchor: string;
}

export const TOOLTIPS = {
  // board columns
  adp: {
    label: 'ADP',
    short: "Average Draft Position: where this player typically gets picked across thousands of real drafts. It's the market price, not a ranking of how good he is.",
    anchor: 'market-price',
  },
  expert: {
    label: 'Expert',
    short: "The middle opinion of 12 independent analysts. We use the median so one unusual take doesn't move it.",
    anchor: 'expert',
  },
  'expert-range': {
    label: 'Expert Range',
    short: 'Where the highest and lowest of those 12 analysts have him. A wide range means the experts genuinely disagree — often a sign his role is uncertain rather than his talent.',
    anchor: 'expert-range',
  },
  'our-value': {
    label: 'Our Value',
    short: 'How many points he scores above a freely-available player at his position, in YOUR league. Not how many points he scores — how many more than someone you could pick up for nothing.',
    anchor: 'our-value-explained',
  },
  'our-range': {
    label: 'Our Range',
    short: "Our own high and low estimate for him. Shown so you can judge our confidence the same way you judge the analysts'.",
    anchor: 'our-range',
  },
  bargain: {
    label: 'Bargain',
    short: "How much cheaper he is than we think he's worth. Positive means we'd take him over his price. This is the only number on the board that's our opinion rather than arithmetic — and it's scaled by your Model Influence setting.",
    anchor: 'bargain-explained',
  },

  // the two knobs
  variance: {
    label: 'Variance',
    short: "Shifts your valuation from a player's typical outcome toward his best one. Higher settings prefer players who could be great over players who'll reliably be fine.",
    anchor: 'variance-explained',
  },
  'model-influence': {
    label: 'Model Influence',
    short: "How much of our own valuation to act on. At Off you're looking at the consensus board — the market's ordering, arranged for your league. Turn it up to weight where we disagree.",
    anchor: 'model-influence-explained',
  },

  // draft position panel
  'hedge-window': {
    label: 'Hedge window',
    short: 'The shortest gap between two of your picks. At slot 6 in a 10-team league you pick, then nine players go, then you pick again. It\'s the number that decides whether you can wait on someone.',
    anchor: 'hedge-window',
  },
  'draft-position': {
    label: 'Draft position',
    short: "Your pick number in each round. Click a round to see who's likely to still be available when it comes around.",
    anchor: 'draft-position',
  },

  // positional scarcity panel
  'positional-scarcity': {
    label: 'Positional scarcity',
    short: 'How thin each position gets in your league. This is where Our Value comes from — the scarcer a position, the more a good one is worth.',
    anchor: 'positional-scarcity',
  },
  'effective-starters': {
    label: 'Effective starters',
    short: 'How many players at this position start league-wide once every team fills its lineup, including flex spots.',
    anchor: 'effective-starters',
  },
  'replacement-pts': {
    label: 'Replacement pts',
    short: "What the best freely-available player at this position scores. Everything above this line is what you're actually paying for.",
    anchor: 'replacement-level',
  },
  'top-vor': {
    label: 'Top VOR',
    short: 'How much better the best player at this position is than that free replacement. Compare across positions to see where the real scarcity is.',
    anchor: 'top-vor',
  },

  // league settings
  teams: {
    label: 'Teams',
    short: 'How many teams in your league. This changes everything downstream — more teams means thinner positions and more valuable starters.',
    anchor: 'teams',
  },
  scoring: {
    label: 'Scoring',
    short: 'Half PPR gives 0.5 points per catch, Full PPR gives 1. It shifts value toward receivers and pass-catching backs.',
    anchor: 'scoring',
  },
  'draft-slot': {
    label: 'Draft slot',
    short: 'Which pick you have in round one. This sets your whole pick schedule and your hedge window.',
    anchor: 'draft-slot',
  },
  'bench-size': {
    label: 'Bench size',
    short: 'How many bench spots. Deeper benches mean more players get drafted and the pool runs thinner.',
    anchor: 'bench-size',
  },
  'starting-lineup': {
    label: 'Starting lineup',
    short: 'How many of each position you start each week. This is what determines how scarce each position actually is in your league.',
    anchor: 'starting-lineup',
  },
  flex: {
    label: 'Flex',
    short: "A lineup spot that accepts a running back, receiver or tight end — whoever's best.",
    anchor: 'flex',
  },
  'playoff-teams': {
    label: 'Playoff teams',
    short: 'How many teams make your playoffs.',
    anchor: 'playoff-teams',
  },
  'reserved-slots': {
    label: 'Reserved slots',
    short: "Roster spots set aside for kickers and defenses, which we don't rank. They still take up picks, so we account for them.",
    anchor: 'reserved-slots',
  },

  // elsewhere
  'reshuffle-banner': {
    label: 'Reshuffle',
    short: 'How the board changed when you moved a knob. The players who moved furthest are where our view differs most from the market\'s.',
    anchor: 'reshuffle-banner',
  },
  tier: {
    label: 'Tier',
    short: "A group of players close enough in value that which one you get barely matters. When a tier is about to run out, that's when to take from it.",
    anchor: 'tier',
  },
} satisfies Record<string, TooltipEntry>;

export type TooltipId = keyof typeof TOOLTIPS;

// Every term, in inventory order -- the About page's glossary renders
// exactly this list, one row per entry, each addressable at #<id>. This is
// deliberately independent of `anchor` above: a handful of terms (adp,
// our-value, bargain, variance, model-influence, replacement-pts) have a
// full narrative section elsewhere that their tooltip's "Learn more" points
// to instead, but they still get a compact glossary row here like everyone
// else -- the glossary is the complete reference, `anchor` is just the best
// single link for that specific tooltip.
export const TOOLTIP_IDS = Object.keys(TOOLTIPS) as TooltipId[];
