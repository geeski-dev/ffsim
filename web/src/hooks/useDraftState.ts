import { useEffect, useMemo, useState } from 'react';
import { readVersionedStorage, writeVersionedStorage } from '../storage/versionedStorage';

export interface DraftState {
  gone: string[];
  mine: string[];
  draftPosition: number;
}

// Separate key and version from ffsim.appState, deliberately. The two
// version independently -- adding a field to draft state later, or to app
// settings later, can never wipe the other's saved data the way a shared
// key + a single version bump would.
const DRAFT_STORAGE_KEY = 'ffsim.draftState';
const DRAFT_STORAGE_VERSION = 1;

export const DEFAULT_DRAFT_STATE: DraftState = { gone: [], mine: [], draftPosition: 1 };

interface UndoAction {
  playerId: string;
  wasMine: boolean;
  prevDraftPosition: number;
}

const MAX_UNDO = 20;

export function useDraftState() {
  const [state, setState] = useState<DraftState>(() =>
    readVersionedStorage(DRAFT_STORAGE_KEY, DRAFT_STORAGE_VERSION, DEFAULT_DRAFT_STATE),
  );
  // Undo history is deliberately not persisted -- losing it on refresh is
  // fine; losing gone/mine/draftPosition itself is the thing that must not
  // happen ("a refresh at pick 90 must not lose the draft").
  const [undoStack, setUndoStack] = useState<UndoAction[]>([]);

  useEffect(() => {
    writeVersionedStorage(DRAFT_STORAGE_KEY, DRAFT_STORAGE_VERSION, state);
  }, [state]);

  const goneSet = useMemo(() => new Set(state.gone), [state.gone]);
  const mineSet = useMemo(() => new Set(state.mine), [state.mine]);

  // Plain reads of `state`/`undoStack` from this render's closure, plain
  // (non-updater) setState calls -- deliberately, not useCallback + functional
  // updaters. A functional updater that also needs to push an undo-log entry
  // would have to mutate something (a ref, an outer array) from inside the
  // updater function, and React (in StrictMode) invokes updaters twice to
  // check purity -- a mutation inside one is applied twice. Every mark/undo
  // here is a single discrete user action (a click or an Enter key), so a
  // stale closure is not a real risk, and this stays simple and safe.
  function mark(playerId: string, asMine: boolean) {
    if (goneSet.has(playerId)) return;
    setUndoStack([...undoStack, { playerId, wasMine: asMine, prevDraftPosition: state.draftPosition }].slice(-MAX_UNDO));
    setState({
      gone: [...state.gone, playerId],
      mine: asMine ? [...state.mine, playerId] : state.mine,
      draftPosition: state.draftPosition + 1,
    });
  }

  function undo() {
    if (undoStack.length === 0) return;
    const last = undoStack[undoStack.length - 1];
    setUndoStack(undoStack.slice(0, -1));
    setState({
      gone: state.gone.filter((id) => id !== last.playerId),
      mine: last.wasMine ? state.mine.filter((id) => id !== last.playerId) : state.mine,
      draftPosition: last.prevDraftPosition,
    });
  }

  function resetDraft() {
    setUndoStack([]);
    setState(DEFAULT_DRAFT_STATE);
  }

  return {
    draftPosition: state.draftPosition,
    gone: state.gone,
    mine: state.mine,
    goneSet,
    mineSet,
    markGone: (playerId: string) => mark(playerId, false),
    markMine: (playerId: string) => mark(playerId, true),
    undo,
    canUndo: undoStack.length > 0,
    resetDraft,
  };
}
