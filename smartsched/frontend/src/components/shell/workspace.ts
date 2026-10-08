"use client";
/**
 * Workspace memory (planner usability M1): the term, run and week each user last worked on.
 *
 * - Stored per user in localStorage (`smartsched.workspace`, keyed by user id). The backend has no
 *   per-user preference endpoint yet (`/auth/profile` carries identity only), so this is client-side;
 *   ROADMAP has the backend item.
 * - The default term is the **current term by date** (`currentTermByDate`), not the last imported one.
 * - `useUiStore.termId` stays the single runtime source for existing consumers; this store only remembers.
 *
 * Calendar / rooms views: read `useRememberedRun(termId)` and `useRememberedWeek(runId)`, and call their
 * setters when the planner changes run or week, so the timetable opens where he left off.
 */
import { useCallback, useEffect } from "react";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { Term } from "@/lib/api/schemas";

type UserMemory = {
  termId?: number;
  /** termId → runId */
  runByTerm?: Record<string, number>;
  /** runId → week index */
  weekByRun?: Record<string, number>;
};

interface WorkspaceState {
  users: Record<string, UserMemory>;
  remember: (userKey: string, patch: (m: UserMemory) => UserMemory) => void;
}

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set) => ({
      users: {},
      remember: (userKey, patch) => set((s) => ({ users: { ...s.users, [userKey]: patch(s.users[userKey] ?? {}) } })),
    }),
    { name: "smartsched.workspace", version: 1 },
  ),
);

/* The signed-in user, published by the shell (AppShell → WorkspaceUser) so hooks need no prop drilling. */
interface UserKeyState {
  userKey: string;
  setUserKey: (k: string) => void;
}
export const useWorkspaceUser = create<UserKeyState>()((set) => ({ userKey: "anon", setUserKey: (userKey) => set({ userKey }) }));

const DAY = 86_400_000;

function parseDay(iso: string): number {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return Date.UTC(y ?? 1970, (m ?? 1) - 1, d ?? 1);
}

/** Inclusive date range of a term: `end_date`, or `start_date + week_count` weeks. */
export function termRange(t: Pick<Term, "start_date" | "end_date" | "week_count">): { start: number; end: number } {
  const start = parseDay(t.start_date);
  const end = t.end_date ? parseDay(t.end_date) : start + Math.max(1, t.week_count) * 7 * DAY - DAY;
  return { start, end };
}

/**
 * The term a planner means by "now":
 * 1. a term whose dates contain today (a regular term wins over an exam period that overlaps it);
 * 2. otherwise the next term that starts within 45 days;
 * 3. otherwise the most recently ended **regular** term (an exam period belongs to its teaching term);
 * 4. otherwise the most recently ended term of any kind, else the first one.
 */
export function currentTermByDate<T extends Pick<Term, "id" | "kind" | "start_date" | "end_date" | "week_count">>(terms: T[], today: Date = new Date()): T | undefined {
  if (terms.length === 0) return undefined;
  const now = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  const regular = (t: T) => t.kind === "REGULAR" || t.kind === "SUMMER";
  const withRange = terms.map((t) => ({ t, ...termRange(t) }));
  const containing = withRange.filter((x) => x.start <= now && now <= x.end);
  if (containing.length) return (containing.find((x) => regular(x.t)) ?? containing[0])?.t;
  const upcoming = withRange.filter((x) => x.start > now && x.start - now <= 45 * DAY).sort((a, b) => a.start - b.start);
  if (upcoming[0]) return upcoming[0].t;
  const past = withRange.filter((x) => x.end < now).sort((a, b) => b.end - a.end);
  return (past.find((x) => regular(x.t)) ?? past[0] ?? withRange[0])?.t;
}

/** The week index of `today` inside a term (1-based), clamped to the term; `undefined` before it starts. */
export function weekOfTerm(t: Pick<Term, "start_date" | "end_date" | "week_count">, today: Date = new Date()): number | undefined {
  const { start } = termRange(t);
  const now = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
  if (now < start) return undefined;
  return Math.min(Math.max(1, t.week_count), Math.floor((now - start) / (7 * DAY)) + 1);
}

export function useRememberedTermId(): [number | undefined, (id: number) => void] {
  const userKey = useWorkspaceUser((s) => s.userKey);
  const termId = useWorkspaceStore((s) => s.users[userKey]?.termId);
  const remember = useWorkspaceStore((s) => s.remember);
  const set = useCallback((id: number) => remember(userKey, (m) => ({ ...m, termId: id })), [remember, userKey]);
  return [termId, set];
}

/** The run this user last opened for `termId` (calendar, run report, dashboard). */
export function useRememberedRun(termId: number | undefined): [number | undefined, (runId: number) => void] {
  const userKey = useWorkspaceUser((s) => s.userKey);
  const runId = useWorkspaceStore((s) => (termId === undefined ? undefined : s.users[userKey]?.runByTerm?.[String(termId)]));
  const remember = useWorkspaceStore((s) => s.remember);
  const set = useCallback(
    (id: number) => {
      if (termId === undefined) return;
      remember(userKey, (m) => ({ ...m, runByTerm: { ...m.runByTerm, [String(termId)]: id } }));
    },
    [remember, userKey, termId],
  );
  return [runId, set];
}

/** The week this user last looked at in `runId`. */
export function useRememberedWeek(runId: number | null | undefined): [number | undefined, (week: number) => void] {
  const userKey = useWorkspaceUser((s) => s.userKey);
  const week = useWorkspaceStore((s) => (runId == null ? undefined : s.users[userKey]?.weekByRun?.[String(runId)]));
  const remember = useWorkspaceStore((s) => s.remember);
  const set = useCallback(
    (w: number) => {
      if (runId == null) return;
      remember(userKey, (m) => ({ ...m, weekByRun: { ...m.weekByRun, [String(runId)]: w } }));
    },
    [remember, userKey, runId],
  );
  return [week, set];
}

/** Remember the run of a page the planner opened (run report). */
export function useRememberRunOnView(termId: number | undefined, runId: number | undefined) {
  const [, setRun] = useRememberedRun(termId);
  useEffect(() => {
    if (runId !== undefined) setRun(runId);
  }, [runId, setRun]);
}

/** The week this user last looked at on the dashboard of `termId` (kept apart from run weeks). */
export function useRememberedTermWeek(termId: number | undefined): [number | undefined, (week: number) => void] {
  const userKey = useWorkspaceUser((s) => s.userKey);
  const key = termId === undefined ? undefined : `term:${termId}`;
  const week = useWorkspaceStore((s) => (key === undefined ? undefined : s.users[userKey]?.weekByRun?.[key]));
  const remember = useWorkspaceStore((s) => s.remember);
  const set = useCallback(
    (w: number) => {
      if (key === undefined) return;
      remember(userKey, (m) => ({ ...m, weekByRun: { ...m.weekByRun, [key]: w } }));
    },
    [remember, userKey, key],
  );
  return [week, set];
}
