"use client";
/**
 * HX-03 / HX-04: everything the helper sends. A question streams one turn (`POST /helper/turn`); a shortcut, a row
 * action, a choice pick or a form asks the action's card with **no model call** (`POST /helper/actions/{name}/card`);
 * the card's button confirms (`POST /helper/actions/confirm`) and "Geri al" undoes (`POST /helper/actions/undo`).
 * helper.md §4.1: only the card's button confirms (typed "evet" never does), an expired token shows "Bu öneri
 * eskidi" + Yenile, a 409 brings the new preview, the result line takes the focus and a toast offers "Geri al" 8 s.
 * HX-16: a question carries the "Bu sayfa: …" chip's `context` while the chip is on (the sheet passes it).
 * HX-15 / HX-17: after a confirm or an undo, "Son işlemler" is refetched, and for a note (`remember_note`) the notes
 * and the memory count of Profil › Yardımcı too.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { toast } from "sonner";
import { crbs } from "@/lib/api/crbs";
import { helperApi, helperRefusal, invalidateAfterHelperWrite, trackHelper, type ActionArgs, type TurnContext } from "@/lib/api/helper";
import { translate, type Locale, type MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { useHelperStore, type CardEntry } from "./helper-store";
import type { IntentHints } from "./intents";
import type { FormCard, HelperCard } from "./schema.gen";
import { streamTurn } from "./stream";

const both = (key: MessageKey, vars?: Record<string, string | number>) => ({ tr: translate("tr", key, vars), en: translate("en", key, vars) });

/** Typed consent never confirms a card (helper.md §4.1 rule 4). */
const TYPED_YES = /^\s*(evet|tamam|onayla(yın|yorum)?|olur|yes|yep|ok(ay)?|confirm|do it)\s*[.!]?\s*$/i;
export const isTypedYes = (text: string) => TYPED_YES.test(text.toLocaleLowerCase("tr-TR"));

/** A trusted pointer or keyboard activation (a script's synthetic click is not consent). Tests replace it. */
export const activation = {
  trusted: (event: { nativeEvent?: Event } | Event | undefined): boolean => {
    const native = event && "nativeEvent" in event ? event.nativeEvent : (event as Event | undefined);
    return !!native && native.isTrusted === true;
  },
};

/** Move the focus to an entry's result line (or its card) after the DOM has it; never leave it on <body>. */
export function focusEntry(key: string) {
  const run = () => {
    const root = document.querySelector<HTMLElement>(`[data-entry="${CSS.escape(key)}"]`);
    const target = root?.querySelector<HTMLElement>("[data-focus-target]") ?? root;
    target?.focus({ preventScroll: false });
  };
  if (typeof requestAnimationFrame === "function") requestAnimationFrame(() => requestAnimationFrame(run));
  else run();
}

/** The booking period a shortcut meant ("10:00", "3. saat") among the room's periods of that day. */
export async function resolvePeriod(roomId: number, date: string, hints: IntentHints): Promise<number | null> {
  if (!hints.time && !hints.period) return null;
  try {
    const grid = await crbs.bookings.grid({ display: "room", room_id: roomId, date });
    const periods = [...grid.periods].sort((a, b) => a.time_start.localeCompare(b.time_start));
    const hit = hints.time ? periods.find((p) => p.time_start.slice(0, 5) === hints.time) : periods[(hints.period ?? 0) - 1];
    return hit?.id ?? null;
  } catch {
    return null;
  }
}

function formValue(card: FormCard, name: string) {
  return card.fields.find((f) => f.name === name)?.value ?? null;
}

export interface Runner {
  /** `context`: the "Bu sayfa: …" chip while it is on (HX-16) */
  ask: (text: string, opts?: { context?: TurnContext | null }) => Promise<void>;
  runAction: (action: string, args: ActionArgs, opts?: { hints?: IntentHints; step?: number; replaces?: string }) => Promise<void>;
  confirm: (entry: CardEntry, event: { nativeEvent?: Event } | Event | undefined) => Promise<void>;
  undo: (entry: CardEntry, event?: { nativeEvent?: Event } | Event) => Promise<void>;
  refresh: (entry: CardEntry) => Promise<void>;
  cancel: (entry: CardEntry) => void;
}

