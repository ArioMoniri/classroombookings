import type { Metadata } from "next";
import { Suspense } from "react";
import { ImportWizard } from "@/components/import/import-wizard";

export const metadata: Metadata = { title: "Import" };

export default function ImportPage() {
  return (
    <Suspense fallback={null}>
      <ImportWizard />
    </Suspense>
  );
}
