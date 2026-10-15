import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { ProgramWizard } from "@/components/program-wizard/program-wizard";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("programWizard.title");

/** Yeni program (Phase 19 F4): /programs/new, /programs/new?draft=<key>&step=term|program|courses|… */
export default function NewProgramPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <ProgramWizard />
      </HydrationGate>
    </Suspense>
  );
}
