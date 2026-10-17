"use client";
/**
 * The welcome guide's UI state, shared by the shell mounts (user menu › Yardım, ⌘K, the sidebar pill, the phone
 * "Daha" rows) and the provider that renders the surfaces. Nothing here is persisted: progress lives on the server
 * (`welcome_progress`), and the one-auto-surface-per-session flag lives in sessionStorage (`ss.welcome.auto`).
 */
import { create } from "zustand";
import type { Audience } from "@/lib/api/welcome";
import type { ResolvedStep } from "./model";

export type SheetRequest =
  | { mode: "auto" | "restart"; kind: "sheet" | "delta"; deltaAudiences?: string[] }
  | { mode: "preview"; kind: "sheet"; audience: Audience; overrides?: Record<string, string> };

export interface TourRequest {
  steps: ResolvedStep[];
  /** admin preview: no events are written */
  preview?: boolean;
}

interface WelcomeUi {
  sheet: SheetRequest | null;
  tour: TourRequest | null;
  /** the checklist panel (desktop popover) or full-screen list (phones) */
  checklistOpen: boolean;
  /** hints closed in this tab before the server's `seen` comes back */
  dismissedHints: string[];
  /** items marked done in this tab before the refetch lands */
  localDone: string[];
  openSheet: (req: SheetRequest) => void;
  closeSheet: () => void;
  startTour: (req: TourRequest) => void;
  endTour: () => void;
  setChecklistOpen: (open: boolean) => void;
  dismissHint: (key: string) => void;
  markLocalDone: (key: string) => void;
}

export const useWelcomeStore = create<WelcomeUi>()((set) => ({
  sheet: null,
  tour: null,
  checklistOpen: false,
  dismissedHints: [],
  localDone: [],
  openSheet: (req) => set({ sheet: req, checklistOpen: false }),
  closeSheet: () => set({ sheet: null }),
  startTour: (req) => set({ tour: req, sheet: null, checklistOpen: false }),
  endTour: () => set({ tour: null }),
  setChecklistOpen: (open) => set({ checklistOpen: open }),
  dismissHint: (key) => set((s) => ({ dismissedHints: s.dismissedHints.includes(key) ? s.dismissedHints : [...s.dismissedHints, key] })),
  markLocalDone: (key) => set((s) => ({ localDone: s.localDone.includes(key) ? s.localDone : [...s.localDone, key] })),
}));

/** sessionStorage key of the "one automatic interruption per session" budget (spec §6.1). */
export const AUTO_KEY = "ss.welcome.auto";
export function autoBudgetFree(): boolean {
  try {
    return window.sessionStorage.getItem(AUTO_KEY) === null;
  } catch {
    return true;
  }
}
export function spendAutoBudget(what: string): void {
  try {
    window.sessionStorage.setItem(AUTO_KEY, what);
  } catch {
    /* private mode: the server's single `show` still limits it */
  }
}

/** Another modal dialog, sheet or alert is open (the guide never auto-shows over one, spec §6.2). */
export function otherDialogOpen(): boolean {
  if (typeof document === "undefined") return false;
  return !!document.querySelector('[role="dialog"][aria-modal="true"]:not([data-welcome]), [role="alertdialog"]:not([data-welcome])');
}

/** Focus the page's heading (focus never falls to <body> after an action). Retries while a route renders. */
export function focusPageHeading(timeoutMs = 2000): void {
  if (typeof window === "undefined") return;
  const started = performance.now();
  const tick = () => {
    const h = document.querySelector<HTMLElement>("main h1") ?? document.querySelector<HTMLElement>("#main");
    if (h) {
      if (!h.hasAttribute("tabindex")) h.setAttribute("tabindex", "-1");
      h.focus({ preventScroll: false });
      if (document.activeElement === h) return;
    }
    if (performance.now() - started < timeoutMs) window.setTimeout(tick, 80);
  };
  window.setTimeout(tick, 0);
}

/** Open the existing "Yenilikler" sheet (its header button owns the sheet; we press the visible one). */
export function openWhatsNew(): void {
  const buttons = [...document.querySelectorAll<HTMLElement>('[data-testid="whats-new"]')];
  const visible = buttons.find((b) => b.offsetParent !== null) ?? buttons[0];
  visible?.click();
}
