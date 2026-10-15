"use client";
/**
 * "N değişiklik yayında değil" (moderation spec §5.1): the requests the coordinator changed since the last
 * re-solve, per term, in this browser. They seed the re-solve's `changed_request_ids` (a repair frees their
 * neighbourhood). The backend has no `changes-since-publish` read yet (P19-M-07), so this is local state.
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { addStaged, type StagedChange } from "./moderation-model";

interface StagedState {
  byTerm: Record<string, StagedChange[]>;
  add: (termId: number, change: StagedChange) => void;
  remove: (termId: number, at: string) => void;
  clear: (termId: number) => void;
}

export const useStagedStore = create<StagedState>()(
  persist(
    (set) => ({
      byTerm: {},
      add: (termId, change) => set((s) => ({ byTerm: { ...s.byTerm, [termId]: addStaged(s.byTerm[termId] ?? [], change) } })),
      remove: (termId, at) => set((s) => ({ byTerm: { ...s.byTerm, [termId]: (s.byTerm[termId] ?? []).filter((c) => c.at !== at) } })),
      clear: (termId) => set((s) => ({ byTerm: { ...s.byTerm, [termId]: [] } })),
    }),
    { name: "smartsched.moderation.staged" },
  ),
);

const NONE: StagedChange[] = [];
export function useStaged(termId: number | null): StagedChange[] {
  return useStagedStore((s) => (termId === null ? NONE : (s.byTerm[termId] ?? NONE)));
}
