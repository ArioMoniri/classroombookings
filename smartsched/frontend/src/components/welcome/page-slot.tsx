"use client";
/**
 * The guide's slot at the top of a page (one mount line in the app shell, above the page content): the inline hint
 * strip on the feature's own page (`/admin/ai`, `/admin/ops`, `/admin/integrations`, `/my-bookings`), the phone hint
 * card (`/bookings` for quick reserve), and the "Başlarken" card on the audience's home (`/dashboard`, `/reserve`,
 * `/admin`). Nothing while the sheet or the tour is open.
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
  return (
    <>
      {hint ? <HintStrip hint={hint} /> : null}
      {CHECKLIST_HOMES.includes(pathname) ? <ChecklistHomeCard /> : null}
    </>
  );
}
