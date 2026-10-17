import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { PublicIndexView } from "@/components/public-schedule/public-views";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("publicSchedule.indexTitle");

/** /public: the buildings and rooms the public day view shows (404 page while an administrator has it off). */
export default function PublicIndexPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate fallback={null}>
        <PublicIndexView />
      </HydrationGate>
    </Suspense>
  );
}
