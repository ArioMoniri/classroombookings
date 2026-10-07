import type { Metadata } from "next";
import { Suspense } from "react";
import { RequestsView } from "@/components/requests/requests-view";

export const metadata: Metadata = { title: "Requests" };

export default function RequestsPage() {
  return (
    <Suspense fallback={null}>
      <RequestsView />
    </Suspense>
  );
}
