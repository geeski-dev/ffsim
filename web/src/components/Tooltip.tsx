import { useEffect, useId, useRef, useState } from 'react';
import { TOOLTIPS, type TooltipId } from '../tooltips';

interface Props {
  id: TooltipId;
  // Optional: render the trigger as an inline label with the info glyph
  // after it, instead of a bare icon. Use where there's no adjacent label
  // text already doing that job (e.g. a bare "?" next to a table header).
  label?: string;
}

// One component, used everywhere a term needs explaining -- same shape,
// size and styling regardless of where it's dropped in. Hover OR focus
// opens it; Escape closes it and returns focus to the trigger; clicking
// outside closes it (for touch, where there's no hover to fall back to).
// The trigger uses aria-describedby so screen readers announce the short
// description even for users who never interact with the popover at all.
export default function Tooltip({ id, label }: Props) {
  const entry = TOOLTIPS[id];
  const [open, setOpen] = useState(false);
  const descId = useId();
  const wrapRef = useRef<HTMLSpanElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);

  function close() {
    setOpen(false);
  }

  function handleBlur(e: React.FocusEvent) {
    if (!wrapRef.current?.contains(e.relatedTarget as Node)) close();
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Escape') {
      close();
      triggerRef.current?.focus();
    }
  }

  // Blur only fires when focus actually moves to another element -- a tap
  // on a non-focusable area of the page (the common case on touch, and
  // exactly the case a click-to-open trigger needs this for) leaves focus
  // right where it was and never fires it. This is the real "click
  // outside" close, independent of focus.
  useEffect(() => {
    if (!open) return;
    function handleDocumentMouseDown(e: MouseEvent) {
      if (!wrapRef.current?.contains(e.target as Node)) close();
    }
    document.addEventListener('mousedown', handleDocumentMouseDown);
    return () => document.removeEventListener('mousedown', handleDocumentMouseDown);
  }, [open]);

  return (
    <span
      className="tooltip-wrap"
      ref={wrapRef}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onBlur={handleBlur}
      onKeyDown={handleKeyDown}
    >
      <button
        type="button"
        ref={triggerRef}
        className="tooltip-trigger"
        aria-describedby={descId}
        aria-expanded={open}
        onClick={(e) => {
          // Opens, deliberately not toggles: a real click on a button also
          // fires focus first, which already opens it via onFocus below --
          // a toggle here would immediately flip that back closed, so a
          // mouse or touch click would never appear to do anything.
          // Escape/blur/mouseleave are what close it.
          e.stopPropagation();
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
      >
        {label ? <span className="tooltip-trigger-label">{label}</span> : null}
        <span className="tooltip-glyph" aria-hidden="true">?</span>
      </button>
      {/* No role="tooltip" here on purpose: that ARIA role forbids
          interactive content, and this popover contains a real link.
          aria-describedby on the trigger (pointing at the text span alone,
          not the link) is what makes this readable by screen readers; the
          link is just a normal focusable element after the trigger in tab
          order when the popover is open. */}
      {open && (
        <span className="tooltip-popover">
          <span className="tooltip-text" id={descId}>{entry.short}</span>
          <a className="tooltip-link" href={`/about#${entry.anchor}`}>
            Learn more →
          </a>
        </span>
      )}
    </span>
  );
}
