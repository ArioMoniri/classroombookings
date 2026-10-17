import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { ModerationConsole } from "@/components/moderation/moderation-console";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("moderation.title");

/** Moderasyon (Phase 19 F1/F2): /moderation?tab=classes|people|requests|preferences|matchings */
export default function ModerationPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <ModerationConsole />
      </HydrationGate>
    </Suspense>
  );
}
