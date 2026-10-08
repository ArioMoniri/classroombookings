import type { Metadata } from "next";
import { Suspense } from "react";
import { UsersAdmin } from "@/components/admin/users-admin";

export const metadata: Metadata = { title: "Users" };

// the screen reads its query (deep links from other admin screens and ⌘K), so it renders under Suspense
export default function Page() {
  return (
    <Suspense fallback={null}>
      <UsersAdmin />
    </Suspense>
  );
}
