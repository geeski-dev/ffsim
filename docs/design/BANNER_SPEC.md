# Banner implementation — handoff spec

Adapted from the ChatGPT-authored spec (28 Aug 2026) to match this codebase.
The banner's visual design is unchanged. What changed is everything the original
spec assumed about the repo, plus the structural decisions it
left open, which Grant has now resolved (§2). It covers three things that ship
together: the full-width banner, the tab-row navigation, and the SPA conversion.

**Read `docs/design/banner-reference.html` first.** Open it in a browser. It is
not a mockup or a reconstruction — it is the live reference's own markup and CSS,
captured from its DOM and computed styles, with class names already converted to
this repo's convention and the logo already pointed at the real asset. Your job
is to move that into React, not to reinvent it from a screenshot.

---

## 1. What is actually in this repo

Correcting the original spec's assumptions:

| Original spec said | Reality |
| --- | --- |
| `mispricing-engine-logo.png` is supplied | Logo already lives at `web/src/assets/logo.png`, imported in `App.tsx` |
| Two banner reference `.jpg` files | Do not exist. `docs/design/banner-reference.html` replaces them |
| "Run the relevant build, typecheck, and tests" | There is no test script. See §5 |
| "the current plain black logo area" | It is `.app-header`, and it renders in **two** places |

Other facts you need:

- **The logo is 1983×793 (2.5:1)** with essentially no transparent padding
  (bbox 41,21 → 1927,774). There is nothing to crop.
- **The header is duplicated.** `App.tsx` renders `.app-header` once in the
  `isAboutPage` branch (~line 133) and once in the main return (~line 145).
  Both must go.
- **Styling convention:** one plain `web/src/App.css`, kebab-case class names.
  No CSS modules, no Tailwind, no preprocessor. Tokens are `:root` variables in
  `web/src/index.css` (`--ground`, `--surface`, `--surface-alt`, `--primary:
  #3DD68C`, `--rule`, `--ink`, `--ink-mute`, `--tooltip-border`).
- **`html { font-size: 20.8px }`** in `index.css` — a deliberate 1.3× type ramp.
  The banner's clamp values are absolute px from a design authored at a 16px
  root, so the banner reads slightly smaller relative to the rest of the UI than
  the reference implies. Leave the px values alone; flag it in your report if it
  looks wrong on screen rather than adjusting silently.
- **No container queries exist in the repo yet.** This introduces the pattern.
  Fine — no dependency, universal support in current browsers.
- **No new dependencies.** The mesh is inline SVG. Do not add a library.

Already applied, ahead of this work: the logo `<img>` carried
`width={288} height={288}` — a 2.5:1 image forced into a square box and rescued
only by `object-fit: contain`, leaving ~86px of dead space above and below it.
Both call sites now pass the intrinsic 1983×793 with `height: auto` in CSS. That
markup is superseded by this change; the note is here so you know why it looks
different from any screenshot taken before 28 Aug.

---

## 2. Resolved structure

### 2.1 Page shell

One top-level wrapper at the root; the banner is a sibling of everything else,
both inside that wrapper.

```jsx
<div className="root">
  <Banner mode={mode} />
  <div className="app">
    {/* everything that is there today, minus .app-header */}
  </div>
</div>
```

- `.root` — no `max-width`, no padding. The banner spans the viewport.
- `.app` — keeps `max-width: 1400px; padding: 24px` exactly as it is today.
- `.app-header` and its CSS are deleted. So is `.mode-toggle`'s
  `margin-left: auto` (see §2.2).

**Where `container-type` goes.** `Banner` renders its own `.banner-shell` with
`container-type: inline-size`, and `.draft-banner` sits inside it. Do **not** put
`container-type` on `.root` — it applies `contain: layout style inline-size` to
the entire application, which is a much larger blast radius than this needs.

The `cqw` units in the logo's `clamp()` and the `@container (width <= 700px)`
block resolve against `.banner-shell`. Miss this and `cqw` falls back to the
small-viewport font size, so the logo comes out at its 205px minimum at every
width.

### 2.2 Navigation — three uniform tabs above Settings

