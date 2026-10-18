// RF-B ask from AUX-F (rf-f-2026-10-18): the Admin › Kullanıcılar 2FA filter is the server's `mfa_state` parameter
// of GET /users/search (total and paging cover the filtered set), not a narrowing of the loaded page.
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

describe("2FA filter on the server (RF-B users mfa_state)", () => {
  it("sends mfa_state to GET /users/search, so the filter covers every page, and starts at the first page", async () => {
    const OTHER = { ...USER, id: 8, username: "mehmet", email: "mehmet@ornek.edu.tr", displayname: "Mehmet Kaya" };
    routes["/api/v1/users/search"] = () => res(200, { items: [USER, OTHER], total: 60, limit: 25, offset: 0 });
    routes["/api/v1/auth/sso/admin/user-status"] = () => res(200, { "7": { status: "none", auth_methods: ["local"], mfa_state: "pending", mfa_grace_until: null }, "8": { status: "none", auth_methods: ["local"], mfa_state: "on", mfa_grace_until: null } });
    wrap(<UsersAdmin />);
    const filter = (await screen.findAllByTestId("mfa-filter"))[0]!;
    fireEvent.change(filter, { target: { value: "pending" } });
    await waitFor(() => expect(calls.some((c) => c.startsWith("GET /api/v1/users/search?") && c.includes("mfa_state=pending") && c.includes("offset=0"))).toBe(true));
  });

  it("no filter chosen: no mfa_state in the search", async () => {
    routes["/api/v1/auth/sso/admin/user-status"] = () => res(200, { "7": { status: "none", auth_methods: ["local"], mfa_state: "on", mfa_grace_until: null } });
    wrap(<UsersAdmin />);
    await screen.findAllByTestId("mfa-filter");
    expect(calls.filter((c) => c.startsWith("GET /api/v1/users/search")).every((c) => !c.includes("mfa_state"))).toBe(true);
  });
});
