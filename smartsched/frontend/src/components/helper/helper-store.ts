"use client";
/**
 * HX-03: the helper's client state (helper.md §2.4–§2.5, §4.1 rule 7). One conversation per tab: the sheet's open
 * state and opener, the log entries (the person's messages and the server's cards with their local state), and the
 * "Yalnızca metin" preference (device only, localStorage). Nothing here talks to the network; the runner
 * (use-helper-runner.ts) does.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { HelperCard } from "./schema.gen";
import type { IntentHints } from "./intents";

export type CardPhase =
  /** waiting for the person (confirm / form / choice) */
  | "pending"
  /** an older pending card, collapsed to one line by a newer one */
  | "parked"
  | "busy"
  | "done"
  | "cancelled"
  | "expired";

export interface CardEntry {
  kind: "card";
  key: string;
  card: HelperCard;
  phase: CardPhase;
  /** the client hints of the shortcut that asked for this card (a clock time or "3. saat") */
  hints?: IntentHints;
  /** a localised line under the card (an error of the button, "Önizleme değişti") */
  notice?: { tr: string; en: string } | null;
  /** form cards: the server's refusal of one field's value (HB-E `time_outside_grid` / `no_period_at_time` → start) */
  fieldError?: { name: string; text: { tr: string; en: string } } | null;
  /** "1 / 2": the place of a choice in a run of choices (the server sends one at a time) */
  step?: number;
  /** confirm cards: the slot was taken before the click (409 `conflict`, HB18-F03); the free rooms of that slot */
  taken?: { alternatives: { room_id: number; name: string; capacity: number | null }[] } | null;
  /** result cards: undone already */
  undone?: boolean;
  /** the turn that sent it (`run_started.turn_id`): feedback and telemetry */
  turnId?: string;
}

export interface UserEntry {
  kind: "user";
  key: string;
  text: string;
}

/** An answer the client could not read (a newer card type): shown as the fallback text + "Menüde ara". */
export interface FallbackEntry {
  kind: "fallback";
  key: string;
}

/** A short client line in the log (e.g. typed "evet": "Onaylamak için karttaki düğmeye basın."). */
export interface NoteEntry {
  kind: "note";
  key: string;
  text: { tr: string; en: string };
}

export type LogEntry = CardEntry | UserEntry | FallbackEntry | NoteEntry;

export interface TurnState {
  busy: boolean;
  /** tool rows while the server works ("Salonlar aranıyor…") */
  tools: { name: string; state: "pending" | "ok" | "failed" }[];
  /** the model's text before its answer card arrives */
  draft: string;
  /** the last turn fell back to index mode (`run_finished.fallback`) */
  fallback: string | null;
  error: { tr: string; en: string } | null;
}

const IDLE: TurnState = { busy: false, tools: [], draft: "", fallback: null, error: null };

interface HelperState {
  open: boolean;
  /** the element focus returns to on close (the trigger, or the palette's opener) */
  opener: HTMLElement | null;
  entries: LogEntry[];
  turn: TurnState;
  textOnly: boolean;
  /** text the sheet should send as soon as it is open (palette → "Yardımcıya sor") */
  pendingAsk: string | null;
  /** a shortcut the sheet should run as soon as it is open (palette → Kısayollar) */
  pendingAction: { action: string; args: Record<string, string | number>; hints?: IntentHints } | null;
  /** Rehber modu: the text the palette handed over, put into the guide's search field */
  guideSeed: string | null;
  /** Rehber modu: what the person typed in the guide field; kept while "Göster" closes the sheet (HB18-F09) */
  guideText: string;
  setGuideText: (q: string) => void;
  /** "Göster": a 1-step spotlight on this feature's anchor (show-me.tsx) */
  showMe: { featureId: string; reopen: boolean; n: number } | null;
  openSheet: (opts?: { opener?: HTMLElement | null; ask?: string; action?: HelperState["pendingAction"] }) => void;
  closeSheet: () => void;
  setGuideSeed: (q: string | null) => void;
  takePending: () => { ask: string | null; action: HelperState["pendingAction"] };
  pushUser: (text: string) => void;
  pushCard: (card: HelperCard, extra?: Partial<CardEntry>) => string;
  pushFallback: () => void;
  pushNote: (text: { tr: string; en: string }) => void;
  updateCard: (key: string, patch: Partial<CardEntry>) => void;
  setTurn: (patch: Partial<TurnState> | ((t: TurnState) => Partial<TurnState>)) => void;
  newThread: () => void;
  setTextOnly: (v: boolean) => void;
  startShowMe: (featureId: string, reopen: boolean) => void;
  endShowMe: () => void;
}

