import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { PersonProfile } from "@/components/moderation/person-profile";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("moderation.profile.title");

export default async function PersonPage({ params }: { params: Promise<{ personId: string }> }) {
  const { personId } = await params;
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <PersonProfile instructorId={Number(personId)} />
      </HydrationGate>
    </Suspense>
  );
}
