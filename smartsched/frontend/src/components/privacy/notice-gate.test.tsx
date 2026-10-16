/** The first-sign-in notice gate (round-1 T-R1-28, R1-A-15): "Okudum" closes it at once and hands focus to the page
 * (#main), never to <body>; an administrator's "Daha sonra" does the same. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

vi.mock("next/navigation", () => ({ usePathname: () => "/bookings", useRouter: () => ({ replace: vi.fn(), push: vi.fn() }) }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), message: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/components/bookings/use-is-phone", () => ({ useIsPhone: () => false }));
const perms = vi.hoisted(() => ({ admin: false }));
vi.mock("@/lib/api/shell-extra", () => ({
  usePermissions: () => ({ perms: [], me: { id: 5, force_password_reset: false }, can: (p: string) => perms.admin && p === "setup.settings" }),
}));
const api = vi.hoisted(() => ({ acked: false, calls: [] as string[] }));
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { method?: string } = {}) => {
      const method = opts.method ?? "GET";
      api.calls.push(`${method} ${path}`);
      if (path === "/me/privacy" && method === "GET")
        return {
          notice: { id: 3, version: 1, language: "tr", title: "Aydınlatma metni", body_md: "Verileriniz KVKK kapsamında işlenir.", published_at: "2026-10-16T09:00:00" },
          needs_ack: !api.acked,
          consents: [],
          requests: [],
        };
      if (path === "/me/privacy/ack" && method === "POST") {
        api.acked = true;
        return { notice_id: 3, acked_at: "2026-10-16T10:00:00" };
      }
      throw new Error(`unexpected ${method} ${path}`);
    },
  };
});

import { PrivacyNoticeGate } from "./notice-gate";

function renderGate() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="tr">
        <main id="main" tabIndex={-1}>
          <h1>Rezervasyonlar</h1>
        </main>
        <PrivacyNoticeGate />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.acked = false;
  api.calls = [];
  perms.admin = false;
  window.sessionStorage.clear();
});

describe("PrivacyNoticeGate focus", () => {
  it("closes on Okudum and focuses #main", async () => {
    renderGate();
    const ok = await screen.findByTestId("notice-gate-ack");
    expect(screen.getByText("Aydınlatma metni")).toBeTruthy();
    await userEvent.click(ok);
    await waitFor(() => expect(screen.queryByTestId("notice-gate")).toBeNull());
    expect(api.calls).toContain("POST /me/privacy/ack");
    await waitFor(() => expect(document.activeElement?.id).toBe("main"));
    expect(document.activeElement).not.toBe(document.body);
  });

  it("an administrator's Daha sonra also hands focus to the page", async () => {
    perms.admin = true;
    renderGate();
    await userEvent.click(await screen.findByTestId("notice-gate-later"));
    await waitFor(() => expect(screen.queryByTestId("notice-gate")).toBeNull());
    await waitFor(() => expect(document.activeElement?.id).toBe("main"));
    expect(api.calls).not.toContain("POST /me/privacy/ack");
  });
});
