import type { Metadata } from "next";
import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { OnboardingFlow } from "@/components/onboarding/onboarding-flow";

export const metadata: Metadata = { title: "Onboarding" };

export default function OnboardingPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <OnboardingFlow />
      </HydrationGate>
    </Suspense>
  );
}
