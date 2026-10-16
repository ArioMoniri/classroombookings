import { localizedTitle } from "@/lib/i18n/server";
import { HydrationGate } from "@/components/common/hydration-gate";
import { Suspense } from "react";
import { RunView } from "@/components/runs/run-view";

export const generateMetadata = localizedTitle("titles.run");

export default async function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <RunView id={Number(id)} />
      </HydrationGate>
    </Suspense>
  );
}
