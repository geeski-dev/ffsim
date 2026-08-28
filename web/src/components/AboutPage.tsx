import { useEffect } from 'react';
import { TOOLTIPS, TOOLTIP_IDS } from '../tooltips';

export default function AboutPage() {
  // The browser's own "scroll to #fragment on load" fires before React has
  // rendered anything -- the target id doesn't exist in the DOM yet, the
  // native scroll silently no-ops, and nothing retries it. This does that
  // retry, once layout has actually happened.
  useEffect(() => {
    const hash = window.location.hash.slice(1);
    if (!hash) return;
    const target = document.getElementById(hash);
    target?.scrollIntoView({ block: 'start' });
  }, []);

  return (
    <div className="about-page">
      <a href="/" className="back-link">← Back to board</a>

      <section id="what-this-is">
        <h2>What this is</h2>
        <p>Most draft tools rank players. This one <strong>prices</strong> them.</p>
        <p>
          A ranking tells you who's better. A price tells you what you're paying. Those are
          different questions, and the second one is where drafts are won — you don't need to
          find the best player, you need to find the one who's cheaper than he should be.
        </p>
        <p>
          So this board shows you two things side by side: what the market and the analysts
          think a player is worth, and what we think. Where those disagree is the only place
          an edge can come from.
        </p>
      </section>

      <section id="the-one-idea">
        <h2>The one idea</h2>
        <p>
          A player's value isn't how many points he scores. It's <strong>how many more he
          scores than someone you could have for free.</strong>
        </p>
        <p>
          A quarterback who scores 300 points sounds better than a running back who scores 200.
          But if the best quarterback available on waivers scores 280 and the best running back
          scores 90, the running back is worth far more to you. That gap — 20 versus 110 — is
          what actually matters.
        </p>
        <p>Every number on this board is built from that idea.</p>
      </section>

      <section id="how-its-built">
        <h2>How the board is built</h2>
        <p>Four steps, in order. The first three are arithmetic. Only the fourth is an opinion.</p>

        <h3 id="replacement-level">1. Replacement level</h3>
        <p>
          We fill every team's starting lineup in your league, including flex spots, and see
          who's left. That best leftover player is "free." In a 10-team league starting two
          backs plus a flex, roughly 24 running backs start, so replacement is about what the
          25th best scores.
        </p>

        <h3 id="our-value-explained">2. Our Value</h3>
        <p>A player's projected points minus that replacement level. How much better than free he is.</p>

        <h3 id="market-price">3. The market's price</h3>
        <p>
          We take everyone's ADP and work out what the market implicitly thinks each draft slot
          is worth, expressed in the same units.
        </p>

        <h3 id="bargain-explained">4. Bargain</h3>
        <p>Our value minus the market's. Positive means we think he's worth more than he costs.</p>

        <p>
          Steps 1 to 3 are bookkeeping — they'd be true whoever ran them. <strong>Step 4 is a
          claim</strong>, and it's the one you should be sceptical of. See{' '}
          <a href="#confidence">What we know and what we don't</a>.
        </p>
      </section>

      <section id="the-two-settings">
        <h2>The two settings</h2>
        <p>They control different things and you can mix them freely.</p>

        <h3 id="variance-explained">Variance</h3>
        <p>
          How much upside you chase. At Low, you're valuing a player by his typical season. At
          Extreme, by his best plausible one. Higher settings prefer the player who might be
          great over the one who'll reliably be fine.
        </p>

        <h3 id="model-influence-explained">Model Influence</h3>
        <p>How much of <em>our</em> opinion to act on.</p>
        <p>
          At <strong>Off</strong>, you're looking at the consensus board: the market's ordering,
          rearranged for your league's roster and scoring. We're not asserting anything. The
          Bargain column greys out, because there's nothing being applied.
        </p>
        <p>
          Turn it up and we start weighting the places we disagree with the market. At{' '}
          <strong>Extreme</strong>, the board is entirely our view.
        </p>
        <p><strong>Off is the default, deliberately.</strong> See <a href="#confidence">below</a>.</p>
      </section>

      <section id="the-two-modes">
        <h2>The two modes</h2>
        <p><strong>Board</strong> is for exploring — sort, filter, move the knobs, see what changes.</p>
        <p>
          <strong>Draft</strong> is for the two hours you're actually drafting. Rows get bigger,
          the knobs lock so you can't fumble a setting on the clock, and you mark players as
          they come off the board. Drafted players stay visible but struck through, because
          watching a run happen tells you something: three tight ends gone in four picks
          changes what you do next.
        </p>
        <p>
          Nothing recalculates that shouldn't. A player's value doesn't change because someone
          else got taken — what changes is whether you can still get him.
        </p>
      </section>

      <section id="confidence">
        <h2>What we know and what we don't</h2>
        <p>Most tools won't tell you this. We think you should know it before you trust a number.</p>

        <p>
          <strong>What's solid.</strong> Replacement levels, values, tiers, your pick schedule,
          hedge window, and the odds a player survives to your next pick — all of it is
          arithmetic. It's bookkeeping you'd otherwise do badly in your head with a clock
          running. None of it depends on us being right about anything.
        </p>

        <p>
          <strong>What's a claim.</strong> The Bargain column. It says the market has mispriced
          someone, and that's a genuine assertion that could be wrong.
        </p>

        <p>
          <strong>What we've actually measured.</strong> We tested this against five real
          seasons. Drafting straight down the consensus board finishes exactly league-average,
          as you'd expect. <strong>We have not been able to show that our board beats it.</strong>{' '}
          The test was small — five seasons is not many — and it ran on weaker projections than
          the live board uses, so it isn't damning either. But it isn't a green light, and we're
          not going to pretend otherwise.
        </p>

        <p>
          <strong>That's why Model Influence defaults to Off.</strong> The consensus board is
          the setting whose behaviour we've measured. Everything above Off is you deciding we're
          worth listening to. We'd rather you make that choice than have us make it quietly on
          your behalf.
        </p>

        <p>
          <strong>One open problem.</strong> We don't yet have a reliable way to spot a
          high-ceiling player before the season. We've tested several — how much a player
          bounces around week to week, how concentrated his production is, how much the
          analysts disagree about him — and every one of them tells you almost nothing once you
          account for how good he already is. The best predictor of a big season is simply
          being a good player. So treat the Variance setting as a preference about what kind of
          team you want, not as a way of finding hidden upside.
        </p>
      </section>

      <section id="glossary">
        <h2>Every term, defined</h2>
        <dl className="glossary-list">
          {TOOLTIP_IDS.map((id) => {
            const entry = TOOLTIPS[id];
            return (
              <div className="glossary-entry" id={id} key={id}>
                <dt>{entry.label}</dt>
                <dd>{entry.short}</dd>
              </div>
            );
          })}
        </dl>
      </section>
    </div>
  );
}
