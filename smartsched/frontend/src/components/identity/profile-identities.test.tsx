// Profil › Güvenlik: link / unlink a Google, OIDC or SAML identity (idp-2026-10-18; backend
// app/services/identity/links.py). One row per provider, one action per row, a confirmation before leaving for the
// provider, re-authentication (password dialog) only when the sign-in is older than 10 minutes, focus kept on the row.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { forgetReauth } from "@/components/profile/security/reauth-dialog";
import { I18nProvider } from "@/lib/i18n/provider";
import { IdentityLinkRows, readLinkNotice } from "./profile-identities";

const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast: toasts }));

beforeAll(() => {
  if (!document.elementFromPoint) Object.defineProperty(document, "elementFromPoint", { value: () => null, configurable: true });
});

const KC = { slug: "keycloak", kind: "oidc", badge: "OIDC", label: "Üniversite SSO (Keycloak)", label_en: "University SSO (Keycloak)", enabled: true, linked: false };
const YETKIM = {
  slug: "yetkim",
  kind: "saml",
  badge: "SAML",
  label: "YETKİM",
  label_en: "YETKİM",
  enabled: true,
  linked: true,
  email_at_login: "ayse.yilmaz@uni.edu.tr",
  linked_at: "2026-10-12T09:30:00",
  last_login_at: "2026-10-17T07:00:00",
};

type Route = (body: unknown) => Response | Promise<Response>;
const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const reauthFailed = () => res(403, { detail: { code: "reauth_failed", tr: "Parolanızla onaylayın (parola yanlış ya da girilmedi).", en: "confirm with your password" } });
let routes: Record<string, Route>;
let calls: { key: string; body: unknown }[];
let identities: { has_password: boolean; providers: unknown[] };

