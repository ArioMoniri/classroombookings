import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { PublicBuildingView } from "@/components/public-schedule/public-views";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("publicSchedule.buildingTitle");

/** /public/buildings/A?date=YYYY-MM-DD: every room of a building that day, with now / next per room. */
export default async function PublicBuildingPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  return (
    <Suspense fallback={null}>
      <HydrationGate fallback={null}>
        <PublicBuildingView code={decodeURIComponent(code)} />
      </HydrationGate>
    </Suspense>
  );
}
