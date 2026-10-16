"use client";
/**
 * The wizard's draft and its autosave (program-wizard spec §0, §9; backend `/program-drafts`). The draft lives on
 * the server; this hook keeps the local copy, saves 800 ms after the last edit as field ops
 * (`PATCH {ops, base_version, step}`), and carries the server's validation back. A save that finds a newer
 * version (someone else saved in between) reloads the draft and replays our unsaved edits on top; the fields
 * the server reports as `overwritten` become an info line. Unsaved edits are also kept in this browser, so an
 * offline edit or a closed tab is never lost: "Çevrimdışı · değişiklikler bu cihazda tutuluyor", synced on
 * reconnect. A committed or undone draft is read-only.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { HttpError } from "@/lib/api/client";
import { dk, draftsApi, type DraftOut, type DraftStatus, type Overwritten, type Validation } from "@/lib/api/program-drafts";
import { applyOps, deepEqual, diffOps, readPayload, type Payload, type Step } from "./wizard-model";

/** unsaved edits per draft id: what we last saw from the server (`acked` at `version`) and our local payload */
interface Pending {
  version: number;
  acked: Payload;
  local: Payload;
  at: string;
}
interface PendingStore {
  byId: Record<string, Pending>;
  put: (id: number, p: Pending) => void;
  drop: (id: number) => void;
}
export const usePendingStore = create<PendingStore>()(
  persist(
    (set) => ({
      byId: {},
      put: (id, p) => set((s) => ({ byId: { ...s.byId, [id]: p } })),
      drop: (id) =>
        set((s) => {
          const next = { ...s.byId };
          delete next[id];
          return { byId: next };
        }),
    }),
    { name: "smartsched.programDrafts.pending" },
  ),
);

export type SaveState =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved"; at: string }
  | { kind: "offline" }
  | { kind: "error"; message: string }
  | { kind: "readonly"; status: DraftStatus };

const DEBOUNCE_MS = 800;

export function errorText(e: unknown, lang: "tr" | "en" = "tr"): string {
  if (e instanceof HttpError) {
    const raw = e.detail as { detail?: unknown } | undefined;
    const body = raw && typeof raw === "object" && "detail" in raw ? raw.detail : raw;
    if (typeof body === "string") return body;
    if (body && typeof body === "object") {
      const b = body as Record<string, unknown>;
      if (lang === "tr" && typeof b.message_tr === "string") return b.message_tr;
      if (typeof b.message === "string") return b.message;
    }
    return e.message;
  }
  return e instanceof Error ? e.message : String(e);
}

const isOffline = (e: unknown) => (e instanceof HttpError && e.status === 0) || (typeof navigator !== "undefined" && navigator.onLine === false);

export interface WizardDraft {
  id: number;
  termId: number;
  status: DraftStatus;
  version: number;
  payload: Payload;
  validation: Validation;
  updatedBy: number | null;
  created: DraftOut["created"];
}

