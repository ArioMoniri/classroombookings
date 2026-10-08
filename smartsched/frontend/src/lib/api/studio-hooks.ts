"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "./endpoints";
import type { StudioKind } from "./studio-schemas";

/** Query keys: everything for one draft lives under ["studio", termId, kind]. */
export const sk = {
  all: (termId: number, kind: StudioKind) => ["studio", termId, kind] as const,
  draft: (termId: number, kind: StudioKind) => ["studio", termId, kind, "draft"] as const,
  summary: (termId: number, kind: StudioKind) => ["studio", termId, kind, "summary"] as const,
  classes: (termId: number, kind: StudioKind) => ["studio", termId, kind, "classes"] as const,
  rules: (termId: number, kind: StudioKind) => ["studio", termId, kind, "rules"] as const,
  meta: ["studio-meta"] as const,
  presets: (kind: StudioKind) => ["presets", kind] as const,
};

export function useStudioMeta() {
  return useQuery({ queryKey: sk.meta, queryFn: api.studio.meta, staleTime: Number.POSITIVE_INFINITY });
}
export function useStudioDraft(termId: number | undefined, kind: StudioKind) {
  return useQuery({ queryKey: sk.draft(termId ?? 0, kind), queryFn: () => api.studio.draft(termId ?? 0, kind), enabled: termId !== undefined, staleTime: Number.POSITIVE_INFINITY, retry: 1 });
}
export function useStudioSummary(termId: number | undefined, kind: StudioKind, version: number | undefined) {
  return useQuery({
    queryKey: [...sk.summary(termId ?? 0, kind), version ?? 0],
    queryFn: () => api.studio.summary(termId ?? 0, kind),
    enabled: termId !== undefined && version !== undefined,
    placeholderData: (prev) => prev,
  });
}
export function useStudioClasses(termId: number | undefined, kind: StudioKind) {
  return useQuery({ queryKey: sk.classes(termId ?? 0, kind), queryFn: () => api.studio.classes(termId ?? 0, kind), enabled: termId !== undefined, staleTime: 30_000 });
}
export function useStudioRules(termId: number | undefined, kind: StudioKind) {
  return useQuery({ queryKey: sk.rules(termId ?? 0, kind), queryFn: () => api.studio.rules(termId ?? 0, kind), enabled: termId !== undefined, placeholderData: (prev) => prev });
}
export function usePresets(kind: StudioKind) {
  return useQuery({ queryKey: sk.presets(kind), queryFn: () => api.presets.list(kind) });
}
/** Settings for the studio (AI key present, solver defaults). Planners get 403: no toast, just undefined. */
export function useSettingsPeek() {
  return useQuery({ queryKey: ["settings", "peek"], queryFn: api.settings.peek, retry: false, staleTime: 5 * 60_000 });
}
