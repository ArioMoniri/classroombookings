// AUX-03 (docs/design/v3/auth.md §4.1–§4.3, §4.6): passkeys in door 2, only with passwordless sign-in allowed.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { OrgPublicAuth } from "@/lib/api/identity";
import { I18nProvider } from "@/lib/i18n/provider";
import { SignInPage } from "./sign-in-page";
import { doorsFor, readSignInParams } from "./signin-model";

const nav = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav, useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api/crbs", () => ({ useAppVersion: () => ({ data: "1.4.0" }), crbs: { org: { i18n: () => Promise.reject(new Error("x")) } } }));
vi.mock("@/components/bookings/use-booking-format", () => ({ applySessionLanguage: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }));

function org(signIn: boolean): OrgPublicAuth {
  return {
    name: "Örnek Üniversitesi",
    maintenance_mode: false,
    ldap_enabled: false,
    setup_required: false,
    auth: { microsoft: { enabled: false, label: "Microsoft", start_url: "/x", self_signup: false }, local_enabled: true, ldap_enabled: false },
    passkeys: { enabled: true, sign_in: signIn, trusted_device_days: 30 },
  };
}

function view(o: OrgPublicAuth, lastMethodPasskey = false) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="tr">
        <SignInPage org={o} params={readSignInParams(new URLSearchParams(""))} invite={null} lastMethodLocal={false} lastMethodPasskey={lastMethodPasskey} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

const OPTIONS = { options: { publicKey: { challenge: "AAEC", rpId: "localhost", allowCredentials: [], userVerification: "required" } } };
const resp = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

let get: ReturnType<typeof vi.fn>;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  nav.replace.mockReset();
  nav.push.mockReset();
  get = vi.fn(() => new Promise(() => undefined));
  Object.defineProperty(navigator, "credentials", { value: { get, create: vi.fn() }, configurable: true });
  const PKC = function PublicKeyCredential() {} as unknown as Record<string, unknown>;
  PKC.isConditionalMediationAvailable = vi.fn(async () => true);
  vi.stubGlobal("PublicKeyCredential", PKC);
  fetchMock = vi.fn(async (url: string) => (String(url).endsWith("signin-passkey-options") ? resp(200, OPTIONS) : resp(404, {})));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function assertion(id = "AQIDBA") {
  return { id, rawId: new Uint8Array([1, 2, 3, 4]).buffer, type: "public-key", response: { clientDataJSON: new Uint8Array([1]).buffer, authenticatorData: new Uint8Array([2]).buffer, signature: new Uint8Array([3]).buffer, userHandle: null }, getClientExtensionResults: () => ({}) };
}

describe("passkeys in door 2", () => {
  it("passwordless off: no button, no webauthn token, no conditional get", async () => {
    view(org(false));
    expect(screen.queryByTestId("passkey-signin")).toBeNull();
    expect(screen.getByTestId("login-identifier")).toHaveAttribute("autocomplete", "username");
    await new Promise((r) => setTimeout(r, 20));
    expect(get).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("passwordless on: 'veya' + the button, the webauthn token, a conditional get with empty allowCredentials", async () => {
    view(org(true));
    expect(screen.getByTestId("passkey-signin")).toHaveTextContent("Geçiş anahtarıyla giriş yap");
    expect(screen.getByTestId("login-identifier")).toHaveAttribute("autocomplete", "username webauthn");
    await waitFor(() => expect(get).toHaveBeenCalled());
    const arg = get.mock.calls[0][0] as CredentialRequestOptions;
    expect(arg.mediation).toBe("conditional");
    expect(arg.publicKey?.allowCredentials).toEqual([]);
  });

  it("autofill pick signs in with no second step", async () => {
    get.mockResolvedValueOnce(assertion());
    fetchMock.mockImplementation(async (url: string) => (String(url).endsWith("signin-passkey-options") ? resp(200, OPTIONS) : String(url).endsWith("signin-passkey-verify") ? resp(200, { status: "signed_in", user: { id: 1, full_name: "Ayşe Yılmaz", permissions: ["planning.view"] } }) : resp(404, {})));
    view(org(true));
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/dashboard"));
    expect(nav.push).not.toHaveBeenCalledWith(expect.stringContaining("/login/verify"));
    expect(document.cookie).toContain("smartsched_last_signin=passkey");
  });

  it("NotAllowedError from the button: a neutral notice, no focus move", async () => {
    view(org(true));
    await waitFor(() => expect(get).toHaveBeenCalled());
    get.mockRejectedValueOnce(new DOMException("no", "NotAllowedError"));
    const button = screen.getByTestId("passkey-signin");
    button.focus();
    await act(async () => {
      fireEvent.click(button);
    });
    const notice = await screen.findByTestId("passkey-notice-cancelled");
    expect(notice).toHaveTextContent("Geçiş anahtarı kullanılmadı");
    expect(notice.contains(document.activeElement)).toBe(false);
  });

  it("an unknown credential: the error takes focus and the Signal API is told", async () => {
    const signalUnknownCredential = vi.fn(async () => undefined);
    Object.assign(globalThis.PublicKeyCredential as object, { signalUnknownCredential });
    view(org(true));
    await waitFor(() => expect(get).toHaveBeenCalled());
    get.mockResolvedValueOnce(assertion("AQIDBA"));
    fetchMock.mockImplementation(async (url: string) => (String(url).endsWith("signin-passkey-options") ? resp(200, OPTIONS) : String(url).endsWith("signin-passkey-verify") ? resp(401, { detail: { code: "passkey_invalid" } }) : resp(404, {})));
    await act(async () => {
      fireEvent.click(screen.getByTestId("passkey-signin"));
    });
    const notice = await screen.findByTestId("passkey-notice-unknown");
    await waitFor(() => expect(notice).toHaveFocus());
    expect(signalUnknownCredential).toHaveBeenCalledWith({ rpId: "localhost", credentialId: "AQIDBA" });
  });

  it("a passkey last time opens door 2 and says so", () => {
    const o = { ...org(true), auth: { ...org(true).auth!, microsoft: { enabled: true, label: "Microsoft", start_url: "/x", self_signup: false } } };
    view(o, true);
    expect(screen.getByTestId("login-form")).toBeInTheDocument();
    expect(screen.getByTestId("login-last-method")).toHaveTextContent("Son girişinizi geçiş anahtarıyla yaptınız.");
    // doorsFor: a passkey last time counts like the password form (the page passes local || passkey)
    expect(doorsFor({ auth: o.auth, reachable: true, params: { methodLocal: false }, invite: null, lastMethodLocal: true }).formOpenInitially).toBe(true);
  });

  it("the second step: the password answer 'mfa' goes to /login/verify with next only", async () => {
    fetchMock.mockImplementation(async (url: string) => (String(url).endsWith("/login") ? resp(200, { status: "mfa", methods: ["totp"], masked: "ay•••" }) : resp(200, OPTIONS)));
    view(org(false));
    fireEvent.change(screen.getByTestId("login-identifier"), { target: { value: "ayse" } });
    fireEvent.change(screen.getByTestId("login-password"), { target: { value: "pw" } });
    await act(async () => {
      fireEvent.submit(screen.getByTestId("login-form"));
    });
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/login/verify"));
  });
});