**Decision (Grant, 29 Aug):** Board, Draft and About all sit together in one
row, directly above `SettingsPanel`, identically styled. They read as tabs. The
banner carries no navigation at all — logo only.

    [ Board | Draft | About ]

- One bordered container, shared rounding, segments divided by `--rule` rather
  than gapped. Today's `.mode-toggle` is `display:flex; gap:4px` with
  independently-bordered buttons; that is the look being replaced. So is
  `.about-link`, which had its own separate treatment — delete it.
- Selected tab keeps the current active treatment: `--primary` fill,
  `--ground` text. Exactly one is selected at any time, About included.
- "Mesh with the new design" means picking up the banner's green edge language
  — the selected tab can carry a restrained version of `.draft-banner__edge`'s
  glow (`box-shadow: 0 0 16px rgba(24,239,125,.26)`). Restrained. If it competes
  with the banner for attention it is wrong.
- **Build it to hold four, not three.** Simulate is coming (item 2 of the
  draft-mode UI/UX pass). Do not add it here — just do not write layout that
  assumes a fixed count.

On the About page the same three tabs render in the same position with About
selected, so the row never moves or changes shape between views.

### 2.3 About becomes a mode (SPA conversion)

**Decision (Grant, 29 Aug):** convert to a single-page app. About is a third
mode rendered by a component swap, not a route. All three tabs then behave
identically, which is what the uniform styling promises.

```
type AppMode = 'board' | 'draft' | 'about';
```

`AboutPage` is already a component; render it in place of the board when
`mode === 'about'`.

#### There are four navigation exits, not one

Grep found every hard link out of the app. All four have to change together or
the SPA is only half-converted:

| Where | Today | Becomes |
| --- | --- | --- |
| `App.tsx:69` | `isAboutPage` from `window.location.pathname` | seeds the **initial** mode, then never read again |
| `App.tsx:156` | `<a href="/about" class="about-link">` | the About tab (§2.2); `.about-link` CSS is deleted |
| `AboutPage.tsx:18` | `<a href="/">← Back to board</a>` | **delete it.** Confirmed by Grant, 29 Aug: the three tabs are the navigation, and a second way back is redundant |
| `Tooltip.tsx:143` | `<a href={`/about#${entry.anchor}`}>Learn more →</a>` | see below |

**The tooltip link is the one that matters.** Every "Learn more →" in every
tooltip across the app currently triggers a full page load. Miss this and the
most-clicked path into About stays exactly as slow as it is today, while looking
like it was fixed.

`Tooltip` is used from `PlayerBoard`, `SettingsPanel`, `ScarcityTable` and
others, so threading a prop through every call site is not worth it. Use a small
context — a provider in `App` exposing `navigateToAbout(anchor)`, consumed by
`Tooltip` via `useContext`, falling back to plain `href` behaviour when no
provider is present so nothing breaks if it is rendered outside one.

**Keep the `<a href>` and intercept the click.** Do not replace it with a
`<button>`. About is a reference page people will want to open in a background
tab while drafting, and a real href keeps middle-click, cmd-click and "copy link
address" working:

```jsx
onClick={(e) => {
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
  e.preventDefault();
  navigateToAbout(entry.anchor);
}}
```

#### Anchors

`AboutPage`'s internal `<a href="#confidence">` links keep working untouched —
same-document hash, no navigation.

Jumping to an anchor from **outside** About needs an effect, in two cases:

1. Tooltip "Learn more" — the target element does not exist until `AboutPage`
   has rendered, so switching mode and setting the hash in the same tick will
   not scroll. Scroll in an effect after the mode change commits.
2. A cold load of `/about#confidence` — the browser's native hash scroll fires
   before React has rendered anything, so it silently does nothing. Same effect
   handles it.

Honour `prefers-reduced-motion` when scrolling; `App.tsx`'s `selectPick` already
shows the pattern.

#### Why this is actually instant

The tab switch is a component swap inside a component that never unmounts. No
request, no remount of `App`, no re-parse. `AboutPage` is 181 lines of static
JSX with no data fetching, so it paints in a single frame.

Switching **back** is equally instant, and this is the bigger win: `league`
lives in `App` state, and the fetch effect keys on `settings`, not `mode`. So
returning to Board does not refetch and does not show the loading spinner. The
board is simply there again, in the state it was left in.