beforeEach(() => {
  forgetReauth();
  calls = [];
  Object.values(toasts).forEach((f) => f.mockReset());
  identities = { has_password: true, providers: [KC, YETKIM] };
  routes = { "GET /api/v1/auth/sso/me/identities": () => res(200, identities) };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${String(url).split("?")[0]}`;
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ key, body });
      const r = routes[key];
      return r ? r(body) : res(404, { detail: "not found" });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const wrap = (props: Partial<Parameters<typeof IdentityLinkRows>[0]> = {}) => {
  const navigate = vi.fn();
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">
        <ul>
          <IdentityLinkRows navigate={navigate} {...props} />
        </ul>
      </I18nProvider>
    </QueryClientProvider>,
  );
  return navigate;
};

describe("IdentityLinkRows", () => {
  it("one row per provider in Turkish: linked shows the address and the date, one action each", async () => {
    wrap();
    const kc = await screen.findByTestId("security-idp-keycloak");
    expect(within(kc).getByText("Üniversite SSO (Keycloak)")).toBeTruthy();
    expect(within(kc).getByText(/Bağlı değil/)).toBeTruthy();
    expect(within(kc).getAllByRole("button").map((b) => b.textContent)).toEqual(["Bağla"]);
    const y = screen.getByTestId("security-idp-yetkim");
    expect(within(y).getByText(/ayse\.yilmaz@uni\.edu\.tr · 12 Ekim 2026 tarihinde bağlandı/)).toBeTruthy();
    expect(within(y).getAllByRole("button").map((b) => b.textContent)).toEqual(["Bağlantıyı kaldır"]);
  });

  it("shows nothing for an account without a SmartSched password or without providers", async () => {
    identities = { has_password: false, providers: [KC] };
    wrap();
    await waitFor(() => expect(calls.some((c) => c.key === "GET /api/v1/auth/sso/me/identities")).toBe(true));
    expect(screen.queryByTestId("security-idp-keycloak")).toBeNull();
  });

  it("link: confirm first, then the provider; a fresh session needs no password", async () => {
    routes["POST /api/v1/auth/sso/keycloak/link"] = () => res(200, { authorize_url: "https://sso.uni.edu.tr/realms/uni/auth?state=x" });
    const navigate = wrap();
    fireEvent.click(await screen.findByTestId("idp-link-keycloak"));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("Üniversite SSO (Keycloak) hesabınızı bağlayın")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Üniversite SSO (Keycloak) sayfasına devam et" }));
    expect(await within(dialog).findByText("Önce onayı işaretleyin.")).toBeTruthy();
    expect(calls.some((c) => c.key.startsWith("POST"))).toBe(false);
    fireEvent.click(within(dialog).getByRole("checkbox"));
    fireEvent.click(within(dialog).getByRole("button", { name: "Üniversite SSO (Keycloak) sayfasına devam et" }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("https://sso.uni.edu.tr/realms/uni/auth?state=x"));
    expect(calls.find((c) => c.key === "POST /api/v1/auth/sso/keycloak/link")?.body).toEqual({ confirm: true });
  });

  it("link after 10 minutes: the password dialog, then the provider", async () => {
    routes["POST /api/v1/auth/sso/keycloak/link"] = (body) =>
      (body as { password?: string }).password === "doğru-parola" ? res(200, { authorize_url: "https://sso.uni.edu.tr/x" }) : reauthFailed();
    const navigate = wrap();
    fireEvent.click(await screen.findByTestId("idp-link-keycloak"));
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("checkbox"));
    fireEvent.click(within(dialog).getByRole("button", { name: /sayfasına devam et/ }));
    const pw = await screen.findByTestId("reauth-password");
    fireEvent.change(pw, { target: { value: "doğru-parola" } });
    fireEvent.click(screen.getByTestId("reauth-submit"));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith("https://sso.uni.edu.tr/x"));
  });

  it("unlink: a destructive confirmation, re-authentication, a toast and focus on the row's new action", async () => {
    routes["POST /api/v1/auth/sso/yetkim/unlink"] = (body) => {
      if ((body as { password?: string }).password !== "doğru-parola") return reauthFailed();
      identities = { has_password: true, providers: [KC, { ...YETKIM, linked: false, email_at_login: null, linked_at: null }] };
      return res(204);
    };
    wrap();
    fireEvent.click(await screen.findByTestId("idp-unlink-yetkim"));
    const dialog = await screen.findByRole("alertdialog");
    expect(within(dialog).getByText("YETKİM bağlantısı kaldırılsın mı?")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Bağlantıyı kaldır" }));
    fireEvent.change(await screen.findByTestId("reauth-password"), { target: { value: "doğru-parola" } });
    fireEvent.click(screen.getByTestId("reauth-submit"));
    await waitFor(() => expect(toasts.success).toHaveBeenCalledWith("YETKİM bağlantısı kaldırıldı"));
    const link = await screen.findByTestId("idp-link-yetkim");
    await waitFor(() => expect(document.activeElement).toBe(link));
  });

  it("the return from the provider is shown on its row (linked or the reason)", async () => {
    expect(readLinkNotice("?sso=linked&provider=keycloak")).toEqual({ provider: "keycloak", kind: "linked" });
    expect(readLinkNotice("?error=already_linked&provider=yetkim")).toEqual({ provider: "yetkim", kind: "already_linked" });
    expect(readLinkNotice("?error=weird_code&provider=yetkim")).toEqual({ provider: "yetkim", kind: "failed" });
    expect(readLinkNotice("?sso=linked")).toBeNull(); // Microsoft's own notice
    expect(readLinkNotice("?sso=linked&provider=entra")).toBeNull();
    wrap({ notice: { provider: "keycloak", kind: "linked" } });
    const kc = await screen.findByTestId("security-idp-keycloak");
    expect(within(kc).getByText("Üniversite SSO (Keycloak) hesabınız bağlandı. Artık onunla da giriş yapabilirsiniz.")).toBeTruthy();
  });
});
