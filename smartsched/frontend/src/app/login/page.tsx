import type { Viewport } from "next";
import { SignInPage } from "@/components/auth/sign-in-page";
import { readSignInParams } from "@/components/auth/signin-model";
import { localizedTitle } from "@/lib/i18n/server";
import { lastMethodLocal, loadInvite, loadOrgPublic } from "@/lib/server/sign-in";

export const generateMetadata = localizedTitle("titles.login");
export const dynamic = "force-dynamic";

/* sign-in.md §5.4: Chromium Android resizes the layout viewport with the keyboard, so 100dvh shrinks with it */
export const viewport: Viewport = { width: "device-width", initialScale: 1, viewportFit: "cover", interactiveWidget: "resizes-content" };

/**
 * /login (docs/design/v2/sign-in.md): `GET /org/public` and the invite banner are read here, on the server, so the
 * doors (Microsoft button, password disclosure, open form) are final on the first paint (§4.3).
 */
export default async function LoginPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = readSignInParams(await searchParams);
  const [org, invite, lastLocal] = await Promise.all([loadOrgPublic(), loadInvite(params.invite), lastMethodLocal()]);
  return <SignInPage org={org} params={params} invite={invite} lastMethodLocal={lastLocal} />;
}
