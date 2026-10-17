import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { InvigilationView } from "@/components/invigilation/invigilation-view";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("invigilation.title");

/** Gözetmen ataması: /exams/invigilation?run=<exam run>&plan=<plan>&tab=plans|pool&view=posts|people */
export default function InvigilationPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <InvigilationView />
      </HydrationGate>
    </Suspense>
  );
}
