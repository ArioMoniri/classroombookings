import type { Metadata } from "next";
import { Suspense } from "react";
import { AccessChecker } from "@/components/admin/access-checker";

export const metadata: Metadata = { title: "Access" };

// the screen reads its query (deep links from other admin screens and ⌘K), so it renders under Suspense
export default function Page() {
  return (
    <Suspense fallback={null}>
      <AccessChecker />
    </Suspense>
  );
}
