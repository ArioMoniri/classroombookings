import { SignInPage } from "@/components/auth/sign-in-page";
import { readSignInParams } from "@/components/auth/signin-model";
import { localizedTitle } from "@/lib/i18n/server";
import { lastMethodLocal, loadInvite, loadOrgPublic } from "@/lib/server/sign-in";

export const generateMetadata = localizedTitle("titles.login");
export const dynamic = "force-dynamic";

/* sign-in.md §5.4 (the keyboard resizes the layout viewport): the root layout's viewport carries
   interactive-widget=resizes-content for every route since T-R1-02, so this page no longer overrides it */

/**
 * /login (docs/design/v2/sign-in.md): `GET /org/public` and the invite banner are read here, on the server, so the
 * doors (Microsoft button, password disclosure, open form) are final on the first paint (§4.3).
 */
export default async function LoginPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const params = readSignInParams(await searchParams);
  const [org, invite, lastLocal] = await Promise.all([loadOrgPublic(), loadInvite(params.invite), lastMethodLocal()]);
  return <SignInPage org={org} params={params} invite={invite} lastMethodLocal={lastLocal} />;
}
