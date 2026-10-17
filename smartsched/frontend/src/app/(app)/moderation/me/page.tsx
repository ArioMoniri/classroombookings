import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { MyRequests } from "@/components/moderation/moderation-console";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("moderation.mine.title");

/** Taleplerim: the signed-in academician's own planning requests (GET /moderation/me, Q11 own-only) */
export default function MyRequestsPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <MyRequests />
      </HydrationGate>
    </Suspense>
  );
}
