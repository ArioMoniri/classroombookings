import type { Metadata } from "next";
import { Suspense } from "react";
import { TimetablePage } from "@/components/timetable/timetable-page";

export const metadata: Metadata = { title: "Timetable" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <TimetablePage />
    </Suspense>
  );
}
