import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { CompareView } from "@/components/compare/compare-view";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("compare.title");

/** Senaryo karşılaştırma: /runs/compare?a=<baseline run>&b=<scenario run>[&week=][&tab=] */
export default function CompareRunsPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <CompareView />
      </HydrationGate>
    </Suspense>
  );
}
