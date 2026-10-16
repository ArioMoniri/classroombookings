import { localizedTitle } from "@/lib/i18n/server";
import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { OnboardingFlow } from "@/components/onboarding/onboarding-flow";

export const generateMetadata = localizedTitle("titles.onboarding");

export default function OnboardingPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <OnboardingFlow />
      </HydrationGate>
    </Suspense>
  );
}
