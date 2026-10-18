// FIX-K (fix-k-2026-10-18): E2EA-F10 "Davet et" with password sign-in only (a local-password invite), and
// E2EA2-F03 the users pager keeps focus on a control when Sonraki / Önceki disable themselves.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
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
import { InviteSheet } from "./users-admin-identity";

beforeAll(() => {
  if (!document.elementFromPoint) Object.defineProperty(document, "elementFromPoint", { value: () => null, configurable: true });
});

const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const USER = { id: 7, email: "kisi.a@ornek.edu.tr", username: "kisi.a", displayname: "Kişi A", role: "PLANNER", role_id: 2, role_name: "Planlamacı", is_active: true, has_password: true, auth_source: "local", last_login_at: null, force_password_reset: false };
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
    "/api/v1/auth/sso/invites/inv-token": () => res(200, { provider: "local", login_hint: "kisi.a@ornek.edu.tr" }),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url).split("?")[0]!;
      calls.push(`${init?.method ?? "GET"} ${String(url)}`);
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

describe("Davet et without Microsoft sign-in (E2EA-F10)", () => {
  it("shows Davet et beside Yeni kullanıcı and opens a local-password invite", async () => {
    wrap(<UsersAdmin />);
    const invite = await screen.findByTestId("users-invite");
    expect(screen.getByTestId("users-new")).toHaveTextContent("Yeni kullanıcı");
    fireEvent.click(invite);
    expect(await screen.findByTestId("invite-sheet")).toHaveTextContent("Kişi bağlantıyı açıp kendi parolasını belirler.");
  });

  it("the local invite sends provider local", async () => {
    let posted: Record<string, unknown> | null = null;
    routes["/api/v1/auth/sso/admin/invite-mail"] = () => res(200, { configured: false });
    routes["/api/v1/auth/sso/admin/invites"] = () => res(201, { id: 9, user_id: 5, email: "kisi.b@ornek.edu.tr", kind: "local", status: "invited", created_at: "2026-10-18T08:00:00Z", expires_at: "2026-10-25T08:00:00Z", link: "https://x/login?invite=abc", email_status: null });
    const f = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    const inner = f.getMockImplementation()!;
    f.mockImplementation(async (url: string, init?: RequestInit) => {
      if (String(url).endsWith("/auth/sso/admin/invites") && init?.method === "POST") posted = JSON.parse(String(init.body));
      return inner(url, init);
    });
    wrap(<InviteSheet open onOpenChange={() => undefined} auth={undefined} canListRoles={false} local />);
    fireEvent.change(await screen.findByTestId("invite-email"), { target: { value: "kisi.b@ornek.edu.tr" } });
    fireEvent.click(await screen.findByTestId("invite-role-code:TEACHER"));
    fireEvent.click(screen.getByRole("button", { name: "Davet et" }));
    await waitFor(() => expect(posted).toMatchObject({ email: "kisi.b@ornek.edu.tr", provider: "local" }));
  });
});

describe("users pager focus (E2EA2-F03)", () => {
  it("Sonraki to the last page moves focus to Önceki, Önceki to the first page moves it to Sonraki", async () => {
    routes["/api/v1/users/search"] = () => res(200, { items: [USER], total: 30, limit: 25, offset: 0 });
    wrap(<UsersAdmin />);
    const next = await screen.findByRole("button", { name: "Sonraki" });
    next.focus();
    fireEvent.click(next);
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Önceki" })));
    fireEvent.click(screen.getByRole("button", { name: "Önceki" }));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Sonraki" })));
  });
});
