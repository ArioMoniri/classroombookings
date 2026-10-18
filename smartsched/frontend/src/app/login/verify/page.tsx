import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { MfaStep } from "@/components/auth/mfa-step";
import { decodePending, MFA_COOKIE } from "@/components/auth/mfa-model";
import { SignInShell } from "@/components/auth/signin-shell";
import { safeNext } from "@/components/auth/signin-model";
import { localizedTitle } from "@/lib/i18n/server";
import { loadOrgPublic } from "@/lib/server/sign-in";

export const generateMetadata = localizedTitle("titles.login");
export const dynamic = "force-dynamic";

/**
 * /login/verify (docs/design/v3/auth.md §5; AUX-04): the second step in the sign-in sheet. The challenge lives in the
 * httpOnly `ss_mfa` cookie (route handler app/api/auth/mfa/[step]); without one the person goes back to /login.
 */
export default async function VerifyPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const pending = decodePending((await cookies()).get(MFA_COOKIE)?.value);
  if (!pending || pending.k !== "mfa") redirect("/login?method=local&mfa=expired");
  const org = await loadOrgPublic();
  const rememberDays = org?.passkeys ? org.passkeys.trusted_device_days : 30;
  return (
    <SignInShell logoUrl={org?.logo_url} kvkkUrl={org?.kvkk_notice_url ?? null} testId="verify-page">
      <MfaStep methods={pending.m} masked={pending.a} next={safeNext(sp.next) ?? pending.n ?? null} rememberDays={rememberDays} passkeySignIn={Boolean(org?.passkeys?.sign_in)} />
    </SignInShell>
  );
}
