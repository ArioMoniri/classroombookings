/**
 * The shell must not call planning routes for people without planning.view: teachers got "Bu işlem için
 * yetkiniz yok" on every page because the sidebar badges (GET /requests NEEDS_REVIEW, GET /runs), the run
 * island (GET /runs) and the term switcher (GET /terms) asked anyway. The approvals count asks only with
 * approvals.decide. The planner case proves the spy sees those requests when they are allowed.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { useUiStore } from "@/stores/ui";

vi.mock("next/navigation", () => ({
  usePathname: () => "/bookings",
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

import { AppShell } from "./app-shell";

const TEACHER = ["book_single.create", "book_recur.create", "book_single.view_other_users"];
const PLANNER = [...TEACHER, "planning.view", "planning.edit"];

let calls: string[] = [];

function stubFetch(permissions: string[]) {
  calls = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      calls.push(url);
      const path = new URL(url, "http://localhost").pathname;
      const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
      if (path === "/api/v1/auth/me") return json({ id: 7, email: "hoca@uni.edu.tr", username: "hoca", full_name: "Deniz Kaya", role: "TEACHER", permissions });
      if (path === "/api/v1/requests/meetings") return json({ items: [], total: 0, page: 1, page_size: 1 });
      if (path.startsWith("/api/v1/me/notifications") || path === "/api/v1/runs" || path === "/api/v1/terms" || path === "/api/v1/approvals/inbox") return json([]);
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
          <p>içerik</p>
        </AppShell>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

const planningCalls = () => calls.filter((u) => /\/api\/v1\/(runs|requests|terms)(\/|\?|$)/.test(new URL(u, "http://localhost").pathname + "/"));

describe("teacher shell (no planning.view)", () => {
  beforeEach(() => useUiStore.getState().setPaletteOpen(true));
  afterEach(() => {
    vi.unstubAllGlobals();
    useUiStore.getState().setPaletteOpen(false);
  });

  it("makes no /runs, /requests or /terms requests and no approvals inbox request", async () => {
    stubFetch(TEACHER);
    renderShell();
    await waitFor(() => expect(calls.some((u) => u.includes("/auth/me"))).toBe(true));
    // let the permission-gated queries settle (they would start right after /auth/me answers)
    await waitFor(() => expect(calls.some((u) => u.includes("/me/notifications"))).toBe(true));
    await new Promise((r) => setTimeout(r, 50));
    expect(planningCalls()).toEqual([]);
    expect(calls.some((u) => u.includes("/approvals/inbox"))).toBe(false);
  });

  it("a planner's shell does ask for runs, review counts and terms (the spy works)", async () => {
    stubFetch(PLANNER);
    renderShell();
    await waitFor(() => {
      const paths = planningCalls().map((u) => new URL(u, "http://localhost").pathname);
      expect(paths).toEqual(expect.arrayContaining(["/api/v1/runs", "/api/v1/terms", "/api/v1/requests/meetings"]));
    });
  });
});
