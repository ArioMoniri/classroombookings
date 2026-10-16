import type { Viewport } from "next";
import { Suspense } from "react";
import { SsoExchange } from "@/components/auth/sso-exchange";
import { localizedTitle } from "@/lib/i18n/server";
import { loadOrgPublic } from "@/lib/server/sign-in";

export const generateMetadata = localizedTitle("titles.login");
export const dynamic = "force-dynamic";
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", interactiveWidget: "resizes-content" };

/** /login/sso?ticket=…[&next=…][&welcome=…]: the callback's landing page; posts the one-time ticket (§14). */
export default async function SsoLandingPage() {
  const org = await loadOrgPublic();
  return (
    <Suspense fallback={null}>
      <SsoExchange logoUrl={org?.logo_url ?? null} kvkkUrl={org?.kvkk_notice_url ?? null} />
    </Suspense>
  );
}
