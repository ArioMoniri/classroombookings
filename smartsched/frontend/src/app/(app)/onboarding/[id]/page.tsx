import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { OnboardingFlow } from "@/components/onboarding/onboarding-flow";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.onboarding");

/** A council job's own address (T-R2-20 / R2-M-25): /onboarding/<id> opens that job, the same screen as
 * /onboarding?job=<id>; a bad id falls back to the files step. */
export default async function OnboardingJobPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const jobId = Number(id);
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <OnboardingFlow initialJobId={Number.isInteger(jobId) && jobId > 0 ? jobId : null} />
      </HydrationGate>
    </Suspense>
  );
}
