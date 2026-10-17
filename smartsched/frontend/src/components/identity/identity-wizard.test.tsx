import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { IdentityProvidersPanel } from "./identity-providers-panel";
import { ProviderButtons } from "./provider-buttons";
import { ProviderWizard } from "./provider-wizard";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/permissions", async (orig) => ({ ...(await orig<typeof import("@/lib/permissions")>()), usePermissions: () => ({ perms: [], can: () => true, canAll: () => true, userId: 1, loading: false, departmentId: null }) }));
vi.mock("@/lib/api/crbs", () => ({
  useRoles: () => ({
    data: [
      { id: 2, code: "TEACHER", name: "Teacher", permissions: ["bookings.create"] },
      { id: 3, code: "PLANNER", name: "Planner", permissions: ["planning.edit"] },
    ],
  }),
  useDepartments: () => ({ data: [] }),
  crbs: { org: { i18n: () => Promise.reject(new Error("x")) } },
}));

type Route = (url: string, init?: RequestInit) => { status: number; body?: unknown } | undefined;
function mockFetch(route: Route) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const r = route(url, init) ?? { status: 404, body: { detail: "not found" } };
    return new Response(r.body === undefined ? null : JSON.stringify(r.body), { status: r.status, headers: { "content-type": "application/json" } });
  });
}