let seq = 0;
const nextKey = (p: string) => `${p}-${Date.now().toString(36)}-${(seq += 1)}`;

const WAITING: readonly string[] = ["confirm", "form", "choice"];

export const useHelperStore = create<HelperState>()(
  persist(
    (set, get) => ({
      open: false,
      opener: null,
      entries: [],
      turn: IDLE,
      textOnly: false,
      pendingAsk: null,
      pendingAction: null,
      showMe: null,
      guideSeed: null,
      setGuideSeed: (q) => set({ guideSeed: q }),
      guideText: "",
      setGuideText: (q) => set({ guideText: q }),
      openSheet: (opts) =>
        set((s) => ({
          open: true,
          opener: opts?.opener ?? (s.open ? s.opener : typeof document !== "undefined" && document.activeElement instanceof HTMLElement ? document.activeElement : null),
          pendingAsk: opts?.ask ?? null,
          pendingAction: opts?.action ?? null,
          // HB18-F14: a step card left open would cover the sheet and take its focus
          showMe: null,
        })),
      closeSheet: () => set({ open: false, pendingAsk: null, pendingAction: null, guideSeed: null }),
      takePending: () => {
        const { pendingAsk, pendingAction } = get();
        set({ pendingAsk: null, pendingAction: null });
        return { ask: pendingAsk, action: pendingAction };
      },
      pushUser: (text) => set((s) => ({ entries: [...s.entries, { kind: "user", key: nextKey("u"), text }] })),
      pushCard: (card, extra) => {
        const key = nextKey("c");
        const waiting = WAITING.includes(card.type);
        set((s) => ({
          // rule 7: a new card parks the older pending form / confirm / choice (at most one pending R2 too)
          entries: [
            ...s.entries.map((e) => (waiting && e.kind === "card" && e.phase === "pending" && WAITING.includes(e.card.type) ? { ...e, phase: "parked" as const } : e)),
            { kind: "card", key, card, phase: waiting ? "pending" : "done", ...extra },
          ],
        }));
        return key;
      },
      pushFallback: () => set((s) => ({ entries: [...s.entries, { kind: "fallback", key: nextKey("f") }] })),
      pushNote: (text) => set((s) => ({ entries: [...s.entries, { kind: "note", key: nextKey("n"), text }] })),
      updateCard: (key, patch) => set((s) => ({ entries: s.entries.map((e) => (e.kind === "card" && e.key === key ? { ...e, ...patch } : e)) })),
      setTurn: (patch) => set((s) => ({ turn: { ...s.turn, ...(typeof patch === "function" ? patch(s.turn) : patch) } })),
      newThread: () => set({ entries: [], turn: IDLE }),
      setTextOnly: (v) => set({ textOnly: v }),
      startShowMe: (featureId, reopen) => set({ showMe: { featureId, reopen, n: (seq += 1) } }),
      endShowMe: () => set({ showMe: null }),
    }),
    // only the device preference is kept (helper.md §5.1: "Yalnızca metin" in localStorage)
    { name: "smartsched.helper", partialize: (s) => ({ textOnly: s.textOnly }) },
  ),
);

export const IDLE_TURN = IDLE;
