import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { PublicRoomView } from "@/components/public-schedule/public-views";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("publicSchedule.roomTitle");

/** /public/rooms/A101?date=YYYY-MM-DD: one room's day, kiosk-sized, refreshed every 60 s. */
export default async function PublicRoomPage({ params }: { params: Promise<{ code: string }> }) {
  const { code } = await params;
  return (
    <Suspense fallback={null}>
      <HydrationGate fallback={null}>
        <PublicRoomView code={decodeURIComponent(code)} />
      </HydrationGate>
    </Suspense>
  );
}
