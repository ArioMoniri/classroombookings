import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { EnrolNotice } from "@/components/auth/enrol-notice";
import { decodePending, MFA_COOKIE } from "@/components/auth/mfa-model";
import { SignInShell } from "@/components/auth/signin-shell";
import { safeNext } from "@/components/auth/signin-model";
import { localizedTitle } from "@/lib/i18n/server";
import { AUTH_COOKIE, backendBaseUrl } from "@/lib/server/config";
import { loadOrgPublic } from "@/lib/server/sign-in";

export const generateMetadata = localizedTitle("titles.login");
export const dynamic = "force-dynamic";

async function signedIn(path: string, token: string): Promise<Record<string, unknown> | null> {
  try {
    const r = await fetch(`${backendBaseUrl()}/api/v1${path}`, { headers: { authorization: `Bearer ${token}`, accept: "application/json" }, cache: "no-store", signal: AbortSignal.timeout(4000) });
    return r.ok ? ((await r.json()) as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/**
 * /login/setup-2fa (docs/design/v3/auth.md §5.6; AUX-04). Enforced (grace over): the setup token is in `ss_mfa`, no
 * session yet. Grace: signed in and `GET /auth/mfa` says required without a method; "Daha sonra" is offered.
 */
export default async function SetupTwoFactorPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const sp = await searchParams;
  const next = safeNext(sp.next);
  const jar = await cookies();
  const pending = decodePending(jar.get(MFA_COOKIE)?.value);
  const org = await loadOrgPublic();
  const orgName = org?.name?.trim() || null;
  const shell = (body: React.ReactNode) => (
    <SignInShell logoUrl={org?.logo_url} kvkkUrl={org?.kvkk_notice_url ?? null} testId="setup-2fa-page">
      {body}
    </SignInShell>
  );
  if (pending?.k === "setup") {
    return shell(<EnrolNotice mode="enforced" graceUntil={pending.g ?? null} methods={pending.m} org={orgName} next={next ?? pending.n ?? null} account={pending.a ?? ""} />);
  }
  const token = jar.get(AUTH_COOKIE)?.value;
  if (!token) redirect("/login");
  const [status, me] = await Promise.all([signedIn("/auth/mfa", token), signedIn("/auth/me", token)]);
  const totp = status?.totp as { enabled?: boolean } | undefined;
  const has = Boolean(totp?.enabled) || (Array.isArray(status?.passkeys) && status.passkeys.length > 0);
  if (!status || !status.required || has) redirect(next ?? "/");
  const methods = ["totp", ...(status.passkeys_available ? ["passkey"] : [])];
  const account = String(me?.username ?? me?.email ?? "");
  return shell(<EnrolNotice mode="grace" graceUntil={(status.grace_until as string | null) ?? null} methods={methods} org={orgName} next={next} account={account} permissions={(me?.permissions as string[] | undefined) ?? null} />);
}