/** the draft `id`, its updater and the autosave state */
export function useWizard(id: number, initial: DraftOut) {
  const qc = useQueryClient();
  const putPending = usePendingStore((s) => s.put);
  const dropPending = usePendingStore((s) => s.drop);
  const [draft, setDraft] = useState<WizardDraft>(() => fromServer(initial));
  const [save, setSave] = useState<SaveState>(() => (initial.status !== "draft" ? { kind: "readonly", status: initial.status } : { kind: "idle" }));
  const [overwritten, setOverwritten] = useState<Overwritten[]>([]);
  // what the server holds, verbatim: the first save also writes the defaults a sparse payload lacks
  const acked = useRef<Payload>((initial.payload ?? {}) as unknown as Payload);
  const local = useRef<Payload>(draft.payload);
  const version = useRef<number>(initial.version);
  const step = useRef<Step | null>(null);
  const stepSent = useRef<string | null>(initial.step);
  const running = useRef(false);
  const again = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flushRef = useRef<() => Promise<boolean>>(async () => true);
  const readonly = initial.status !== "draft";

  const remember = useCallback(() => {
    if (deepEqual(acked.current, local.current)) dropPending(id);
    else putPending(id, { version: version.current, acked: acked.current, local: local.current, at: new Date().toISOString() });
  }, [id, putPending, dropPending]);

  const flush = useCallback(async (): Promise<boolean> => {
    if (readonly) return true;
    if (running.current) {
      again.current = true;
      return false;
    }
    running.current = true;
    let ok = true;
    try {
      for (let pass = 0; pass < 4; pass++) {
        again.current = false;
        const sent = local.current;
        const ops = diffOps(acked.current, sent);
        const wantStep = step.current && step.current !== stepSent.current ? step.current : undefined;
        if (!ops.length && !wantStep) break;
        setSave({ kind: "saving" });
        const base = version.current;
        const out = await draftsApi.patch(id, { ops: ops.length ? ops : undefined, base_version: base, step: wantStep });
        if (wantStep) stepSent.current = wantStep;
        let server: Payload = sent;
        let raw: Payload = sent;
        if (out.version !== base + 1) {
          // someone else saved in between: their fields are in the server payload, ours were merged on top
          const fresh = await draftsApi.get(id);
          raw = (fresh.payload ?? {}) as unknown as Payload;
          server = readPayload(fresh.payload);
        }
        acked.current = raw;
        version.current = out.version;
        const edited = !deepEqual(local.current, sent);
        if (edited) {
          local.current = applyOps(server, diffOps(sent, local.current));
          again.current = true;
        } else {
          local.current = server;
        }
        if (out.overwritten.length) setOverwritten(out.overwritten);
        setDraft((d) => ({ ...d, version: out.version, validation: out.validation, payload: local.current }));
        remember();
        if (!again.current) break;
      }
      setSave({ kind: "saved", at: new Date().toISOString() });
      void qc.invalidateQueries({ queryKey: ["program-drafts", "list"] });
    } catch (e) {
      ok = false;
      remember();
      setSave(isOffline(e) ? { kind: "offline" } : { kind: "error", message: errorText(e) });
    } finally {
      running.current = false;
      if (again.current && ok) {
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(() => void flushRef.current(), DEBOUNCE_MS);
      }
    }
    return ok;
  }, [id, qc, readonly, remember]);
  useEffect(() => {
    flushRef.current = flush;
  }, [flush]);

  // resume: unsaved edits of this browser are replayed onto the server's version (rebased when it moved on)
  const resumed = useRef(false);
  useEffect(() => {
    if (resumed.current || readonly) return;
    resumed.current = true;
    const p = usePendingStore.getState().byId[id];
    if (!p) {
      if (!deepEqual(acked.current, local.current)) void flush();
      return;
    }
    const rebased = p.version === version.current ? p.local : applyOps(readPayload(acked.current), diffOps(p.acked, p.local));
    local.current = rebased;
    setDraft((d) => ({ ...d, payload: rebased }));
    void flush();
  }, [id, flush, readonly]);

  // back online: send what was kept on this device
  useEffect(() => {
    const on = () => void flush();
    window.addEventListener("online", on);
    return () => window.removeEventListener("online", on);
  }, [flush]);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const update = useCallback(
    (fn: (p: Payload) => Payload) => {
      if (readonly) return;
      local.current = fn(local.current);
      setDraft((d) => ({ ...d, payload: local.current }));
      remember();
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => void flush(), DEBOUNCE_MS);
    },
    [flush, readonly, remember],
  );

  /** the step the coordinator is on ("Kaldığınız yer: Kohortlar"), saved with the next write */
  const setStep = useCallback(
    (s: Step) => {
      step.current = s;
      if (readonly) return;
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => void flush(), DEBOUNCE_MS);
    },
    [flush, readonly],
  );

  /** a fresh validation (per step on "Devam", or with the pre-check) without a write */
  const revalidate = useCallback(
    async (s?: Step, precheck = false): Promise<Validation | null> => {
      if (!(await flush())) return null;
      const v = await draftsApi.validate(id, s, precheck);
      if (!s) setDraft((d) => ({ ...d, validation: v }));
      return v;
    },
    [id, flush],
  );

  return { draft, update, save, flush, setStep, revalidate, overwritten, dismissOverwritten: () => setOverwritten([]) };
}

export function fromServer(d: DraftOut): WizardDraft {
  return { id: d.id, termId: d.term_id, status: d.status, version: d.version, payload: readPayload(d.payload), validation: d.validation, updatedBy: d.updated_by, created: d.created };
}

export const draftKey = dk.draft;
