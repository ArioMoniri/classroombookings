import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { RecreatePreview } from "@/components/moderation/recreate-preview";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("moderation.preview.title");

export default async function RecreatePage({ params }: { params: Promise<{ runId: string }> }) {
  const { runId } = await params;
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <RecreatePreview runId={Number(runId)} />
      </HydrationGate>
    </Suspense>
  );
}
