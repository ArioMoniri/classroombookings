"use client";

/**
 * One Zustand store per studio instance: the local draft (reducer in ./studio-reducer.ts), the
 * studio-wide undo/redo stack (`studio.history`, generator-studio.md §3.2) and the pre-check result.
 * A store (instead of useReducer) lets the autosaver and `flush()` read the latest state synchronously.
 */
import { createStore } from "zustand/vanilla";
import type { ProposedConstraint } from "@/lib/api/schemas";
import type { Precheck, ProposedSectionEdit, Unparsed } from "@/lib/api/studio-schemas";
import { initialStudioState, studioReducer, type StudioAction, type StudioState } from "./studio-reducer";

export interface HistoryEntry {
  label: string;
  undo: () => Promise<unknown> | unknown;
  redo: () => Promise<unknown> | unknown;
}

/** One suggestion waiting in the review tray (NL text, an uploaded file row, a pasted e-mail). */
export type TrayItem = {
  key: string;
  origin: "nl" | "upload";
  /** file name for uploads ("Pasted text" for the paste tab) */
  file?: string;
  state: "pending" | "accepted" | "rejected";
  createdIds?: number[];
} & ({ type: "rule"; proposal: ProposedConstraint } | { type: "edit"; edit: ProposedSectionEdit } | { type: "unparsed"; unparsed: Unparsed });

export interface ActiveRun {
  runId: number;
  previousRunId: number | null;
  startedAt: number;
}

export interface StudioStoreState {
  studio: StudioState;
  dispatch: (a: StudioAction) => void;
  past: HistoryEntry[];
  future: HistoryEntry[];
  /** record an action that already happened; it can be undone with its inverse */
  record: (e: HistoryEntry) => void;
  undo: () => Promise<string | null>;
  redo: () => Promise<string | null>;
  precheck: Precheck | null;
  checking: boolean;
  precheckError: string | null;
  setPrecheck: (p: Precheck | null) => void;
  setChecking: (v: boolean, error?: string | null) => void;
  /** bumped on every change anywhere in the studio (the pre-check re-runs 1.5 s later) */
  changeTick: number;
  touch: () => void;
  tray: TrayItem[];
  addTray: (items: TrayItem[]) => void;
  updateTray: (key: string, patch: Partial<TrayItem>) => void;
  setTrayState: (keys: string[], state: TrayItem["state"], createdIds?: number[]) => void;
  clearTray: (origin?: TrayItem["origin"]) => void;
  activeRun: ActiveRun | null;
  setActiveRun: (r: ActiveRun | null) => void;
  /** the Write-it box text (kept across steps; "Rephrase as text…" moves an unreadable row here) */
  nlText: string;
  setNlText: (v: string) => void;
}

const HISTORY_LIMIT = 50;

export function createStudioStore() {
  return createStore<StudioStoreState>()((set, get) => ({
    studio: initialStudioState,
    dispatch: (a) => set((s) => ({ studio: studioReducer(s.studio, a), changeTick: isEdit(a) ? s.changeTick + 1 : s.changeTick })),
    past: [],
    future: [],
    record: (e) => set((s) => ({ past: [...s.past.slice(-HISTORY_LIMIT + 1), e], future: [], changeTick: s.changeTick + 1 })),
    undo: async () => {
      const e = get().past.at(-1);
      if (!e) return null;
      set((s) => ({ past: s.past.slice(0, -1), future: [...s.future, e] }));
      await e.undo();
      set((s) => ({ changeTick: s.changeTick + 1 }));
      return e.label;
    },
    redo: async () => {
      const e = get().future.at(-1);
      if (!e) return null;
      set((s) => ({ future: s.future.slice(0, -1), past: [...s.past, e] }));
      await e.redo();
      set((s) => ({ changeTick: s.changeTick + 1 }));
      return e.label;
    },
    precheck: null,
    checking: false,
    precheckError: null,
    setPrecheck: (p) => set({ precheck: p, checking: false, precheckError: null }),
    setChecking: (v, error = null) => set({ checking: v, precheckError: error }),
    changeTick: 0,
    touch: () => set((s) => ({ changeTick: s.changeTick + 1 })),
    tray: [],
    addTray: (items) => set((s) => ({ tray: [...s.tray.filter((x) => !items.some((i) => i.key === x.key)), ...items] })),
    updateTray: (key, patch) => set((s) => ({ tray: s.tray.map((x) => (x.key === key ? ({ ...x, ...patch } as TrayItem) : x)) })),
    setTrayState: (keys, state, createdIds) => set((s) => ({ tray: s.tray.map((x) => (keys.includes(x.key) ? { ...x, state, createdIds: createdIds ?? x.createdIds } : x)) })),
    clearTray: (origin) => set((s) => ({ tray: origin ? s.tray.filter((x) => x.origin !== origin) : [] })),
    activeRun: null,
    setActiveRun: (r) => set({ activeRun: r }),
    nlText: "",
    setNlText: (v) => set({ nlText: v }),
  }));
}

function isEdit(a: StudioAction): boolean {
  return !["hydrate", "saving", "saved", "saveFailed", "conflict", "keepMine", "setStep"].includes(a.type);
}

export type StudioStore = ReturnType<typeof createStudioStore>;
