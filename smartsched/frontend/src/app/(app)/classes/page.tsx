import type { Metadata } from "next";
import { Suspense } from "react";
import { AfterHydration } from "@/components/timetable/after-hydration";
import { ClassesPage } from "@/components/classes/classes-page";

export const metadata: Metadata = { title: "Classes" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      {/* client-only after hydration: React #418 (see AfterHydration) */}
      <AfterHydration testId="classes-loading">
        <ClassesPage />
      </AfterHydration>
    </Suspense>
  );
}
