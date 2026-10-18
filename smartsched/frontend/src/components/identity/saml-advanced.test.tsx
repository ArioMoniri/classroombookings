/**
 * The SAML step's "Gelişmiş" section of the provider wizard (idp2-2026-10-18): the federation metadata signing
 * certificate, the SP key (Oluştur / yapıştır / kaldır, write-only), "İstekleri imzala", read-only certificate details
 * and the metadata_signature check row. Backend contract: PUT /auth/sso/admin/providers/{id} (RF-12, idp-2026-10-18).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { ProviderWizard } from "./provider-wizard";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/permissions", async (orig) => ({
  ...(await orig<typeof import("@/lib/permissions")>()),
  usePermissions: () => ({ perms: [], can: () => true, canAll: () => true, userId: 1, loading: false, departmentId: null }),
}));
vi.mock("@/lib/api/crbs", () => ({
  useRoles: () => ({ data: [{ id: 2, code: "TEACHER", name: "Teacher", permissions: ["bookings.create"] }] }),
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
});

const PANEL = "https://rezervasyon.uni.edu.tr";
const VERSION = "2026-10-18T09:00:00.000001";
const FED = { subject: "CN=YETKİM Metadata İmzalama", not_after: "2027-10-18T09:00:00", sha256: "AB:CD:EF:01" };
const SPC = { subject: "CN=rezervasyon.uni.edu.tr", not_after: "2036-10-18T09:00:00", sha256: "12:34:56:78" };

function saml(over: Record<string, unknown> = {}) {
  return {
    metadata_url: "https://yetkim.org.tr/metadata.xml",
    idp_entity_id: "https://idp.uni.edu.tr/idp/shibboleth",
    sso_url: "https://idp.uni.edu.tr/idp/profile/SAML2/Redirect/SSO",
    certificates: 1,
    cert_not_after: "2027-10-18T00:00:00",
    email_attribute: "urn:oid:0.9.2342.19200300.100.1.3",
    name_attribute: "urn:oid:2.16.840.1.113730.3.1.241",
    groups_attribute: "urn:oid:1.3.6.1.4.1.5923.1.1.1.7",
    subject_attribute: null,
    metadata_signing_cert: null,
    metadata_signed: false,
    sp_certificate: null,
    sp_private_key_set: false,
    sign_requests: false,
    ...over,
  };
}

function provider(samlOver: Record<string, unknown> = {}, over: Record<string, unknown> = {}) {
  return {
    id: 7,
    name: "yetkim",
    kind: "saml",
    badge: "SAML",
    label: "YETKİM",
    label_en: "YETKİM",
    display_name: null,
    preset: "yetkim",
    enabled: false,
    configured: true,
    status: "disabled",
    sort_order: 10,
    allowed_domains: [],
    invite_only: true,
    self_signup: false,
    default_role: { id: 2, code: "TEACHER", name: "Teacher" },
    role_mapping_enabled: false,
    allow_admin_mapping: false,
    oidc_only_non_admins: false,
    invite_days: 30,
    domain_hint: null,
    client_id: null,
    client_secret_set: false,
    from_environment: [],
    secret_expires: null,
    tenant_id: null,
    issuer: null,
    hosted_domains: [],
    groups_claim: "groups",
    roles_claim: "roles",
    trust_email: false,
    scopes: [],
    discovery: {
      ok: true,
      checks: [{ key: "metadata", ok: true, tr: "Meta veri okundu: https://idp.uni.edu.tr/idp/shibboleth.", en: "Metadata read." }],
      fetched_at: null,
    },
    saml: saml(samlOver),
    library_required: false,
    redirect_uri: null,
    start_url: "/api/v1/auth/sso/yetkim/start",
    identities: 0,
    test_ok: null,
    test_at: null,
    last_check_at: null,
    last_check_ok: null,
    last_check_detail: null,
    changed_by: "Mehmet Kaya",
    changed_at: "2026-10-18T09:00:00Z",
    version: VERSION,
    ...over,
  };
}

function setup(p: ReturnType<typeof provider>) {
  return {
    provider: p,
    public_url: PANEL,
    public_url_source: "settings",
    public_url_secure: true,
    console: [],
    steps: { tr: [], en: [] },
    fields: [],
    issuer_hint: null,
    groups_claim_hint: null,
  };
}

/** The wizard on step 3 with "Gelişmiş" opened; ``put`` answers each PUT. */
async function openAdvanced(p: ReturnType<typeof provider>, put?: (body: Record<string, unknown>) => { status: number; body?: unknown }, locale: "tr" | "en" = "tr") {
  const f = mockFetch((url, init) => {
    if (url.includes("/providers/7/setup")) return { status: 200, body: setup(p) };
    if (url.endsWith("/auth/sso/admin/providers/7") && init?.method === "PUT") return put ? put(JSON.parse(String(init.body))) : { status: 200, body: p };
    return undefined;
  });
  wrap(<ProviderWizard providerId={7} onBack={() => undefined} />, locale);
  await screen.findByTestId("idp-wizard");
  fireEvent.click(screen.getByTestId("idp-step-values"));
  return f;
}

