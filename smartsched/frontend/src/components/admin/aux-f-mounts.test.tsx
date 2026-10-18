// AUX-F mounts (docs/design/v3/auth.md §4.5, §6, §7, §9, §10.2): Admin › Kullanıcılar row menu gets the "Giriş" group
// (no "Tek kullanımlık sıfırlama kodu"; "Sıfırlama kodunu ekranda göster" shows the code), Ayarlar gets the
// "Giriş güvenliği" tab, the profile password form follows password_min_length, the local invite is SetPasswordForm,
// and every field carries the :autofill rule.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { fieldSurface } from "@/components/ui/field-styles";
import { LocalInviteAccept } from "@/components/identity/local-invite-accept";
import { I18nProvider } from "@/lib/i18n/provider";

const nav = vi.hoisted(() => ({ search: "" }));
vi.mock("next/navigation", () => ({ usePathname: () => "/admin/users", useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }), useSearchParams: () => new URLSearchParams(nav.search) }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), message: vi.fn() }) }));
const PERMS = ["setup.users", "setup.authentication", "setup.settings"];
vi.mock("@/lib/permissions", async (orig) => ({
  ...(await orig<typeof import("@/lib/permissions")>()),
  usePermissions: () => ({ perms: PERMS, can: (p: string | string[]) => (Array.isArray(p) ? p.some((x) => PERMS.includes(x)) : PERMS.includes(p)), canAll: () => true, userId: 1, loading: false }),
}));
vi.mock("@/lib/api/shell-extra", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/shell-extra")>()),
  usePermissions: () => ({ perms: PERMS, me: undefined, can: (p: string | string[]) => (Array.isArray(p) ? p.some((x) => PERMS.includes(x)) : PERMS.includes(p)) }),
}));
vi.mock("@/components/bookings/use-is-phone", () => ({ useIsPhone: () => false, useIsCompact: () => false }));

import { UsersAdmin } from "./users-admin";
import { SettingsView } from "@/components/settings/settings-view";

beforeAll(() => {
  if (!document.elementFromPoint) Object.defineProperty(document, "elementFromPoint", { value: () => null, configurable: true });
});

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const USER = { id: 7, email: "ayse@ornek.edu.tr", username: "ayse", displayname: "Ayşe Yılmaz", role: "PLANNER", role_id: 2, role_name: "Planlamacı", is_active: true, has_password: true, auth_source: "local", last_login_at: null, force_password_reset: false };
let calls: string[];
let routes: Record<string, () => Response>;
beforeEach(() => {
  calls = [];
  nav.search = "";
  routes = {
    "/api/v1/users/search": () => res(200, { items: [USER], total: 1, limit: 25, offset: 0 }),
    "/api/v1/auth/sso/providers": () => res(200, { auth: { microsoft: { enabled: false }, local_enabled: true } }),
    "/api/v1/auth/sso/admin/user-status": () => res(200, { "7": { status: "none", auth_methods: ["local"] } }),
    "/api/v1/admin/auth/mfa-policy": () => res(200, { mfa_policy: "optional", mfa_roles: ["ADMIN"], mfa_grace_days: 14, passkeys_enabled: true, passkey_first_factor: false, trusted_device_days: 30 }),
    "/api/v1/users/7/reset-token": () => res(200, { token: "RESET-CODE-123", expires_at: "2026-10-19T09:00:00" }),
    "/api/v1/auth/sso/invites/inv-token": () => res(200, { provider: "local", login_hint: "ayse@ornek.edu.tr" }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url).split("?")[0]!;
      calls.push(`${init?.method ?? "GET"} ${path}`);
      return routes[path]?.() ?? res(200, []);
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

describe("Admin › Kullanıcılar (A5)", () => {
  it("the row menu has the 'Giriş' group, no 'Tek kullanımlık sıfırlama kodu'; the on-screen code still works", async () => {
    wrap(<UsersAdmin />);
    fireEvent.click(await screen.findByRole("button", { name: "ayse için işlemler" }));
    expect(await screen.findByTestId("user-security-menu-7")).toBeInTheDocument();
    expect(screen.getByTestId("user-send-link-7")).toHaveTextContent("Parola sıfırlama bağlantısı gönder");
    expect(screen.getByTestId("user-reset-mfa-7")).toHaveTextContent("2FA'yı sıfırla");
    expect(screen.getByTestId("user-end-sessions-7")).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Tek kullanımlık sıfırlama kodu/ })).toBeNull();
    fireEvent.click(screen.getByTestId("user-show-code-7"));
    await waitFor(() => expect(calls).toContain("POST /api/v1/users/7/reset-token"));
  });
});

