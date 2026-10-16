import { localizedTitle } from "@/lib/i18n/server";
import { Suspense } from "react";
import { TimetablePage } from "@/components/timetable/timetable-page";

export const generateMetadata = localizedTitle("titles.timetable");

export default function Page() {
  return (
    <Suspense fallback={null}>
      <TimetablePage />
    </Suspense>
  );
}
