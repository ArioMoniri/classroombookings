import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { HeatmapView } from "@/components/analytics/heatmap-view";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("analytics.title");

/** Doluluk ısı haritası: /analytics/heatmap?tab=rooms|instructors&source=live|run&run=&group=&scope=&week= */
export default function HeatmapPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <HeatmapView />
      </HydrationGate>
    </Suspense>
  );
}