describe("2FA state in the list (AU-18)", () => {
  it("tags 'pending' without a grace date as 'ilk girişte başlar', shows the filter, and the filter narrows the rows", async () => {
    const OTHER = { ...USER, id: 8, username: "mehmet", email: "mehmet@ornek.edu.tr", displayname: "Mehmet Kaya" };
    routes["/api/v1/users/search"] = () => res(200, { items: [USER, OTHER], total: 2, limit: 25, offset: 0 });
    routes["/api/v1/auth/sso/admin/user-status"] = () => res(200, { "7": { status: "none", auth_methods: ["local"], mfa_state: "pending", mfa_grace_until: null }, "8": { status: "none", auth_methods: ["local"], mfa_state: "on", mfa_grace_until: null } });
    wrap(<UsersAdmin />);
    expect((await screen.findAllByTestId("mfa-tag-pending"))[0]).toHaveTextContent("2FA bekleniyor (ilk girişte başlar)");
    expect(screen.getAllByTestId("mfa-tag")[0]).toHaveTextContent("2FA");
    const filter = screen.getAllByTestId("mfa-filter")[0]!;
    fireEvent.change(filter, { target: { value: "on" } });
    await waitFor(() => expect(screen.queryByRole("button", { name: "ayse için işlemler" })).toBeNull());
    expect(screen.getByRole("button", { name: "mehmet için işlemler" })).toBeInTheDocument();
  });

  it("no mfa_state anywhere (identity-provider-only map): no filter", async () => {
    wrap(<UsersAdmin />);
    await screen.findByRole("button", { name: "ayse için işlemler" });
    expect(screen.queryByTestId("mfa-filter")).toBeNull();
  });
});

describe("Ayarlar (A6)", () => {
  it("shows the 'Giriş güvenliği' tab with setup.authentication and opens the policy card", async () => {
    nav.search = "tab=signin-security";
    wrap(<SettingsView />);
    expect(await screen.findByTestId("tab-signin-security")).toHaveTextContent("Giriş güvenliği");
    expect(await screen.findByTestId("signin-security")).toBeInTheDocument();
  });
});

describe("local invite (A3) and the field surface", () => {
  it("the invite is SetPasswordForm: one password field, no repeat, the hidden username for password managers", async () => {
    wrap(<LocalInviteAccept token="inv-token" org="Örnek Üniversitesi" />);
    expect(await screen.findByText("Parolanızı belirleyin")).toBeInTheDocument();
    const form = screen.getByTestId("local-invite-form");
    expect(form.querySelectorAll('input[type="password"]')).toHaveLength(1);
    await waitFor(() => expect(form.querySelector<HTMLInputElement>('input[autocomplete="username"]')?.value).toBe("ayse@ornek.edu.tr"));
    expect(form.querySelector('input[autocomplete="new-password"]')).toHaveAttribute("minlength", "12");
  });

  it("every field surface carries the :autofill rule (no browser yellow, label-1 text)", () => {
    expect(fieldSurface).toContain("autofill:shadow-[inset_0_0_0_100vmax_color-mix(in_oklab,var(--tint)_7%,var(--mat-thick-solid)),var(--edge-control)]");
    expect(fieldSurface).toContain("autofill:[-webkit-text-fill-color:var(--label-1)]");
  });
});
