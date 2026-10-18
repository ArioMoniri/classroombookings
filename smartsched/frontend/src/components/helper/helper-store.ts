"use client";
/**
 * HX-03: the helper's client state (helper.md §2.4–§2.5, §4.1 rule 7). One conversation per tab: the sheet's open
 * state and opener, the log entries (the person's messages and the server's cards with their local state), and the
 * "Yalnızca metin" preference (device only, localStorage). Nothing here talks to the network; the runner
 * (use-helper-runner.ts) does.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { FileAnswerCard, Stage } from "@/lib/api/helper-files";
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

/**
 * HB-23c (helper-file-router.md §7.3): a dropped / attached / pasted file and the router's answer, **ephemeral** (never
 * sent to `/helper/turn` or kept in the history; gone after "Yeni konuşma"). The browser's File objects stay in
 * memory in file-router.ts, never here.
 */
export type FileView =
  /** `file` card (detected / unknown / needs_planner), `choice` (ambiguous), `refusal` / `error` / `limit` */
  | { kind: "card"; card: FileAnswerCard }
  /** "Başka bir tür seç": the client's list of kinds this person may import (no server call) */
  | { kind: "pick"; card: FileAnswerCard }
  /** several files (decision 16): one client card; the browser hands the File objects to the setup wizard, no stage */
  | { kind: "many"; n: number }
  /** the client's own refusal before any request (size over 15 MB) or a network / read failure */
  | { kind: "local"; code: "file_too_large" | "file_empty" | "file_read_failed"; size?: number };

export interface FileEntry {
  kind: "file";
  key: string;
  files: { name: string; size: number }[];
  /** reading → shown; `collapsed`: a newer file took over (one live file card per thread); `handed`: the primary ran */
  phase: "reading" | "shown" | "collapsed" | "handed" | "cancelled";
  view: FileView | null;
  stage: Stage | null;
  /** `HELPER_FILE_STAGE=off`: nothing staged; the target page re-sends the browser's File */
  resend?: boolean;
  /** the token's 10 minutes passed (or the server said 410): "Dosyayı yeniden oku" */
  expired?: boolean;
  /** a localised line under the card (the button's error) */
  notice?: { tr: string; en: string } | null;
  /** bumps when a new card arrives, so the view moves the focus to its title once */
  seq: number;
  /** the chooser row the person picked: its tint moves into the next card's header (§9 "Chooser pick") */
  picked?: string | null;
}

export type LogEntry = CardEntry | UserEntry | FallbackEntry | NoteEntry | FileEntry;

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
  /** HB-23c: open the file picker as soon as the sheet is open (palette "Dosya ekle…", empty-state links) */
  pendingPick: boolean;
  takePick: () => boolean;
  /** Rehber modu: the text the palette handed over, put into the guide's search field */
  guideSeed: string | null;
  /** Rehber modu: what the person typed in the guide field; kept while "Göster" closes the sheet (HB18-F09) */
  guideText: string;
  setGuideText: (q: string) => void;
  /** "Göster": a 1-step spotlight on this feature's anchor (show-me.tsx) */
  showMe: { featureId: string; reopen: boolean; n: number } | null;
  openSheet: (opts?: { opener?: HTMLElement | null; ask?: string; action?: HelperState["pendingAction"]; pickFile?: boolean }) => void;
  closeSheet: () => void;
  setGuideSeed: (q: string | null) => void;
  takePending: () => { ask: string | null; action: HelperState["pendingAction"] };
  pushUser: (text: string) => void;
  pushCard: (card: HelperCard, extra?: Partial<CardEntry>) => string;
  pushFallback: () => void;
  pushNote: (text: { tr: string; en: string }) => void;
  /** HB-23c: a new file entry; the older live one collapses to a line (§7.3 thread rule) */
  pushFile: (files: { name: string; size: number }[]) => string;
  updateFile: (key: string, patch: Partial<FileEntry> | ((e: FileEntry) => Partial<FileEntry>)) => void;
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
      pendingPick: false,
      takePick: () => {
        const v = get().pendingPick;
        if (v) set({ pendingPick: false });
        return v;
      },
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
          pendingPick: !!opts?.pickFile,
          // HB18-F14: a step card left open would cover the sheet and take its focus
          showMe: null,
        })),
      closeSheet: () => set({ open: false, pendingAsk: null, pendingAction: null, pendingPick: false, guideSeed: null }),
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
      pushFile: (files) => {
        const key = nextKey("file");
        set((s) => ({
          entries: [
            ...s.entries.map((e) => (e.kind === "file" && (e.phase === "shown" || e.phase === "reading") ? { ...e, phase: "collapsed" as const } : e)),
            { kind: "file", key, files, phase: "reading", view: null, stage: null, seq: 0 },
          ],
        }));
        return key;
      },
      updateFile: (key, patch) =>
        set((s) => ({ entries: s.entries.map((e) => (e.kind === "file" && e.key === key ? { ...e, ...(typeof patch === "function" ? patch(e) : patch) } : e)) })),
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
