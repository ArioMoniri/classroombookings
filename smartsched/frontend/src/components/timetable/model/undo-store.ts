"use client";
/**
 * Undo / redo (calendar.md §9.10): a per-run client stack of {label, forward, inverse}, up to 100 entries,
 * surviving lens and week changes but not reloads. Server mutations are undone by their inverse call; when
 * the inverse fails (slot taken meanwhile) the entry stays and the caller reports it.
 */
import { create } from "zustand";

export interface UndoEntry {
  id: number;
  label: string;
  forward: () => Promise<void>;
  inverse: () => Promise<void>;
}

interface UndoState {
  runId: number | null;
  past: UndoEntry[];
  future: UndoEntry[];
  busy: boolean;
  setRun: (runId: number | null) => void;
  push: (e: Omit<UndoEntry, "id">) => void;
  undo: () => Promise<UndoEntry | null>;
  redo: () => Promise<UndoEntry | null>;
  clear: () => void;
}

export const UNDO_LIMIT = 100;
let seq = 0;

export const useUndoStore = create<UndoState>()((set, get) => ({
  runId: null,
  past: [],
  future: [],
  busy: false,
  setRun: (runId) => {
    if (get().runId !== runId) set({ runId, past: [], future: [] });
  },
  push: (e) => set((s) => ({ past: [...s.past, { ...e, id: ++seq }].slice(-UNDO_LIMIT), future: [] })),
  undo: async () => {
    const { past, busy } = get();
    const entry = past[past.length - 1];
    if (!entry || busy) return null;
    set({ busy: true });
    try {
      await entry.inverse();
      set((s) => ({ past: s.past.slice(0, -1), future: [...s.future, entry] }));
      return entry;
    } finally {
      set({ busy: false });
    }
  },
  redo: async () => {
    const { future, busy } = get();
    const entry = future[future.length - 1];
    if (!entry || busy) return null;
    set({ busy: true });
    try {
      await entry.forward();
      set((s) => ({ future: s.future.slice(0, -1), past: [...s.past, entry] }));
      return entry;
    } finally {
      set({ busy: false });
    }
  },
  clear: () => set({ past: [], future: [] }),
}));
