import type { Viewport } from "next";
import { Suspense } from "react";
import { WelcomeView } from "@/components/auth/welcome-view";
import { localizedTitle } from "@/lib/i18n/server";
import { loadOrgPublic } from "@/lib/server/sign-in";

export const generateMetadata = localizedTitle("signin.welcome.title");
export const dynamic = "force-dynamic";
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", interactiveWidget: "resizes-content" };

/** /welcome: once per account, after the Microsoft sign-in that created or bound it (sign-in.md §6.4). */
export default async function WelcomePage() {
  const org = await loadOrgPublic();
  return (
    <Suspense fallback={null}>
      <WelcomeView logoUrl={org?.logo_url ?? null} kvkkUrl={org?.kvkk_notice_url ?? null} />
    </Suspense>
  );
}
