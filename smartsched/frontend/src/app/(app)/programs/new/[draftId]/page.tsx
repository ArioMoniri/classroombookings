import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { ProgramWizard } from "@/components/program-wizard/program-wizard";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("programWizard.title");

/** a server-side program draft (P19-W-01): /programs/new/<id>?step=program|courses|sections|instructors|cohorts|rooms|constraints|generate */
export default async function ProgramDraftPage({ params }: { params: Promise<{ draftId: string }> }) {
  const { draftId } = await params;
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <ProgramWizard draftId={Number(draftId)} />
      </HydrationGate>
    </Suspense>
  );
}
