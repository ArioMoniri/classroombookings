import type { Metadata } from "next";
import { Suspense } from "react";
import { ClassesPage } from "@/components/classes/classes-page";

export const metadata: Metadata = { title: "Classes" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <ClassesPage />
    </Suspense>
  );
}