Two things that would break that guarantee:

- **Do not code-split `AboutPage`.** A `React.lazy` boundary reintroduces
  exactly the load-and-flash this change exists to remove. Import it directly.
- **Do not key the fetch effect on `mode`**, or entering About and coming back
  will refetch the league and flash the spinner.

**Scroll position.** Entering About from a board scrolled halfway down leaves
the window scroll where it was, against much shorter content — so it clamps, and
coming back lands somewhere other than where you left. Reset scroll to top when
**entering or leaving About only**; leave board ↔ draft alone, since those show
substantially the same content and resetting there would be annoying. The
anchor-scroll effect above takes precedence when there is an anchor.

#### Persistence and deep links

- **Do not persist `'about'`** to `localStorage`. Mode is restored on load and
  landing on About after a reload is nobody's intent. Persist board/draft only;
  anything else falls back to `'board'`.
- **Keep `/about` as a deep link.** Read `pathname` at mount to seed the initial
  mode so links already shared still land correctly.
- Updating the URL via `history.pushState` on tab click is optional. If you skip
  it, the URL goes stale while browsing — acceptable for now, and worth a line
  in your report either way.

This also removes the static-host SPA-fallback requirement, which was a real
unresolved deploy risk: there is no `_redirects`, no `_routes.json`, and
`web/dist/` contains only `index.html`. `/about` has never been exercised on
Cloudflare Pages and was a plausible 404 in production.

### 2.3.1 About reuses the board's container

**Decision (Grant, 29 Aug):** wrap `AboutPage` in the same chrome the board
uses, so switching tabs does not change the shape of the page.

Render it inside `.board-area`, in a `.panel`. `.about-page` already sets
`max-width: 720px`, which sits correctly inside a full-width panel — the card
matches the other panels, the text keeps a comfortable measure.

**Recommendation, confirm before building:** in about mode, hide the tagline,
the intro paragraph, `SettingsPanel` and `SimulationPanel`. None of them mean
anything next to a text page, and leaving them makes the tab switch feel like a
different app rather than a different tab. What stays constant is banner → tab
row → panel, which is the consistency being asked for.

Item 4 of the draft-mode UI/UX pass (About page visual structure — green
headers, soft-green dividers) targets this same component and should land in the
same pass rather than fighting this one.

### 2.4 Collapsed variant in draft mode

Board mode keeps the reference height. Draft mode collapses:

```css
.draft-banner            { height: clamp(220px, 25dvh, 320px); }
.draft-banner--collapsed { height: clamp(132px, 17dvh, 200px); }
```

- **Normal flow. Never `position: fixed` or `sticky`.** It scrolls out of view
  like anything else — that is the point.
- **The logo must shrink too, or it overflows.** The container query is
  width-based, so a collapsed banner does not change the logo on its own. At
  1280px wide the logo is 330px → 132px tall, plus a 42px top offset = 174px,
  against a 132px collapsed minimum. It will spill. Collapsed values:

  ```css
  .draft-banner--collapsed .draft-banner__logo {
    top: clamp(14px, 2.2cqw, 24px);
    width: clamp(150px, 16cqw, 220px);
  }
  ```

  220 ÷ 2.5 = 88px + 24px = 112px, inside 132px. Check the 700px container case
  too, where the logo is pinned at a fixed width.
- **The mesh crops harder.** `preserveAspectRatio="xMidYMid slice"` on a
  1600×440 viewBox slices more aggressively as the banner shortens, and the
  signal trace spans y=72–334. Verify it still reads; if it does not, adjust the
  collapsed rule's mesh inset the same way the reference already does for its
  700px case.

**The transition.** Height, logo width and logo top offset all animate; ~320ms
on an ease-out curve. Optionally shift the mesh inset over the same duration so
the network appears to slide rather than merely be cropped.

Three things to get right:

1. **Do not animate on mount.** Mode is restored from `localStorage`, so loading
   straight into draft mode must render collapsed, not animate down from tall.
   Gate the transition behind a flag set after first paint.
2. **`prefers-reduced-motion: reduce` disables it** — snap between states. The
   codebase already honours this in `App.tsx`'s `selectPick`.
