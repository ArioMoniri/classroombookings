import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { LearningMemoryPanel } from "@/components/learning/learning-memory-panel";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("learning.memory.title");

/** Öğrenme belleği (Phase 19 F3): the standalone settings panel; Settings › Öğrenme can mount the same component */
export default function LearningPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <LearningMemoryPanel heading="h1" />
      </HydrationGate>
    </Suspense>
  );
}