function wrap(node: ReactNode, locale: "tr" | "en" = "tr") {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale={locale}>{node}</I18nProvider>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

const PANEL = "https://rezervasyon.uni.edu.tr";

function provider(over: Record<string, unknown> = {}) {
  return {
    id: 4,
    name: "keycloak",
    kind: "oidc",
    badge: "OIDC",
    label: "Keycloak",
    label_en: "Keycloak",
    display_name: null,
    preset: "keycloak",
    enabled: false,
    configured: true,
    status: "disabled",
    sort_order: 10,
    allowed_domains: [],
    invite_only: true,
    self_signup: true,
    default_role: { id: 2, code: "TEACHER", name: "Teacher" },
    role_mapping_enabled: false,
    allow_admin_mapping: false,
    oidc_only_non_admins: false,
    invite_days: 30,
    domain_hint: null,
    client_id: "smartsched-panel",
    client_secret_set: true,
    from_environment: [],
    secret_expires: null,
    tenant_id: null,
    issuer: "https://sso.uni.edu.tr/realms/uni",
    hosted_domains: [],
    groups_claim: "groups",
    roles_claim: "roles",
    trust_email: false,
    scopes: [],
    discovery: { ok: true, checks: [{ key: "issuer", ok: true, tr: "Yayıncı eşleşiyor.", en: "The issuer matches." }], fetched_at: null },
    saml: null,
    library_required: false,
    redirect_uri: `${PANEL}/api/v1/auth/sso/keycloak/callback`,
    start_url: "/api/v1/auth/sso/keycloak/start",
    identities: 0,
    test_ok: null,
    test_at: null,
    last_check_at: "2026-10-17T19:40:00Z",
    last_check_ok: true,
    last_check_detail: "discovery ok",
    changed_by: "Mehmet Kaya",
    changed_at: "2026-10-17T19:40:00Z",
    version: "2026-10-17T19:40:00.000001",
    ...over,
  };
}

function setup(p = provider(), over: Record<string, unknown> = {}) {
  return {
    provider: p,
    public_url: PANEL,
    public_url_source: "settings",
    public_url_secure: true,
    console: [
      { key: "redirect_uri", label_tr: "Yönlendirme adresi", label_en: "Sign-in redirect URI", value: `${PANEL}/api/v1/auth/sso/keycloak/callback` },
      { key: "scopes", label_tr: "Kapsamlar", label_en: "Scopes", value: "openid profile email" },
    ],
    steps: { tr: ["Keycloak › Clients › Create client."], en: ["Keycloak › Clients › Create client."] },
    fields: [],
    issuer_hint: "https://sso.uni.edu.tr/realms/uni",
    groups_claim_hint: "groups",
    ...over,
  };
}

describe("IdentityProvidersPanel", () => {
  it("lists providers with the status word, the last change and LDAP, in the shared order", async () => {
    mockFetch((url) => {
      if (url.includes("/auth/sso/admin/providers") && !url.includes("/providers/")) {
        return {
          status: 200,
          body: {
            providers: [provider(), provider({ id: 5, name: "google", kind: "google_workspace", badge: "G", label: "Google Workspace", label_en: "Google Workspace", status: "not_configured", configured: false, changed_by: null })],
            ldap: { kind: "ldap", badge: "LDAP", label: "LDAP / Active Directory", label_en: "LDAP / Active Directory", enabled: false, configured: false, settings_href: "/settings?tab=ldap" },
            break_glass_admins: 1,
            saml_available: true,
          },
        };
      }
      if (url.includes("/auth/sso/admin/invites")) return { status: 200, body: [] };
      return undefined;
    });
    wrap(<IdentityProvidersPanel />);
    const row = await screen.findByTestId("idp-row-keycloak");
    expect(row).toHaveTextContent("Keycloak");
    expect(row).toHaveTextContent("Kapalı");
    expect(row).toHaveTextContent("Son değişiklik: Mehmet Kaya");
    expect(screen.getByTestId("idp-row-google")).toHaveTextContent("Yapılandırılmadı");
    expect(screen.getByTestId("idp-setup-google")).toHaveTextContent("Kur");
    expect(screen.getByTestId("idp-ldap")).toHaveTextContent("LDAP / Active Directory");
    expect(screen.getByTestId("idp-invites")).toBeInTheDocument();
  });
});

describe("ProviderWizard (guided setup)", () => {
  it("shows the console values to copy, built from the public URL", async () => {
    mockFetch((url) => (url.includes("/providers/4/setup") ? { status: 200, body: setup() } : undefined));
    wrap(<ProviderWizard providerId={4} onBack={() => undefined} />);
    await screen.findByTestId("idp-wizard");
    fireEvent.click(screen.getByTestId("idp-step-console"));
    expect(screen.getByTestId("idp-copy-redirect_uri")).toHaveTextContent("Yönlendirme adresi");
    expect(screen.getByDisplayValue(`${PANEL}/api/v1/auth/sso/keycloak/callback`)).toBeInTheDocument();
    expect(screen.getByTestId("idp-changed")).toHaveTextContent("Son değişiklik: Mehmet Kaya");
  });

  it("blocks the console step without a public URL", async () => {
    mockFetch((url) => (url.includes("/providers/4/setup") ? { status: 200, body: setup(provider({ configured: false }), { public_url: null }) } : undefined));
    wrap(<ProviderWizard providerId={4} onBack={() => undefined} />);
    await screen.findByTestId("idp-wizard");
    expect(screen.getByTestId("idp-step-console")).toBeDisabled();
    expect(screen.getByTestId("idp-step-test")).toBeDisabled();
  });

  it("keeps the secret write-only, warns on a pasted GUID and sends the version it started from", async () => {
    const f = mockFetch((url, init) => {
      if (url.includes("/providers/4/setup")) return { status: 200, body: setup() };
      if (url.endsWith("/auth/sso/admin/providers/4") && init?.method === "PUT") return { status: 200, body: provider() };
      return undefined;
    });
    wrap(<ProviderWizard providerId={4} onBack={() => undefined} />);
    await screen.findByTestId("idp-wizard");
    fireEvent.click(screen.getByTestId("idp-step-values"));
    expect(screen.getByTestId("idp-secret-set")).toHaveTextContent("kayıtlı");
    expect(screen.queryByDisplayValue("kc-fake-secret")).toBeNull();
    fireEvent.click(screen.getByTestId("idp-secret-replace"));
    fireEvent.change(screen.getByTestId("idp-secret"), { target: { value: "3f2a8c1e-5b7d-4e9a-a6c4-2d8e1f0b9c7a" } });
    expect(screen.getByText(/kimliğe benziyor/)).toBeInTheDocument();
    fireEvent.change(screen.getByTestId("idp-secret"), { target: { value: " kc-yeni-gizli​ " } });
    fireEvent.click(screen.getByTestId("idp-values-save"));
    await waitFor(() => expect(f.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(true));
    const put = f.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(JSON.parse(String(put?.[1]?.body))).toEqual({ version: "2026-10-17T19:40:00.000001", client_secret: "kc-yeni-gizli" });
  });

  it("runs the test login in a popup, polls the result and shows the claims; Etkinleştir unlocks", async () => {
    const popup = { location: { href: "" }, close: vi.fn() };
    vi.spyOn(window, "open").mockReturnValue(popup as unknown as Window);
    let polls = 0;
    mockFetch((url, init) => {
      if (url.includes("/providers/4/setup")) return { status: 200, body: setup() };
      if (url.endsWith("/providers/4/test") && init?.method === "POST") return { status: 200, body: { authorize_url: "https://sso.uni.edu.tr/realms/uni/auth?state=x", test_id: "t1" } };
      if (url.includes("/providers/4/test/t1")) {
        polls += 1;
        return polls < 2
          ? { status: 200, body: { status: "pending" } }
          : { status: 200, body: { status: "done", ok: true, verified_email: "ayse.yilmaz@uni.edu.tr", groups: ["/personel/planlama"], roles: [], claims: { email: "ayse.yilmaz@uni.edu.tr", name: "Ayşe Yılmaz" }, domain_ok: true } };
      }
      return undefined;
    });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    wrap(<ProviderWizard providerId={4} onBack={() => undefined} />);
    await screen.findByTestId("idp-wizard");
    fireEvent.click(screen.getByTestId("idp-step-test"));
    expect(screen.getByTestId("idp-step-enable")).toBeDisabled();
    fireEvent.click(screen.getByTestId("idp-test-login"));
    await waitFor(() => expect(popup.location.href).toBe("https://sso.uni.edu.tr/realms/uni/auth?state=x"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3500);
    });
    const res = await screen.findByTestId("idp-test-result");
    expect(res).toHaveAttribute("data-ok", "true");
    expect(res).toHaveTextContent("Giriş başarılı: ayse.yilmaz@uni.edu.tr");
    expect(res).toHaveTextContent("Gruplar: 1");
    expect(screen.getByTestId("idp-step-enable")).not.toBeDisabled();
  });

  it("translates a failed test into cause + fix and the step to go back to", async () => {
    vi.spyOn(window, "open").mockReturnValue({ location: { href: "" }, close: vi.fn() } as unknown as Window);
    mockFetch((url, init) => {
      if (url.includes("/providers/4/setup")) return { status: 200, body: setup() };
      if (url.endsWith("/providers/4/test") && init?.method === "POST") return { status: 200, body: { authorize_url: "https://x/auth", test_id: "t2" } };
      if (url.includes("/providers/4/test/t2"))
        return { status: 200, body: { status: "done", ok: false, code: "failed", reason: "exchange", detail: "token: invalid_client", hint: { tr: "İstemci kimliği ya da gizli anahtar yanlış.", en: "The client id or secret is wrong.", step: 3, raw: "token: invalid_client" } } };
      return undefined;
    });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    wrap(<ProviderWizard providerId={4} onBack={() => undefined} />);
    await screen.findByTestId("idp-wizard");
    fireEvent.click(screen.getByTestId("idp-step-test"));
    fireEvent.click(screen.getByTestId("idp-test-login"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });
    const res = await screen.findByTestId("idp-test-result");
    expect(res).toHaveAttribute("data-ok", "false");
    expect(res).toHaveTextContent("gizli anahtar yanlış");
    fireEvent.click(screen.getByText("3. adıma dön"));
    expect(screen.getByTestId("idp-step-values")).toHaveAttribute("aria-current", "step");
  });
});

describe("ProviderButtons (/login, design v3 §6)", () => {
  const b = (name: string, kind = "oidc", label = name) => ({ name, kind, label, start_url: `/api/v1/auth/sso/${name}/start`, badge: "OIDC" });

  it("shows three equal buttons and the rest behind 'Diğer giriş yolları'", () => {
    wrap(<ProviderButtons providers={[b("google", "google_workspace", "Google Workspace"), b("okta", "oidc", "Okta"), b("yetkim", "saml", "YETKİM"), b("keycloak", "oidc", "Keycloak")]} next="/bookings" />);
    expect(screen.getByTestId("login-sso-google")).toHaveTextContent("Google ile oturum açın");
    expect(screen.getByTestId("login-sso-okta")).toHaveTextContent("Okta ile giriş yap");
    expect(screen.getByTestId("login-sso-okta")).toHaveAttribute("href", "/api/v1/auth/sso/okta/start?next=%2Fbookings");
    expect(screen.queryByTestId("login-sso-keycloak")).toBeNull();
    fireEvent.click(screen.getByTestId("signin-more-providers"));
    expect(screen.getByTestId("signin-more-providers")).toHaveTextContent("Diğer giriş yolları (1)");
    expect(screen.getByTestId("login-sso-keycloak")).toBeInTheDocument();
  });

  it("an invite shows only the invited method with the invite token", () => {
    wrap(<ProviderButtons providers={[b("google", "google_workspace"), b("okta")]} invited="okta" inviteToken="tok" loginHint="ayse@uni.edu.tr" />);
    expect(screen.queryByTestId("login-sso-google")).toBeNull();
    expect(screen.getByTestId("login-sso-okta")).toHaveAttribute("href", "/api/v1/auth/sso/okta/start?invite=tok&login_hint=ayse%40uni.edu.tr");
  });
});
