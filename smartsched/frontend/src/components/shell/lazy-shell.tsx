"use client";
/**
 * F-CH-1 (fix-c-2026-10-18): the shell parts that are not needed for the first paint, each in its own chunk.
 *
 * - The command palette (cmdk and the helper's palette groups) and the shortcuts sheet are fetched the first
 *   time the person opens them (⌘K, the search field, "?"), then stay mounted for their close animation and the
 *   next open.
 * - The welcome guide (sheet, hero, checklist, hints; welcome-guide.md), its page slot and the privacy notice gate
 *   decide from the API whether to show anything; they are fetched after hydration (no SSR, as before: each of
 *   them rendered nothing until hydrated).
 */
import dynamic from "next/dynamic";
import { useState } from "react";
import { useUiStore } from "@/stores/ui";

const CommandPalette = dynamic(() => import("./command-palette").then((m) => m.CommandPalette), { ssr: false });
const ShortcutsSheet = dynamic(() => import("./shortcuts-sheet").then((m) => m.ShortcutsSheet), { ssr: false });

export const LazyWelcomeProvider = dynamic(() => import("@/components/welcome/welcome-provider").then((m) => m.WelcomeProvider), { ssr: false });
export const LazyWelcomePageSlot = dynamic(() => import("@/components/welcome/page-slot").then((m) => m.WelcomePageSlot), { ssr: false });
// HX12B-F10: the "Başlarken" home card, below the page (same chunk as the slot)
export const LazyWelcomeHomeCardSlot = dynamic(() => import("@/components/welcome/page-slot").then((m) => m.WelcomeHomeCardSlot), { ssr: false });
export const LazyPrivacyNoticeGate = dynamic(() => import("@/components/privacy/notice-gate").then((m) => m.PrivacyNoticeGate), { ssr: false });

/** true from the first time `open` is true (render-time latch, no extra frame) */
function useOpenedOnce(open: boolean): boolean {
  const [opened, setOpened] = useState(open);
  if (open && !opened) setOpened(true);
  return opened || open;
}

export function LazyCommandPalette() {
  const opened = useOpenedOnce(useUiStore((s) => s.paletteOpen));
  return opened ? <CommandPalette /> : null;
}

export function LazyShortcutsSheet() {
  const opened = useOpenedOnce(useUiStore((s) => s.shortcutsOpen));
  return opened ? <ShortcutsSheet /> : null;
}
