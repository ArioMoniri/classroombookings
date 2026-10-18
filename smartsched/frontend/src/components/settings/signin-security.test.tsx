// AUX-11 (docs/design/v3/auth.md §9): Ayarlar › Giriş güvenliği — the saved values round-trip to the policy, Zorunlu
// shows the role chips and the grace, saving Zorunlu / Kapalı confirms first ("İsteğe bağlı kalsın"), the self-scope
// banner, and the pure diff / confirm rules. Plus AU-16's "IdP MFA'yı zorunlu tut" switch.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { IdpMfaSwitch } from "@/components/identity/idp-mfa-switch";
import { I18nProvider } from "@/lib/i18n/provider";
import { confirmFor, policyDiff, SigninSecuritySettings, toForm } from "./signin-security";

const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: toasts }));
const perms = vi.hoisted(() => ({ list: ["setup.authentication"] as string[] }));
vi.mock("@/lib/permissions", async (orig) => ({
  ...(await orig<typeof import("@/lib/permissions")>()),
  usePermissions: () => ({ perms: perms.list, can: (p: string) => perms.list.includes(p), canAll: () => true, userId: 1, loading: false }),
}));

beforeAll(() => {
  if (!document.elementFromPoint) Object.defineProperty(document, "elementFromPoint", { value: () => null, configurable: true });
});

