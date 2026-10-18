// HB-23c (helper-file-router.md §6.5): `/admin/users?import=1&from=helper` opens Kullanıcılar › İçe aktar with the
// helper's file row in place of the file field; "İçe aktar" sends `upload_token` (no bytes) with the page's own
// defaults; ✕ deletes the stage and the file field comes back. `?import=1` alone opens the sheet empty.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { useFileHandoffStore } from "@/components/helper/file-handoff";
import { I18nProvider } from "@/lib/i18n/provider";

const nav = vi.hoisted(() => ({ search: "import=1&from=helper", replace: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => "/admin/users", useRouter: () => ({ push: vi.fn(), replace: nav.replace, refresh: vi.fn() }), useSearchParams: () => new URLSearchParams(nav.search) }));
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), message: vi.fn() }) }));
const PERMS = ["setup.users"];
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

const TOKEN = "eyJzaWQiOiJzdGFnZXVzZXJzIn0.c2lnbmF0dXJlLXNpZ25hdHVyZQ";
const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
let calls: { key: string; form: FormData | null }[];
const onlyAdmin = { value: false };
const ADMIN = { id: 1, email: "yonetici@ornek.edu.tr", username: "yonetici", displayname: "Yönetici", role: "ADMIN", role_id: 1, role_name: "Yönetici", is_active: true, has_password: true, auth_source: "local", last_login_at: null, force_password_reset: false };
beforeEach(() => {
  calls = [];
  onlyAdmin.value = false;
  nav.search = "import=1&from=helper";
  nav.replace.mockReset();
  useFileHandoffStore.getState().set({
    featureId: "admin.users",
    kind: "users_csv",
    params: { import: 1 },
    items: [{ token: TOKEN, sid: "stageusers", name: "kullanicilar.csv", size: 2048, format: "csv", expiresAt: Date.now() + 9 * 60_000 }],
    at: Date.now(),
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = String(url).split("?")[0]!;
      calls.push({ key: `${init?.method ?? "GET"} ${path}`, form: init?.body instanceof FormData ? init.body : null });
      if (path === "/api/v1/users/search") return res(200, onlyAdmin.value ? { items: [ADMIN], total: 1, limit: 25, offset: 0 } : { items: [], total: 0, limit: 25, offset: 0 });
      if (path === "/api/v1/auth/sso/providers") return res(200, { auth: { microsoft: { enabled: false }, local_enabled: true } });
      if (path === "/api/v1/users/import") return res(200, { created: 2, results: [{ line: 2, username: "a.b", status: "created" }, { line: 3, username: "c.d", status: "created" }] });
      if (init?.method === "DELETE") return res(204);
      return res(200, []);
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  useFileHandoffStore.getState().clear();
});

const wrap = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">
        <UsersAdmin />
      </I18nProvider>
    </QueryClientProvider>,
  );

describe("users import from the helper", () => {
  it("?import=1&from=helper opens the import sheet with the handed-over file row", async () => {
    wrap();
    const dialog = await screen.findByTestId("import-dialog");
    const row = within(dialog).getByTestId("users-handed-file");
    expect(row).toHaveTextContent("kullanicilar.csv");
    expect(row).toHaveTextContent("Yardımcıdan geldi");
    expect(dialog.querySelector("#imp-file")).toBeNull();
    // the address forgets ?import=1 (a reload does not reopen it)
    await waitFor(() => expect(nav.replace).toHaveBeenCalled());
    expect(String(nav.replace.mock.calls.at(-1)![0])).not.toContain("import=1");
  });

  it("HB-23d UX-05: the focus goes to 'İçe aktar', not to the row's ✕ (one Enter must not remove the file)", async () => {
    wrap();
    const dialog = await screen.findByTestId("import-dialog");
    await waitFor(() => expect(document.activeElement).toBe(within(dialog).getByTestId("import-run")));
  });

  it("İçe aktar sends upload_token instead of the bytes, with the page's defaults", async () => {
    wrap();
    const dialog = await screen.findByTestId("import-dialog");
    fireEvent.click(within(dialog).getByTestId("import-run"));
    await screen.findByTestId("import-summary");
    const sent = calls.find((c) => c.key === "POST /api/v1/users/import");
    expect(sent?.form?.get("upload_token")).toBe(TOKEN);
    expect(sent?.form?.get("file")).toBeNull();
    expect(sent?.form?.get("force_password_reset")).toBe("true");
    expect(useFileHandoffStore.getState().handoff).toBeNull();
  });

  it("✕ deletes the stage and brings the file field back", async () => {
    wrap();
    const dialog = await screen.findByTestId("import-dialog");
    fireEvent.click(within(dialog).getByTestId("users-handed-file-remove"));
    await waitFor(() => expect(calls.map((c) => c.key)).toContain("DELETE /api/v1/helper/files/stageusers"));
    expect(dialog.querySelector("#imp-file")).not.toBeNull();
  });

  it("?import=1 without a hand-over opens the sheet with the plain file field", async () => {
    useFileHandoffStore.getState().clear();
    nav.search = "import=1";
    wrap();
    const dialog = await screen.findByTestId("import-dialog");
    expect(dialog.querySelector("#imp-file")).not.toBeNull();
    expect(within(dialog).queryByTestId("users-handed-file")).toBeNull();
  });
});

describe("empty state: only the admin (helper-file-router.md §8.4)", () => {
  it("shows the one-line 'Elinizde bir dosya mı var?' link", async () => {
    useFileHandoffStore.getState().clear();
    nav.search = "";
    onlyAdmin.value = true;
    wrap();
    expect(await screen.findByTestId("helper-file-link")).toHaveTextContent("Elinizde bir dosya mı var? Bırakın, ne olduğunu söyleyelim");
  });

  it("is not shown while a search filters the list", async () => {
    useFileHandoffStore.getState().clear();
    nav.search = "q=yon";
    onlyAdmin.value = true;
    wrap();
    expect((await screen.findAllByText("Yönetici")).length).toBeGreaterThan(0);
    expect(screen.queryByTestId("helper-file-link")).toBeNull();
  });
});
