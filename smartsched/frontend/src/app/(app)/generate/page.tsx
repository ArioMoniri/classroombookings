import { localizedTitle } from "@/lib/i18n/server";
import { HydrationGate } from "@/components/common/hydration-gate";
import { Suspense } from "react";
import { StudioView } from "@/components/studio/studio-view";

export const generateMetadata = localizedTitle("titles.generate");

export default function GeneratePage() {
  return (
    <Suspense>
      <HydrationGate>
        <StudioView />
      </HydrationGate>
    </Suspense>
  );
}
