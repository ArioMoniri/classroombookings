import { localizedTitle } from "@/lib/i18n/server";
import { Suspense } from "react";
import { ClassesPage } from "@/components/classes/classes-page";

export const generateMetadata = localizedTitle("titles.classes");

export default function Page() {
  return (
    <Suspense fallback={null}>
      <ClassesPage />
    </Suspense>
  );
}
