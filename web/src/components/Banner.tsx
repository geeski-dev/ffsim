import { useEffect, useState } from 'react';
import logo from '../assets/logo.png';

interface Props {
  collapsed: boolean;
}

// Ported verbatim from docs/design/banner-reference.html -- the reference's
// own markup/CSS captured from its live DOM, not a reconstruction. No
// navigation lives here; see the tab row rendered above SettingsPanel.
export default function Banner({ collapsed }: Props) {
  // Mode restores from localStorage synchronously, so the very first render
  // can already be collapsed -- it must render there directly, not animate
  // down from tall. Gate the transition behind a flag set after first paint.
  const [animatable, setAnimatable] = useState(false);
  useEffect(() => {
    setAnimatable(true);
  }, []);

  const className = [
    'draft-banner',
    collapsed && 'draft-banner--collapsed',
    animatable && 'draft-banner--animatable',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="banner-shell">
      <section className={className} aria-label="Mispricing Engine">
        <div className="draft-banner__glow" />
        <svg
          className="draft-banner__mesh"
          viewBox="0 0 1600 440"
          preserveAspectRatio="xMidYMid slice"
          aria-hidden="true"
        >
          <defs>
            <linearGradient id="meshFade">
              <stop offset="0" stopColor="#00ef79" stopOpacity="0" />
              <stop offset=".28" stopColor="#00ef79" stopOpacity=".1" />
              <stop offset=".66" stopColor="#19f58b" stopOpacity=".48" />
              <stop offset="1" stopColor="#00b85f" stopOpacity=".13" />
            </linearGradient>
            <linearGradient id="signal" x1="0" y1="1" x2="1" y2="0">
              <stop offset="0" stopColor="#00c765" stopOpacity=".08" />
              <stop offset=".56" stopColor="#31ff9b" stopOpacity=".94" />
              <stop offset="1" stopColor="#00a64f" stopOpacity=".15" />
            </linearGradient>
            <radialGradient id="nodeGlow">
              <stop offset="0" stopColor="#baffda" />
              <stop offset=".35" stopColor="#16f386" />
              <stop offset="1" stopColor="#16f386" stopOpacity="0" />
            </radialGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="3.5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <pattern id="microGrid" width="54" height="54" patternUnits="userSpaceOnUse">
              <path d="M54 0H0V54" fill="none" stroke="#22df7e" strokeOpacity=".045" />
            </pattern>
          </defs>
          <rect width="1600" height="440" fill="url(#microGrid)" />
          <g fill="none" stroke="url(#meshFade)" strokeWidth="1.4">
            <path d="M250 360 470 216 670 310 870 124 1050 240 1280 72 1530 210" />
            <path d="M340 90 540 196 742 66 930 228 1150 102 1380 292 1590 132" />
            <path d="M510 430 670 310 930 228 1050 240 1240 422" />
            <path d="M742 66 870 124 1150 102 1280 72" />
            <path d="M470 216 540 196 670 310 742 66" />
            <path d="M870 124 930 228 1050 240 1150 102" />
            <path d="M1050 240 1280 72 1380 292 1530 210" />
            <path d="M1280 72 1590 132" />
            <path d="M1380 292 1600 390" />
          </g>
          <g fill="none" stroke="url(#signal)" strokeLinecap="round" strokeLinejoin="round" filter="url(#glow)">
            <path
              d="M325 332 430 314 505 334 612 275 700 294 790 220 886 240 978 167 1080 191 1188 105 1274 151 1396 72 1525 92"
              strokeWidth="3.1"
            />
            <path
              d="M1085 372 1175 329 1243 349 1320 280 1401 299 1483 232 1586 245"
              strokeWidth="1.5"
              opacity=".55"
            />
          </g>
          <g fill="#21ed83" opacity=".72">
            <circle cx="470" cy="216" r="3.5" />
            <circle cx="540" cy="196" r="3.5" />
            <circle cx="670" cy="310" r="3.5" />
            <circle cx="742" cy="66" r="3.5" />
            <circle cx="870" cy="124" r="3.5" />
            <circle cx="930" cy="228" r="3.5" />
            <circle cx="1050" cy="240" r="3.5" />
            <circle cx="1150" cy="102" r="3.5" />
            <circle cx="1280" cy="72" r="3.5" />
            <circle cx="1380" cy="292" r="3.5" />
            <circle cx="1530" cy="210" r="3.5" />
          </g>
          <g filter="url(#glow)">
            <circle cx="978" cy="167" r="18" fill="url(#nodeGlow)" />
            <circle cx="1396" cy="72" r="14" fill="url(#nodeGlow)" />
            <circle cx="700" cy="294" r="10" fill="url(#nodeGlow)" />
          </g>
          <g fill="#43f89a" opacity=".32" fontFamily="monospace" fontSize="12">
            <text x="1090" y="184">VALUE DELTA +14.8</text>
            <text x="1210" y="338">ADP SIGNAL 0.82</text>
            <text x="1420" y="122">EDGE FOUND</text>
          </g>
        </svg>
        <div className="draft-banner__speed" />
        <img className="draft-banner__logo" src={logo} alt="Mispricing Engine" />
        <div className="draft-banner__edge" />
      </section>
    </div>
  );
}
