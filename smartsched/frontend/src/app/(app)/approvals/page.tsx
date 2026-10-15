import { Suspense } from "react";
import { ApprovalsView } from "@/components/approvals/approvals-view";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.approvals");

// reads ?request= (the in-app notification), so it renders under Suspense
export default function ApprovalsPage() {
  return (
    <Suspense fallback={null}>
      <ApprovalsView />
    </Suspense>
  );
}
