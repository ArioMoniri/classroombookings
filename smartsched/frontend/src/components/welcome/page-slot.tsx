"use client";
/**
 * The guide's slot at the top of a page (one mount line in the app shell, above the page content): the inline hint
 * strip on the feature's own page (`/admin/ai`, `/admin/ops`, `/admin/integrations`, `/my-bookings`), the phone hint
 * card (`/bookings` for quick reserve). The "Başlarken" card on the audience's home (`/dashboard`, `/reserve`,
 * `/admin`) is `WelcomeHomeCardSlot`, below the page. Nothing while the sheet or the tour is open.
 */
import { usePathname } from "next/navigation";
import { useMediaQuery } from "@/components/ui/use-media-query";
import { useHydrated } from "@/lib/use-hydrated";
import { CHECKLIST_HOMES } from "./content";
import { ChecklistHomeCard } from "./checklist/checklist-home-card";
import { HintStrip } from "./hints/hint-strip";
import { useEligibleHints } from "./hints/registry";
import { useWelcomeStore } from "./welcome-store";

export function WelcomePageSlot() {
  const pathname = usePathname();
  const hydrated = useHydrated();
  const desktop = useMediaQuery("(min-width: 1024px)");
  const busy = useWelcomeStore((s) => !!s.sheet || !!s.tour);
  const hints = useEligibleHints();
  if (!hydrated || busy) return null;
  const hint = hints.find((h) => h.def.pages.includes(pathname) || (!desktop && h.def.phonePage === pathname));
  return hint ? <HintStrip hint={hint} /> : null;
}

/**
 * HX12B-F10 (fix-h-2026-10-18): the "Başlarken" card comes after the page's own task, never above its title, and only
 * on desktop. On a phone the list is the first row of "Daha" (welcome-guide.md §4.3), so the first screen stays the
 * page itself. Mounted by the app shell below the page content.
 */
export function WelcomeHomeCardSlot() {
  const pathname = usePathname();
  const hydrated = useHydrated();
  const desktop = useMediaQuery("(min-width: 1024px)");
  const busy = useWelcomeStore((s) => !!s.sheet || !!s.tour);
  if (!hydrated || busy || !desktop || !CHECKLIST_HOMES.includes(pathname)) return null;
  return <ChecklistHomeCard />;
}
