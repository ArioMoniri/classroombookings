import type { Metadata } from "next";
import { Suspense } from "react";
import { ApprovalsView } from "@/components/approvals/approvals-view";

export const metadata: Metadata = { title: "Approvals" };

// reads ?request= (the in-app notification), so it renders under Suspense
export default function ApprovalsPage() {
  return (
    <Suspense fallback={null}>
      <ApprovalsView />
    </Suspense>
  );
}
