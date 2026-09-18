import {
  type FocusEvent,
  type KeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import { createPortal } from 'react-dom';
import { TOOLTIPS, type TooltipId } from '../tooltips';
import { useAboutNavigation } from '../aboutNavigation';

interface Props {
  id: TooltipId;
}

interface PopoverPosition {
  left: number;
  top: number;
}

const GAP = 6;
const VIEWPORT_MARGIN = 8;
const CLOSE_DELAY_MS = 200;

// One component, used everywhere a term needs explaining -- same shape,
// size and styling regardless of where it's dropped in. Hover OR focus
// opens it; Escape closes it and returns focus to the trigger; clicking
// outside closes it (for touch, where there's no hover to fall back to).
// The trigger uses aria-describedby so screen readers announce the short
// description even for users who never interact with the popover at all.
export default function Tooltip({ id }: Props) {
  const entry = TOOLTIPS[id];
  const aboutNavigation = useAboutNavigation();
  const [open, setOpen] = useState(false);
  const descId = useId();
  const wrapRef = useRef<HTMLSpanElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLSpanElement>(null);
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [position, setPosition] = useState<PopoverPosition | null>(null);

  const updatePosition = useCallback(() => {
    const trigger = triggerRef.current;
    const popover = popoverRef.current;
    if (!trigger || !popover) return;

    const triggerRect = trigger.getBoundingClientRect();
    const popoverRect = popover.getBoundingClientRect();
    let left = triggerRect.left;
    let top = triggerRect.bottom + GAP;

    if (left + popoverRect.width > window.innerWidth - VIEWPORT_MARGIN) {
      left = triggerRect.right - popoverRect.width;
    }
    if (top + popoverRect.height > window.innerHeight - VIEWPORT_MARGIN) {
      top = triggerRect.top - popoverRect.height - GAP;
    }

    left = Math.min(Math.max(left, VIEWPORT_MARGIN), window.innerWidth - popoverRect.width - VIEWPORT_MARGIN);
    top = Math.min(Math.max(top, VIEWPORT_MARGIN), window.innerHeight - popoverRect.height - VIEWPORT_MARGIN);
    setPosition({ left, top });
  }, []);

  function close() {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    setOpen(false);
    setPosition(null);
  }

  function openNow() {
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current);
      closeTimerRef.current = null;
    }
    setOpen(true);
  }

  function closeAfterDelay() {
    if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
    closeTimerRef.current = setTimeout(() => {
      closeTimerRef.current = null;
      close();
    }, CLOSE_DELAY_MS);
  }

  function containsTarget(target: EventTarget | null) {
    if (!(target instanceof Node)) return false;
    return Boolean(wrapRef.current?.contains(target) || popoverRef.current?.contains(target));
  }

  function containsFocus() {
    return containsTarget(document.activeElement);
  }

  function handleBlur(e: FocusEvent) {
    if (!containsTarget(e.relatedTarget)) close();
  }

  function handleKeyDown(e: KeyboardEvent) {
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
      if (!containsTarget(e.target)) close();
    }
    document.addEventListener('mousedown', handleDocumentMouseDown);
    return () => document.removeEventListener('mousedown', handleDocumentMouseDown);
  }, [open]);

  useLayoutEffect(() => {
    if (!open) return;
    updatePosition();
  }, [open, updatePosition]);

  useEffect(() => {
    if (!open) return;
    window.addEventListener('scroll', updatePosition, true);
    window.addEventListener('resize', updatePosition);
    return () => {
      window.removeEventListener('scroll', updatePosition, true);
      window.removeEventListener('resize', updatePosition);
    };
  }, [open, updatePosition]);

  useEffect(() => {
    return () => {
      if (closeTimerRef.current) clearTimeout(closeTimerRef.current);
    };
  }, []);

  function handleWrapperMouseLeave(e: ReactMouseEvent) {
    if (containsFocus()) return;
    if (!containsTarget(e.relatedTarget)) closeAfterDelay();
  }

  const popover = open ? (
    <span
      className="tooltip-popover"
      ref={popoverRef}
      style={{
        left: position ? `${position.left}px` : undefined,
        top: position ? `${position.top}px` : undefined,
        visibility: position ? 'visible' : 'hidden',
      }}
      onMouseEnter={openNow}
      onMouseLeave={(e) => {
        if (containsFocus()) return;
        if (!containsTarget(e.relatedTarget)) closeAfterDelay();
      }}
    >
      <span className="tooltip-text" id={descId}>{entry.short}</span>
      <a
        className="tooltip-link"
        href={`/about#${entry.anchor}`}
        onClick={(e) => {
          if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0 || !aboutNavigation) return;
          e.preventDefault();
          aboutNavigation.navigateToAbout(entry.anchor);
        }}
      >
        Learn more →
      </a>
    </span>
  ) : null;

  return (
    <span
      className="tooltip-wrap"
      ref={wrapRef}
      onMouseEnter={openNow}
      onMouseLeave={handleWrapperMouseLeave}
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
        onFocus={openNow}
      >
        <span className="tooltip-glyph" aria-hidden="true">?</span>
      </button>
      {/* No role="tooltip" here on purpose: that ARIA role forbids
          interactive content, and this popover contains a real link.
          aria-describedby on the trigger (pointing at the text span alone,
          not the link) is what makes this readable by screen readers; the
          link is just a normal focusable element after the trigger in tab
          order when the popover is open. */}
      {popover && createPortal(popover, document.body)}
    </span>
  );
}
