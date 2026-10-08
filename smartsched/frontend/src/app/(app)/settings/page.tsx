import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { HydrationGate } from "@/components/common/hydration-gate";
import { Suspense } from "react";
import { SettingsView } from "@/components/settings/settings-view";

export const metadata: Metadata = { title: "Settings" };

/**
 * The old "Users" tab (`?tab=users`: e-mail, name, role code and password only) is replaced by the full CRBS
 * user screen at /admin/users (username, role, department, limits, import; UI gap audit 2026-10-08 #8).
 * Old links, bookmarks and the tab itself land there.
 */
export default async function SettingsPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const tab = (await searchParams).tab;
  if ((Array.isArray(tab) ? tab[0] : tab) === "users") redirect("/admin/users");
  return (
    <Suspense fallback={null}>
      <HydrationGate>
        <SettingsView />
      </HydrationGate>
    </Suspense>
  );
}
