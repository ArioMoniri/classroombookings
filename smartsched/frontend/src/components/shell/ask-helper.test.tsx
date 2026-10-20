/**
 * HX-03 / HX-10 shell asks (helper.md §2.2): "Yardımcıya sor" as the first row of the user menu's Yardım group and
 * of the phone "Daha" › Yardım group (it opens the helper sheet; hidden when an administrator switched the helper off
 * for the person), and the "Fakültemin yapay zekâ kullanımı" nav entry for `ai.usage_faculty` holders only.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";
import { useHelperStore } from "@/components/helper/helper-store";
import { mockMedia, resetWelcomeStore } from "@/components/welcome/test-helpers";
import { visibleNavGroups } from "./nav-config";

const nav = vi.hoisted(() => ({ pathname: "/reserve" }));
vi.mock("next/navigation", () => ({
  usePathname: () => nav.pathname,
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { AppShell } from "./app-shell";

const TEACHER = ["book_single.create", "book_recur.create", "room.view"];
let helperEnabled = true;

function stubFetch(permissions: string[]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      const path = new URL(url, "http://localhost").pathname;
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (path === "/api/v1/auth/me") return json({ id: 7, email: "ayse@uni.edu.tr", username: "ayse", full_name: "Ayşe Tekin", role: "TEACHER", permissions });
      if (path === "/api/v1/helper/status") return json({ mode: "index", enabled: helperEnabled, reason: helperEnabled ? "index_mode" : "disabled" });
      if (path.startsWith("/api/v1/me/notifications") || path === "/api/v1/approvals/inbox") return json([]);
      return json({ detail: "not in this test" }, 404);
    }),
  );
}

function renderShell() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider initialLocale="tr">
        <AppShell>
          <h1>Hızlı rezervasyon</h1>
        </AppShell>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  resetWelcomeStore();
  Element.prototype.scrollIntoView = vi.fn();
  nav.pathname = "/reserve";
  helperEnabled = true;
  useHelperStore.setState({ open: false });
  useUiStore.setState({ paletteOpen: false, drawerOpen: false, sidebarCollapsed: false });
  mockMedia((q) => q.includes("min-width: 1024px"));
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("Yardımcıya sor in the shell", () => {
  it("is the first row of the user menu's Yardım group and opens the helper sheet", async () => {
    stubFetch(TEACHER);
    renderShell();
    const aside = await screen.findByRole("complementary", {}, { timeout: 15_000 });
    await userEvent.click(await within(aside).findByTestId("user-menu", {}, { timeout: 15_000 }));
    const item = await screen.findByTestId("help-ask-helper", {}, { timeout: 15_000 });
    expect(item).toHaveTextContent("Yardımcıya sor");
    await userEvent.click(item);
    await waitFor(() => expect(useHelperStore.getState().open).toBe(true));
  }, 30_000);

  it("is in the phone Daha › Yardım group", async () => {
    mockMedia((q) => q.includes("max-width") || q.includes("coarse"));
    stubFetch(TEACHER);
    renderShell();
    await screen.findByRole("heading", { level: 1, name: "Hızlı rezervasyon" }, { timeout: 15_000 });
    act(() => useUiStore.getState().setDrawerOpen(true));
    const row = await screen.findByTestId("drawer-ask-helper", {}, { timeout: 15_000 });
    expect(row).toHaveTextContent("Yardımcıya sor");
    await userEvent.click(row);
    await waitFor(() => expect(useUiStore.getState().drawerOpen).toBe(false));
    await waitFor(() => expect(useHelperStore.getState().open).toBe(true));
  }, 30_000);

  it("is not offered when the helper is switched off for the person", async () => {
    helperEnabled = false;
    stubFetch(TEACHER);
    renderShell();
    const aside = await screen.findByRole("complementary", {}, { timeout: 15_000 });
    await userEvent.click(await within(aside).findByTestId("user-menu", {}, { timeout: 15_000 }));
    // the menu is open (its Yardım group has no "Yenilikler" row any more: the header's button is the one entry)
    await screen.findByTestId("logout", {}, { timeout: 15_000 });
    expect(screen.queryByTestId("help-ask-helper")).toBeNull();
  }, 30_000);
});

describe("Fakültemin yapay zekâ kullanımı (nav)", () => {
  const can = (perms: string[]) => (p: string | readonly string[] | undefined) => !p || (Array.isArray(p) ? p : [p]).some((x) => perms.includes(x as string));
  const hrefs = (perms: string[]) => visibleNavGroups(can(perms)).flatMap((g) => g.items.map((i) => i.href));
  it("is listed for ai.usage_faculty holders only, and not for administrators (they have /admin/ai)", () => {
    expect(hrefs([...TEACHER, "ai.usage_faculty"])).toContain("/ai/faculty");
    expect(hrefs(TEACHER)).not.toContain("/ai/faculty");
    expect(hrefs(["planning.admin", "setup.settings", "ai.usage_faculty"])).not.toContain("/ai/faculty");
  });
});