export function useHelperRunner(): Runner {
  const { locale } = useI18n();
  const qc = useQueryClient();

  const pushServerCard = useCallback((card: HelperCard, extra?: Partial<CardEntry>) => useHelperStore.getState().pushCard(card, extra), []);

  /** A refused request: the server's card when it sent one, else a status line with its message. */
  const pushRefusal = useCallback(
    (err: unknown) => {
      const r = helperRefusal(err);
      if (r.card) return pushServerCard(r.card);
      useHelperStore.getState().pushNote(r.tr || r.en ? { tr: r.tr ?? r.en ?? "", en: r.en ?? r.tr ?? "" } : both(r.status === 0 ? "helper.card.network" : "helper.error.provider"));
      return null;
    },
    [pushServerCard],
  );

  const runAction = useCallback<Runner["runAction"]>(
    async (action, args, opts) => {
      const st = useHelperStore.getState();
      st.setTurn({ busy: true, error: null });
      try {
        let card = await helperApi.card(action, args);
        // helper.md A1: a shortcut's clock time / "3. saat" picks the period itself, so a resolved room and day go
        // straight to the confirm card (no form step)
        if (card.type === "form" && card.action === "create_booking" && opts?.hints && card.missing?.length === 1 && card.missing[0] === "period_id") {
          const room = Number(formValue(card, "room"));
          const date = String(formValue(card, "date") ?? "");
          if (room > 0 && date) {
            const period = await resolvePeriod(room, date, opts.hints);
            if (period) card = await helperApi.card(action, { ...args, room: String(room), date, period_id: period });
          }
        }
        if (opts?.replaces) useHelperStore.getState().updateCard(opts.replaces, { phase: "parked" });
        const key = pushServerCard(card, { hints: opts?.hints, step: card.type === "choice" ? opts?.step ?? 1 : undefined });
        if (card.type === "form") trackHelper({ kind: "form_open", action: card.action });
        focusEntry(key);
      } catch (err) {
        const key = pushRefusal(err);
        if (key) focusEntry(key);
      } finally {
        useHelperStore.getState().setTurn({ busy: false });
      }
    },
    [pushRefusal, pushServerCard],
  );

  const ask = useCallback<Runner["ask"]>(
    async (raw, opts) => {
      const text = raw.trim();
      if (!text) return;
      const st = useHelperStore.getState();
      st.pushUser(text);
      const waiting = st.entries.some((e) => e.kind === "card" && e.phase === "pending" && e.card.type === "confirm");
      if (waiting && isTypedYes(text)) {
        st.pushNote(both("helper.card.typedYes"));
        return;
      }
      st.setTurn({ busy: true, tools: [], draft: "", error: null, fallback: null });
      let answered = false;
      let turnId: string | undefined;
      try {
        await streamTurn(text, locale as Locale, (e) => {
          const s = useHelperStore.getState();
          switch (e.type) {
            case "run_started":
              turnId = e.turnId || undefined;
              break;
            case "tool_start":
              s.setTurn((t) => ({ tools: [...t.tools, { name: e.name, state: "pending" }] }));
              break;
            case "tool":
              s.setTurn((t) => {
                const i = t.tools.findIndex((x) => x.name === e.name && x.state === "pending");
                const state = e.ok ? ("ok" as const) : ("failed" as const);
                return { tools: i >= 0 ? t.tools.map((x, k) => (k === i ? { ...x, state } : x)) : [...t.tools, { name: e.name, state }] };
              });
              break;
            case "text":
              s.setTurn({ draft: e.text });
              break;
            case "card":
              answered = true;
              s.pushCard(e.card, { turnId });
              if (e.card.type === "form") trackHelper({ kind: "form_open", action: e.card.action, ...(turnId ? { turn_id: turnId } : {}) });
              if (e.card.type === "answer") s.setTurn({ draft: "" });
              break;
            case "bad_card":
              answered = true;
              s.pushFallback();
              break;
            case "run_finished":
              s.setTurn({ fallback: e.fallback });
              break;
            case "error":
              s.setTurn({ error: both("helper.error.provider") });
              break;
            default:
              break;
          }
        }, { context: opts?.context ?? undefined });
      } catch (err) {
        // could not start (429 limit, 403, the network): the server's card or its message, in the log
        pushRefusal(err);
        answered = true;
      } finally {
        const s = useHelperStore.getState();
        if (!answered && !s.turn.error) s.setTurn({ error: both("helper.error.provider") });
        s.setTurn({ busy: false, tools: [] });
      }
    },
    [locale, pushRefusal],
  );

  const undoImpl = useCallback(
    async (entry: CardEntry) => {
      if (entry.card.type !== "result" || !entry.card.undo_token || entry.undone) return;
      const st = useHelperStore.getState();
      st.updateCard(entry.key, { phase: "busy", notice: null });
      try {
        const out = await helperApi.undo(entry.card.undo_token);
        invalidateAfterHelperWrite(qc, entry.card.action);
        useHelperStore.getState().updateCard(entry.key, { phase: "done", undone: true });
        const key = pushServerCard(out, { undone: true });
        focusEntry(key);
        toast(translate(locale as Locale, "helper.card.undone"));
      } catch (err) {
        const r = helperRefusal(err);
        invalidateAfterHelperWrite(qc, entry.card.action);
        useHelperStore.getState().updateCard(entry.key, { phase: "done", undone: r.code === "already_undone", notice: r.tr || r.en ? { tr: r.tr ?? "", en: r.en ?? "" } : both("helper.error.provider") });
        focusEntry(entry.key);
      }
    },
    [locale, pushServerCard, qc],
  );

  const confirm = useCallback<Runner["confirm"]>(
    async (entry, event) => {
      if (entry.card.type !== "confirm" || entry.phase === "busy") return;
      if (!activation.trusted(event)) return;
      const st = useHelperStore.getState();
      if (Date.parse(entry.card.expires_at) <= Date.now()) {
        st.updateCard(entry.key, { phase: "expired" });
        return;
      }
      st.updateCard(entry.key, { phase: "busy", notice: null });
      try {
        const result = await helperApi.confirm(entry.card.token);
        invalidateAfterHelperWrite(qc, "action" in result && result.action ? result.action : entry.card.action);
        useHelperStore.getState().updateCard(entry.key, { phase: "done" });
        const key = pushServerCard(result);
        focusEntry(key);
        // HX-18 m6: while the sheet is open the log's polite region and the focused result line announce it; the
        // toast (with "Geri al") is only for a sheet that closed before the result came
        if (result.type === "result" && result.ok && !useHelperStore.getState().open) {
          const message = result.message[locale as Locale] ?? result.message.tr;
          const fresh = useHelperStore.getState().entries.find((e) => e.key === key) as CardEntry | undefined;
          if (result.undo_token && fresh) toast(message, { duration: 8000, action: { label: translate(locale as Locale, "helper.card.undo"), onClick: () => void undoImpl(fresh) } });
          else toast(message, { duration: 8000 });
        }
      } catch (err) {
        const r = helperRefusal(err);
        const s = useHelperStore.getState();
        if (r.status === 410 || r.code === "expired") s.updateCard(entry.key, { phase: "expired" });
        else if (r.status === 409 && r.code === "changed" && r.card) {
          s.updateCard(entry.key, { phase: "parked" });
          const key = s.pushCard(r.card, { notice: both("helper.card.changed") });
          focusEntry(key);
        } else if (r.status === 409 && r.code === "already_done") {
          s.updateCard(entry.key, { phase: "done", notice: both("helper.card.alreadyDone") });
        } else if (r.status === 403) {
          s.updateCard(entry.key, { phase: "cancelled", notice: r.tr || r.en ? { tr: r.tr ?? "", en: r.en ?? "" } : both("helper.card.gone") });
        } else if (r.status === 0) {
          s.updateCard(entry.key, { phase: "pending", notice: both("helper.card.network") });
        } else {
          // a conflict ("Bu saat az önce doldu.") or another refusal: the message stays on the card, which keeps its inputs
          s.updateCard(entry.key, { phase: "pending", notice: r.tr || r.en ? { tr: r.tr ?? r.en ?? "", en: r.en ?? r.tr ?? "" } : both("helper.error.provider") });
          if (r.card && r.card.type !== "confirm") s.pushCard(r.card);
        }
        focusEntry(entry.key);
      }
    },
    [locale, pushServerCard, qc, undoImpl],
  );

  const undo = useCallback<Runner["undo"]>(
    async (entry, event) => {
      if (event && !activation.trusted(event)) return;
      await undoImpl(entry);
    },
    [undoImpl],
  );

  const refresh = useCallback<Runner["refresh"]>(
    async (entry) => {
      const c = entry.card;
      if (!("action" in c) || !c.action) return;
      const args = c.type === "confirm" || c.type === "choice" ? c.args ?? {} : {};
      await runAction(c.action, args as ActionArgs, { hints: entry.hints, replaces: entry.key });
    },
    [runAction],
  );

  const cancel = useCallback<Runner["cancel"]>((entry) => {
    useHelperStore.getState().updateCard(entry.key, { phase: "cancelled" });
    // HX-18 M2: "Vazgeç" unmounts the focused button; the focus goes to the card's "Vazgeçildi." line
    focusEntry(entry.key);
    if (entry.card.type === "confirm") trackHelper({ kind: "cancel", action: entry.card.action, ...(entry.turnId ? { turn_id: entry.turnId } : {}) });
  }, []);

  return useMemo(() => ({ ask, runAction, confirm, undo, refresh, cancel }), [ask, runAction, confirm, undo, refresh, cancel]);
}
