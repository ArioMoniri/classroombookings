import type { Metadata } from "next";
import { Suspense } from "react";
import { AfterHydration } from "@/components/timetable/after-hydration";
import { TimetablePage } from "@/components/timetable/timetable-page";

export const metadata: Metadata = { title: "Timetable" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      {/* client-only after hydration: React #418 (see AfterHydration) */}
      <AfterHydration testId="timetable-loading">
        <TimetablePage />
      </AfterHydration>
    </Suspense>
  );
}
