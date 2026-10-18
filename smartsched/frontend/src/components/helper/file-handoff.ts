"use client";
/**
 * HB-23c (helper-file-router.md §6.3, §6.5): the file hand-over from the helper's card to a target page.
 *
 * - {@link fileHandoffHref}: `feature_id` + the server's params → the page's address. The address only ever says
 *   `from=helper` (plus the kind, term and year the page reads); **the upload token is never in it**.
 * - {@link useFileHandoffStore}: the one hand-over slot (token, stage id, file name and size from the browser's File, the
 *   kind and params), mirrored to `sessionStorage` so a reload keeps it. Never `localStorage`, never the URL.
 * - Several files (owner decision: one card that opens /onboarding with all) travel as the browser's File objects in
 *   memory (no stage): the setup wizard uploads them itself, so nothing is sent twice.
 * - {@link useHelperFileHandoff}: what a target page reads: the hand-over meant for it, whether it expired (10 min), and
 *   `remove()` (✕ "Dosyayı kaldır": `DELETE /helper/files/{sid}`) / `consumed()` (the page sent the token).
 */
import { useEffect, useState } from "react";
import { create } from "zustand";
import { dropStage } from "@/lib/api/helper-files";
import { featureHref } from "./feature-links";

export interface HandedItem {
  /** the stage's upload token; null for a file carried in memory only (several files) */
  token: string | null;
  sid: string | null;
  /** from the browser's File object (the server never echoes the name) */
  name: string;
  size: number;
  format: string | null;
  /** epoch ms; null without a stage */
  expiresAt: number | null;
}

export type HandoffParams = Record<string, string | number | boolean>;

export interface FileHandoff {
  featureId: string;
  kind: string | null;
  params: HandoffParams;
  items: HandedItem[];
  at: number;
}

export const HANDOFF_STORAGE_KEY = "smartsched.helper.fileHandoff";

/** the browser's File objects of the current hand-over (memory only; gone after a reload) */
const memory = new Map<string, File>();
const fileKey = (name: string, size: number) => `${name}:${size}`;

function readSession(): FileHandoff | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(HANDOFF_STORAGE_KEY);
    if (!raw) return null;
    const v = JSON.parse(raw) as FileHandoff;
    return v && typeof v.featureId === "string" && Array.isArray(v.items) ? v : null;
  } catch {
    return null;
  }
}

function writeSession(v: FileHandoff | null) {
  if (typeof window === "undefined") return;
  try {
    if (v) window.sessionStorage.setItem(HANDOFF_STORAGE_KEY, JSON.stringify(v));
    else window.sessionStorage.removeItem(HANDOFF_STORAGE_KEY);
  } catch {
    /* private mode: the slot still works in memory */
  }
}

interface HandoffState {
  handoff: FileHandoff | null;
  set: (h: FileHandoff, files?: readonly File[]) => void;
  clear: () => void;
}

export const useFileHandoffStore = create<HandoffState>()((set) => ({
  handoff: readSession(),
  set: (h, files = []) => {
    memory.clear();
    for (const f of files) memory.set(fileKey(f.name, f.size), f);
    writeSession(h);
    set({ handoff: h });
  },
  clear: () => {
    memory.clear();
    writeSession(null);
    set({ handoff: null });
  },
}));

/** The in-memory File of a handed item (several-files hand-over, or a re-read), or null after a reload. */
export const handedFile = (item: Pick<HandedItem, "name" | "size">): File | null => memory.get(fileKey(item.name, item.size)) ?? null;

export const isItemExpired = (item: HandedItem, now = Date.now()): boolean => item.token !== null && item.expiresAt !== null && now >= item.expiresAt;

const IMPORTER_KINDS: ReadonlySet<string> = new Set(["planning-list", "exam-list", "weekly-grid", "room-master", "crbs"]);
const int = (v: unknown): number | null => {
  const n = typeof v === "number" ? v : typeof v === "string" && /^\d{1,6}$/.test(v) ? Number(v) : NaN;
  return Number.isInteger(n) && n > 0 ? n : null;
};

/**
 * The target page's address for a file route (§6.5). Only the page's own params, validated; never a token. A feature
 * without a file hand-over opens its plain route (`profile.calendar` its "Takvimime ekle" sheet).
 */
export function fileHandoffHref(featureId: string, params: HandoffParams = {}): string | null {
  switch (featureId) {
    case "import": {
      const q = new URLSearchParams();
      const kind = typeof params.kind === "string" && IMPORTER_KINDS.has(params.kind) ? params.kind : null;
      if (kind) q.set("kind", kind);
      const term = int(params.term_id);
      if (term) q.set("term", String(term));
      const year = int(params.year);
      if (year && year >= 2000 && year <= 2100) q.set("year", String(year));
      q.set("from", "helper");
      return `/import?${q}`;
    }
    case "onboarding":
      return "/onboarding?from=helper";
    case "admin.users":
      return "/admin/users?import=1&from=helper";
    case "profile.calendar":
      return "/profile?calendar=1";
    default:
      return featureHref(featureId);
  }
}

/**
 * The hand-over a target page should show (its `featureId`, and for /import the kind it is on), with the expiry
 * line once the 10 minutes pass. `remove()` deletes the stage; `consumed()` forgets it after the page used the token.
 */
export function useHelperFileHandoff(featureId: string, opts: { kind?: string | null } = {}) {
  const raw = useFileHandoffStore((s) => s.handoff);
  const matches = !!raw && raw.featureId === featureId && (opts.kind === undefined || raw.params.kind === opts.kind);
  const handoff = matches ? raw : null;
  const [now, setNow] = useState(() => Date.now());
  const next = handoff ? Math.min(...handoff.items.map((i) => (i.token && i.expiresAt ? i.expiresAt : Infinity))) : Infinity;
  useEffect(() => {
    if (!Number.isFinite(next)) return;
    const id = window.setTimeout(() => setNow(Date.now()), Math.max(0, next - Date.now()) + 50);
    return () => window.clearTimeout(id);
  }, [next]);
  const [gone, setGone] = useState(false);
  const expired = !!handoff && (gone || handoff.items.some((i) => isItemExpired(i, now)));
  return {
    handoff,
    expired,
    /** the server said 410 (used / expired) on the page's own upload */
    markExpired: () => setGone(true),
    remove: () => {
      for (const i of handoff?.items ?? []) if (i.token) dropStage({ upload_token: i.token, sid: i.sid ?? undefined });
      useFileHandoffStore.getState().clear();
      setGone(false);
    },
    consumed: () => {
      useFileHandoffStore.getState().clear();
      setGone(false);
    },
  };
}
