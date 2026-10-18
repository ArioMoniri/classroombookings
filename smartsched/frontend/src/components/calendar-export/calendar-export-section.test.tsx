/** CAL-08 Profil › Takvim: the entry button, the KVKK-off state, and the push approval resumed after the OAuth round trip. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

// real user events through a sheet: generous on the shared, loaded host
vi.setConfig({ testTimeout: 20_000 });

type Call = { path: string; method: string; body?: unknown };
const api = vi.hoisted(() => ({ options: null as unknown, subs: [] as unknown[], calls: [] as Call[] }));
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { method?: string; body?: unknown; schema?: { parse: (v: unknown) => unknown } } = {}) => {
      const method = opts.method ?? "GET";
      api.calls.push({ path, method, body: opts.body });
      const parse = (v: unknown) => (opts.schema ? opts.schema.parse(v) : v);
      if (path === "/calendar/export/options") return parse(api.options);
      if (path === "/calendar/subscriptions") return parse(api.subs);
      if (path.endsWith("/scopes")) return {};
      throw new Error(`unexpected ${method} ${path}`);
    },
  };
});

import { CalendarExportButton, CalendarExportSection } from "./calendar-export-section";

function renderIt(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="tr">{node}</I18nProvider>
    </QueryClientProvider>,
  );
}

const opts = { enabled: true, scopes: [{ kind: "my_classes", available: true, hours: 6 }], channels: { link: true, file: true, push: [{ provider: "google", configured: true, connected: true }] } };

beforeEach(() => {
  api.options = opts;
  api.subs = [];
  api.calls = [];
  window.sessionStorage.clear();
  window.history.replaceState(null, "", "/profile");
});

describe("CalendarExportSection", () => {
  it("opens the sheet from Takvimime ekle and lists nothing yet", async () => {
    const user = userEvent.setup();
    renderIt(<CalendarExportSection />);
    expect(await screen.findByTestId("cal-manage-empty")).toBeInTheDocument();
    await user.click(screen.getByTestId("cal-open"));
    expect(await screen.findByTestId("cal-sheet")).toBeInTheDocument();
    expect(await screen.findByTestId("cal-scope-my_classes")).toHaveTextContent("bu dönem 6 ders saati");
  });

  it("with sync off says so quietly and offers no button", async () => {
    api.options = { ...opts, enabled: false };
    renderIt(<CalendarExportSection />);
    expect(await screen.findByText(/Takvim aktarımı kurumunuzda kapalı/)).toBeInTheDocument();
    expect(screen.queryByTestId("cal-open")).toBeNull();
  });

  it("resumes a push approval after ?calendar=connected: the backend applied the scope, the sheet shows the progress", async () => {
    window.sessionStorage.setItem("smartsched.calendarExport.pending", JSON.stringify({ provider: "google", kind: "department_classes", departmentId: 7, at: Date.now() }));
    window.history.replaceState(null, "", "/profile?calendar=connected&provider=google");
    renderIt(<CalendarExportSection />);
    expect(await screen.findByTestId("cal-push-done")).toHaveTextContent("Google Takvim takviminize ekleniyor…");
    // connect carried the scopes (API.md): nothing is PUT again on the way back
    expect(api.calls.some((c) => c.path.endsWith("/scopes"))).toBe(false);
    expect(window.sessionStorage.getItem("smartsched.calendarExport.pending")).toBeNull();
  });

  it("drops the stored scope after ?calendar=error", async () => {
    window.sessionStorage.setItem("smartsched.calendarExport.pending", JSON.stringify({ provider: "google", kind: "my_classes", departmentId: null, at: Date.now() }));
    window.history.replaceState(null, "", "/profile?calendar=error&reason=denied");
    renderIt(<CalendarExportSection />);
    await screen.findByTestId("cal-open");
    await waitFor(() => expect(window.sessionStorage.getItem("smartsched.calendarExport.pending")).toBeNull());
    expect(api.calls.some((c) => c.path.endsWith("/scopes"))).toBe(false);
    expect(screen.queryByTestId("cal-sheet")).toBeNull();
  });
});

describe("CalendarExportSection › account not verified (CAL-07)", () => {
  it("says which account to use after ?calendar=error&reason=account_not_verified", async () => {
    window.history.replaceState(null, "", "/profile?calendar=error&provider=google&reason=account_not_verified&domain=uni.edu.tr");
    renderIt(<CalendarExportSection />);
    expect(await screen.findByTestId("cal-not-verified")).toHaveTextContent("Bu hesap kurumunuzun doğrulanmış hesabı değil. uni.edu.tr uzantılı hesabınızla bağlanın.");
  });
  it("says kurumsal without a domain", async () => {
    window.history.replaceState(null, "", "/profile?calendar=error&provider=google&reason=account_not_verified");
    renderIt(<CalendarExportSection />);
    expect(await screen.findByTestId("cal-not-verified")).toHaveTextContent("Kurumsal hesabınızla bağlanın.");
  });
});

describe("CalendarExportButton", () => {
  it("opens the same sheet from another page", async () => {
    const user = userEvent.setup();
    renderIt(<CalendarExportButton />);
    await user.click(screen.getByTestId("cal-open-button"));
    expect(await screen.findByRole("heading", { name: "Neyi eklemek istiyorsunuz?" })).toBeInTheDocument();
  });
});