const POLICY = { mfa_policy: "optional", mfa_roles: ["ADMIN"], mfa_grace_days: 14, passkeys_enabled: true, passkey_first_factor: false, trusted_device_days: 30 } as const;
const ME = { available: true, reason: null, account_type: "local", policy: POLICY, passkeys_available: true, required: false, grace_until: null, totp: { enabled: false, enabled_at: null }, recovery_codes: { remaining: 0, total: 10 }, passkeys: [], trusted_devices: [], locked_until: null };
const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
let calls: { key: string; body: unknown }[];
let routes: Record<string, (b: unknown) => Response>;
beforeEach(() => {
  calls = [];
  perms.list = ["setup.authentication"];
  Object.values(toasts).forEach((f) => f.mockReset());
  routes = {
    "GET /api/v1/admin/auth/mfa-policy": () => res(200, POLICY),
    "PUT /api/v1/admin/auth/mfa-policy": (b) => res(200, { ...POLICY, ...(b as object) }),
    "GET /api/v1/auth/mfa": () => res(200, ME),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${url}`;
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ key, body });
      return routes[key]?.(body) ?? res(404, {});
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const wrap = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">{ui}</I18nProvider>
    </QueryClientProvider>,
  );
const puts = () => calls.filter((c) => c.key === "PUT /api/v1/admin/auth/mfa-policy").map((c) => c.body);

describe("rules", () => {
  it("sends only the changed fields; passwordless goes off with passkeys", () => {
    const saved = toForm({ ...POLICY, mfa_roles: ["ADMIN"] });
    expect(policyDiff(saved, saved)).toEqual({});
    expect(policyDiff(saved, { ...saved, mfa_roles: ["ADMIN"] })).toEqual({});
    expect(policyDiff({ ...saved, passkey_first_factor: true }, { ...saved, passkeys_enabled: false, passkey_first_factor: true })).toEqual({ passkeys_enabled: false, passkey_first_factor: false });
    expect(confirmFor(saved, { ...saved, mfa_policy: "required_for_roles" })).toBe("required");
    expect(confirmFor(saved, { ...saved, mfa_policy: "off" })).toBe("off");
    expect(confirmFor(saved, { ...saved, mfa_grace_days: 30 })).toBeNull();
  });
});

describe("SigninSecuritySettings", () => {
  it("Zorunlu: role chips (Yönetici on), 14 days, the sentence; saving confirms, then PUTs the change", async () => {
    wrap(<SigninSecuritySettings />);
    fireEvent.click(await screen.findByTestId("policy-required"));
    expect(screen.getByTestId("policy-role-ADMIN")).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(screen.getByTestId("policy-role-PLANNER"));
    expect(screen.getByTestId("policy-sentence")).toHaveTextContent("tarihine kadar kurmalı");
    fireEvent.click(screen.getByTestId("policy-save"));
    expect(await screen.findByTestId("policy-confirm")).toHaveTextContent("Seçilen rollerdeki kişilere e-posta gönderilecek");
    expect(puts()).toHaveLength(0);
    fireEvent.click(screen.getByTestId("policy-confirm-save"));
    await waitFor(() => expect(puts()).toEqual([{ mfa_policy: "required_for_roles", mfa_roles: ["ADMIN", "PLANNER"] }]));
    expect(toasts.success).toHaveBeenCalledWith("Giriş güvenliği kaydedildi.");
  });

  it("Kapalı confirms with 'askıya alınacak (silinmez)'; 'İsteğe bağlı kalsın' keeps optional and saves nothing", async () => {
    wrap(<SigninSecuritySettings />);
    fireEvent.click(await screen.findByTestId("policy-off"));
    fireEvent.click(screen.getByTestId("policy-save"));
    expect(await screen.findByTestId("policy-confirm")).toHaveTextContent("askıya alınacak (silinmez)");
    fireEvent.click(screen.getByTestId("policy-keep-optional"));
    expect(puts()).toHaveLength(0);
    expect(screen.getByTestId("policy-save")).toBeDisabled();
  });

  it("passwordless is nested under passkeys and the remember choice sits behind Gelişmiş", async () => {
    wrap(<SigninSecuritySettings />);
    fireEvent.click(await screen.findByTestId("policy-passwordless"));
    expect(screen.queryByTestId("policy-remember")).toBeNull();
    fireEvent.click(screen.getByTestId("policy-advanced"));
    fireEvent.click(screen.getByTestId("policy-remember-0"));
    fireEvent.click(screen.getByTestId("policy-save"));
    await waitFor(() => expect(puts()).toEqual([{ passkey_first_factor: true, trusted_device_days: 0 }]));
    expect(screen.getByTestId("policy-sso-note")).toHaveTextContent("kimlik sağlayıcısı korur");
  });

  it("the rule covers this admin without 2FA: the banner with 'Şimdi kur'", async () => {
    routes["GET /api/v1/auth/mfa"] = () => res(200, { ...ME, required: true, grace_until: "2026-11-01T09:00:00" });
    wrap(<SigninSecuritySettings />);
    expect(await screen.findByTestId("policy-self-banner")).toHaveTextContent("Bu kural sizi de kapsıyor. 1 Kasım 2026 tarihine kadar kurun.");
    expect(screen.getByTestId("policy-setup-now")).toHaveAttribute("href", "/profile#security");
  });
});

describe("IdpMfaSwitch (AU-16)", () => {
  it("saves at once through PUT …/idp-mfa; Entra gets the optional-claim note", async () => {
    routes["GET /api/v1/admin/auth/providers/idp-mfa"] = () => res(200, [{ id: 3, name: "entra", display_name: "Microsoft", kind: "entra", supported: true, require_idp_mfa: false }]);
    routes["PUT /api/v1/admin/auth/providers/3/idp-mfa"] = (b) => res(200, { id: 3, kind: "entra", supported: true, require_idp_mfa: (b as { require: boolean }).require });
    wrap(<IdpMfaSwitch providerId={3} />);
    expect(await screen.findByTestId("idp-mfa-entra")).toHaveTextContent("optional claim");
    fireEvent.click(screen.getByTestId("idp-mfa-switch"));
    await waitFor(() => expect(calls.find((c) => c.key === "PUT /api/v1/admin/auth/providers/3/idp-mfa")?.body).toEqual({ require: true }));
  });

  it("SAML explains instead of a switch; without setup.authentication nothing renders", async () => {
    routes["GET /api/v1/admin/auth/providers/idp-mfa"] = () => res(200, [{ id: 4, kind: "saml", supported: false, require_idp_mfa: false }]);
    const { unmount } = wrap(<IdpMfaSwitch providerId={4} />);
    expect(await screen.findByTestId("idp-mfa-saml")).toBeInTheDocument();
    expect(screen.queryByTestId("idp-mfa-switch")).toBeNull();
    unmount();
    perms.list = [];
    wrap(<IdpMfaSwitch providerId={4} />);
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByTestId("idp-mfa")).toBeNull();
    expect(calls.filter((c) => c.key.includes("idp-mfa"))).toHaveLength(1);
  });
});
