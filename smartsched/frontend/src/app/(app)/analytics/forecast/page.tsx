import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { ForecastView } from "@/components/analytics/forecast-view";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("adaptive.forecast.title");

/** AS-16 Tahmin ve senaryo: room demand with calibrated ranges, short hours, what-if (+ optional draft run). */
export default function ForecastPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <ForecastView />
      </HydrationGate>
    </Suspense>
  );
}