3. Animating `height` lays out every frame. Acceptable for a one-shot 320ms
   change on a top-level block, but watch it on a long board; if it janks, say
   so in your report rather than quietly swapping in a transform that would
   distort the logo.

Grant's UX notes include condensing the sections below the banner. Those land
separately but are meant to fold in with this — leave the collapsed spacing easy
to retune.

---

## 3. The banner component

Create `web/src/components/Banner.tsx`. It renders the `<section>` from
`banner-reference.html` verbatim: the glow div, the mesh `<svg>` (copy it
exactly — every path, gradient, filter and label), the speed-lines div, the
`<img>`, and the edge div. No navigation lives in the banner.

- `import logo from '../assets/logo.png'` — Vite handles it, same as `App.tsx`.
- `alt="Mispricing Engine"`. No `width`/`height` attributes on this one; the
  banner sizes it.
- `aria-hidden="true"` on the `<svg>`.
- Use `<section>`; the surrounding markup has no landmark today.
- SVG attributes need React casing: `strokeWidth`, `strokeOpacity`, `stopColor`,
  `stopOpacity`, `patternUnits`, `strokeLinecap`, `strokeLinejoin`,
  `fontFamily`, `fontSize`, `stdDeviation`, `preserveAspectRatio`.
  `<feMergeNode in="blur"/>` keeps `in`.

**`isolation: isolate` on `.draft-banner` is load-bearing.** The mesh and glow
use `z-index: -2` / `-1`. Without the isolate they paint behind the *page*
rather than behind the banner's own content, and vanish. If the mesh disappears,
that is why.

Keep the raw hexes inside the SVG. They are artwork; they do not map onto
`--primary`. The chrome around it uses tokens.

**Do not:** bake logo and background into one PNG; use canvas; add animation
beyond the collapse transition; touch data flow, state, routing, or the API
client.

---

## 4. Running it

`cd web && npm run dev`. The dev server proxies `/api` to `localhost:8000`, so
unless the FastAPI server is also running the board shows "Could not reach the
API". **That is expected and is not a regression** — the banner renders
regardless. For the full page, from the repo root:
`uvicorn api.main:app --reload`.

---

## 5. Verification

**Widths:** 390, 768, 1280, 1720 — in **both** board and draft mode, since the
heights differ. At each:

- logo not clipped, not distorted, fully visible, inside the banner;
- no overlap with the content below;
- left-side fade still gives the logo contrast;
- mesh carries weight on the right, not the left;
- no horizontal page scroll;
- the tab row below reads as one unit and does not wrap at 390px.

Then: toggle board ↔ draft and watch the transition. Reload while in draft mode
and confirm it does **not** animate on load.

**SPA checks** (§2.3) — every one of these must happen without a page load:

- each of the three tabs, in both directions;
- "Learn more →" from a tooltip in `PlayerBoard`, and again from one in
  `SettingsPanel`, landing on the right anchor both times;
- cmd-click / middle-click on a tooltip "Learn more" still opens a real tab;
- cold load of `/about` lands on the About tab; cold load of
  `/about#confidence` also scrolls to that section;
- reload while on About comes back to Board, not About.

**If you have browser control**, capture each width and compare against
`banner-reference.html` at the same width — same page, same widths, direct
comparison. **If you do not**, say so plainly rather than implying you checked.
Do not add Playwright or screenshot tooling to this repo for this task; leave
Grant a short list of what to look at and at which widths.

**Checks that exist:** `npm run build` (`tsc -b && vite build`) and `npm run
lint` (oxlint). Both must pass. There is no test suite — do not report test
results.

**Commit before moving on**, so progress is not lost if the session dies.

---

## 6. Report

1. Files changed.
2. Widths actually checked, in which modes, and whether that was by eye in a
   real browser or not.
3. Confirmation that all four navigation exits (§2.3) are converted — name them
   — and that no tab click produces a page load.
4. Whether you implemented `history.pushState` on tab click or left the URL
   stale.
5. `npm run build` and `npm run lint` results.
6. Whether the collapse transition janks, and on what.
7. Any deliberate deviation from `banner-reference.html`, and why.
