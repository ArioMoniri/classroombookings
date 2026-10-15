import { Suspense } from "react";
import { AccessChecker } from "@/components/admin/access-checker";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminAccess");

// the screen reads its query (deep links from other admin screens and ⌘K), so it renders under Suspense
export default function Page() {
  return (
    <Suspense fallback={null}>
      <AccessChecker />
    </Suspense>
  );
}