function puts(f: ReturnType<typeof mockFetch>) {
  return f.mock.calls.filter(([, init]) => init?.method === "PUT").map(([, init]) => JSON.parse(String(init?.body)) as Record<string, unknown>);
}

describe("SAML step › Gelişmiş", () => {
  it("E2EB-F15 (FIX-K): step 3 offers 'Meta veriyi yeniden oku' (POST /discover) once a metadata URL is saved", async () => {
    const p = provider({ metadata_signing_cert: FED }, { status: "error", discovery: { ok: false, checks: [{ key: "metadata_signature", ok: false, tr: "Meta veri imzalı değil.", en: "The metadata is not signed.", detail: "unsigned" }], fetched_at: null } });
    const f = mockFetch((url, init) => {
      if (url.includes("/providers/7/setup")) return { status: 200, body: setup(p) };
      if (url.endsWith("/providers/7/discover") && init?.method === "POST") return { status: 200, body: { ok: true, checks: [] } };
      return undefined;
    });
    wrap(<ProviderWizard providerId={7} onBack={() => undefined} />);
    await screen.findByTestId("idp-wizard");
    fireEvent.click(screen.getByTestId("idp-step-values"));
    const btn = await screen.findByTestId("idp-values-rediscover");
    expect(btn).toHaveTextContent("Meta veriyi yeniden oku");
    fireEvent.click(btn);
    await waitFor(() => expect(f.mock.calls.some(([u, init]) => String(u).endsWith("/providers/7/discover") && init?.method === "POST")).toBe(true));
  });

  it("keeps the advanced fields closed until Gelişmiş is opened (simplicity)", async () => {
    await openAdvanced(provider());
    const toggle = screen.getByTestId("idp-saml-advanced-toggle");
    expect(toggle).toHaveTextContent("Gelişmiş");
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByTestId("idp-fed-cert")).toBeNull();
    expect(screen.queryByTestId("idp-sp-generate")).toBeNull();
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByTestId("idp-fed-cert")).toBeInTheDocument();
    expect(screen.getByTestId("idp-sp-generate")).toHaveTextContent("SP anahtarı oluştur");
    expect(screen.getByTestId("idp-sign-requests")).toHaveAttribute("aria-checked", "false");
    expect(screen.getByTestId("idp-sp-none")).toHaveTextContent("SP anahtarı yok");
  });

  it("opens by itself when the metadata signature check failed, with its Turkish reason", async () => {
    const reason = "Meta veri imzalı değil. Federasyon sertifikası girildiği için imzasız meta veri kabul edilmez: federasyonun imzalı meta veri adresini kullanın.";
    await openAdvanced(
      provider(
        { metadata_signing_cert: FED, metadata_signed: false },
        { discovery: { ok: false, checks: [{ key: "metadata_signature", ok: false, tr: reason, en: "The metadata is not signed.", detail: "unsigned" }], fetched_at: null } },
      ),
    );
    expect(screen.getByTestId("idp-saml-advanced-toggle")).toHaveAttribute("aria-expanded", "true");
    const fed = screen.getByTestId("idp-fed-details");
    expect(within(fed).getByTestId("idp-check-metadata_signature")).toHaveTextContent(reason);
    expect(screen.getByTestId("idp-metadata-signed")).toHaveAttribute("data-ok", "false");
  });

  it("shows the certificates read-only and never the private key: only “anahtar kayıtlı”", async () => {
    await openAdvanced(provider({ metadata_signing_cert: FED, metadata_signed: true, sp_certificate: SPC, sp_private_key_set: true }));
    fireEvent.click(screen.getByTestId("idp-saml-advanced-toggle"));
    const fed = screen.getByTestId("idp-fed-details");
    expect(fed).toHaveTextContent("CN=YETKİM Metadata İmzalama");
    expect(fed).toHaveTextContent("AB:CD:EF:01");
    expect(fed).toHaveTextContent("18.10.2027");
    expect(screen.getByTestId("idp-metadata-signed")).toHaveAttribute("data-ok", "true");
    expect(screen.getByTestId("idp-metadata-signed")).toHaveTextContent("Meta veri imzalı ve doğrulandı");
    const sp = screen.getByTestId("idp-sp-details");
    expect(sp).toHaveTextContent("CN=rezervasyon.uni.edu.tr");
    expect(sp).toHaveTextContent("12:34:56:78");
    expect(screen.getByTestId("idp-sp-set")).toHaveTextContent("Anahtar kayıtlı");
    // write-only: no key field while one is kept, and nothing of it on the page
    expect(screen.queryByTestId("idp-sp-private-key")).toBeNull();
    expect(screen.queryByTestId("idp-sp-generate")).toBeNull();
    expect(document.body.textContent).not.toMatch(/PRIVATE KEY/);
  });

  it("saves and removes the federation certificate (empty removes it)", async () => {
    const f = await openAdvanced(provider({ metadata_signing_cert: FED, metadata_signed: true }));
    fireEvent.click(screen.getByTestId("idp-saml-advanced-toggle"));
    const pem = "-----BEGIN CERTIFICATE-----\nMIIC\n-----END CERTIFICATE-----";
    fireEvent.change(screen.getByTestId("idp-fed-cert"), { target: { value: pem } });
    fireEvent.click(screen.getByTestId("idp-fed-save"));
    await waitFor(() => expect(puts(f)).toHaveLength(1));
    expect(puts(f)[0]).toEqual({ version: VERSION, metadata_signing_cert: pem });
    await waitFor(() => expect(screen.getByTestId("idp-fed-cert")).toHaveValue(""));
    fireEvent.click(screen.getByTestId("idp-fed-remove"));
    await waitFor(() => expect(puts(f)).toHaveLength(2));
    expect(puts(f)[1]).toEqual({ version: VERSION, metadata_signing_cert: "" });
  });

  it("generates an SP key with one tap", async () => {
    const f = await openAdvanced(provider());
    fireEvent.click(screen.getByTestId("idp-saml-advanced-toggle"));
    fireEvent.click(screen.getByTestId("idp-sp-generate"));
    await waitFor(() => expect(puts(f)).toHaveLength(1));
    expect(puts(f)[0]).toEqual({ version: VERSION, sp_key_generate: true });
  });

  it("E2EB-F17: after 'SP anahtarı oluştur' focus is on 'Kaldır', never on <body>", async () => {
    let current = provider();
    mockFetch((url, init) => {
      if (url.includes("/providers/7/setup")) return { status: 200, body: setup(current) };
      if (url.endsWith("/auth/sso/admin/providers/7") && init?.method === "PUT") {
        current = provider({ sp_certificate: SPC, sp_private_key_set: true });
        return { status: 200, body: current };
      }
      return undefined;
    });
    wrap(<ProviderWizard providerId={7} onBack={() => undefined} />);
    await screen.findByTestId("idp-wizard");
    fireEvent.click(screen.getByTestId("idp-step-values"));
    fireEvent.click(screen.getByTestId("idp-saml-advanced-toggle"));
    const gen = screen.getByTestId("idp-sp-generate");
    gen.focus();
    fireEvent.click(gen);
    const remove = await screen.findByTestId("idp-sp-remove");
    await waitFor(() => expect(document.activeElement).toBe(remove));
  });

  it("E2EB-F04: below sm the step footer ('Kaydet') sticks above the tab bar, not under it", async () => {
    await openAdvanced(provider());
    const footer = screen.getByTestId("idp-values-save").closest("[data-slot=step-footer]") as HTMLElement;
    expect(footer).not.toBeNull();
    expect(footer.className).toContain("max-sm:bottom-[calc(var(--shell-bottom-h)+0.5rem)]");
    expect(footer.className).not.toMatch(/(^| )bottom-0( |$)/);
  });

  it("pastes an SP key and certificate, then clears the fields", async () => {
    const f = await openAdvanced(provider());
    fireEvent.click(screen.getByTestId("idp-saml-advanced-toggle"));
    fireEvent.click(screen.getByTestId("idp-sp-paste-toggle"));
    const key = "-----BEGIN PRIVATE KEY-----\nMIIE\n-----END PRIVATE KEY-----";
    const cert = "-----BEGIN CERTIFICATE-----\nMIIC\n-----END CERTIFICATE-----";
    const keyField = screen.getByTestId("idp-sp-private-key");
    expect(keyField).toHaveAttribute("autocomplete", "off");
    fireEvent.change(keyField, { target: { value: key } });
    fireEvent.change(screen.getByTestId("idp-sp-certificate"), { target: { value: cert } });
    fireEvent.click(screen.getByTestId("idp-sp-save"));
    await waitFor(() => expect(puts(f)).toHaveLength(1));
    expect(puts(f)[0]).toEqual({ version: VERSION, sp_private_key: key, sp_certificate: cert });
    await waitFor(() => expect(screen.getByTestId("idp-sp-private-key")).toHaveValue(""));
  });

  it("removes the SP key only after a confirmation and shows the 409 sp_key_in_use reason", async () => {
    const inUse = "İstekler bu anahtarla imzalanıyor: önce istek imzalamayı kapatın";
    const f = await openAdvanced(provider({ sp_certificate: SPC, sp_private_key_set: true, sign_requests: true }), () => ({
      status: 409,
      body: { detail: { code: "sp_key_in_use", tr: inUse, en: "the requests are signed with this key: switch request signing off first" } },
    }));
    fireEvent.click(screen.getByTestId("idp-saml-advanced-toggle"));
    fireEvent.click(screen.getByTestId("idp-sp-remove"));
    expect(puts(f)).toHaveLength(0);
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("SP anahtarı kaldırılsın mı?");
    fireEvent.click(within(dialog).getByRole("button", { name: "Anahtarı kaldır" }));
    await waitFor(() => expect(puts(f)).toHaveLength(1));
    expect(puts(f)[0]).toEqual({ version: VERSION, sp_key_remove: true });
    expect(await screen.findByText(inUse)).toBeInTheDocument();
  });

  it("switches request signing and shows the 422 sp_key_required reason", async () => {
    const needsKey = "İstekleri imzalamak için bir SP anahtarı gerekli: önce anahtar oluşturun ya da yapıştırın";
    const f = await openAdvanced(provider(), () => ({ status: 422, body: { detail: { code: "sp_key_required", tr: needsKey, en: "signing the requests needs an SP key" } } }));
    fireEvent.click(screen.getByTestId("idp-saml-advanced-toggle"));
    fireEvent.click(screen.getByTestId("idp-sign-requests"));
    await waitFor(() => expect(puts(f)).toHaveLength(1));
    expect(puts(f)[0]).toEqual({ version: VERSION, sign_requests: true });
    expect(await screen.findByText(needsKey)).toBeInTheDocument();
  });

  it("speaks English when the interface is English", async () => {
    await openAdvanced(provider({ sp_certificate: SPC, sp_private_key_set: true }), undefined, "en");
    const toggle = screen.getByTestId("idp-saml-advanced-toggle");
    expect(toggle).toHaveTextContent("Advanced");
    fireEvent.click(toggle);
    expect(screen.getByTestId("idp-sp-set")).toHaveTextContent("Key saved");
    expect(screen.getByTestId("idp-sign-requests-row")).toHaveTextContent("Sign requests");
  });
});
