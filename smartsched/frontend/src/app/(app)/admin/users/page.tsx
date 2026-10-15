import { Suspense } from "react";
import { UsersAdmin } from "@/components/admin/users-admin";
import { localizedTitle } from "@/lib/i18n/server";

export const generateMetadata = localizedTitle("titles.adminUsers");

// the screen reads its query (deep links from other admin screens and ⌘K), so it renders under Suspense
export default function Page() {
  return (
    <Suspense fallback={null}>
      <UsersAdmin />
    </Suspense>
  );
}
