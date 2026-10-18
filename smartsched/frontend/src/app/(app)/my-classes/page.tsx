import { Suspense } from "react";
import { HydrationGate } from "@/components/common/hydration-gate";
import { MyClassesView } from "@/components/my-classes/my-classes-view";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.myClasses");

/** PER-F09 (fix-h-2026-10-18): "Derslerim", the academician's own classes in one week (read-only) */
export default function MyClassesPage() {
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <MyClassesView />
      </HydrationGate>
    </Suspense>
  );
}
