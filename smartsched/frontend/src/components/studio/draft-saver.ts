import { DraftConflictError } from "@/lib/api/studio-endpoints";
import type { Draft } from "@/lib/api/studio-schemas";
import { patchFor, type DraftField } from "./studio-reducer";
import type { StudioStore } from "./studio-store";

type Patch = ReturnType<typeof patchFor>;

/**
 * The Studio's draft autosave, single flight. The autosave timer and a flush (the pre-check, a step change) can both
 * ask while a save is in flight. Two loops woken by the same answer used to resend the same version next to each
 * other, got a 409 and left the edit dirty with the status stuck on "Kaydediliyor…" (pod e2e #125, integrity-r1 #4 /
 * R1-M-12). Now a caller joins the running loop, and the loop sends what was edited meanwhile right after the answer.
 */
export function createDraftSaver(store: StudioStore, save: (version: number, patch: Patch) => Promise<Draft>, onSaved?: (d: Draft) => void): () => Promise<void> {
  let inflight: Promise<void> | null = null;
  return async () => {
    if (inflight) return inflight;
    const loop = (async () => {
      for (let round = 0; round < 10; round++) {
        const s = store.getState().studio;
        if (!s.server || s.dirty.length === 0 || s.status === "conflict" || (round > 0 && s.status !== "idle")) return;
        const sent: DraftField[] = [...s.dirty];
        const sentEdits = { ...s.edits };
        const { dispatch } = store.getState();
        dispatch({ type: "saving" });
        try {
          const d = await save(s.server.version, patchFor(s.local, sent));
          dispatch({ type: "saved", draft: d, sent, sentEdits });
          onSaved?.(d);
        } catch (e) {
          if (e instanceof DraftConflictError) dispatch({ type: "conflict", current: e.current });
          else dispatch({ type: "saveFailed", error: e instanceof Error ? e.message : String(e) });
        }
      }
    })();
    inflight = loop;
    try {
      await loop;
    } finally {
      if (inflight === loop) inflight = null;
    }
  };
}
