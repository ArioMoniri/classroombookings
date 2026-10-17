/** CAL-08 manage list: row states ("Son eşitleme", "en son … çekti"), Şimdi eşitle, Bağlantıyı yenile, Kaldır with focus to the next row, accounts. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Subscription } from "@/lib/api/calendar-export";
import { translate } from "@/lib/i18n";
import { I18nProvider } from "@/lib/i18n/provider";

type Call = { path: string; method: string; body?: unknown };
const api = vi.hoisted(() => ({ options: null as unknown, subs: [] as unknown[], calls: [] as Call[], rotate404: false }));

vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { method?: string; body?: unknown; schema?: { parse: (v: unknown) => unknown } } = {}) => {
      const method = opts.method ?? "GET";
      api.calls.push({ path, method, body: opts.body });
      const parse = (v: unknown) => (opts.schema ? opts.schema.parse(v) : v);
      if (path === "/calendar/export/options") return parse(api.options);
      if (path === "/calendar/subscriptions" && method === "GET") return parse(api.subs);
      if (path === "/calendar/subscriptions" && method === "POST") return parse({ id: 77, urls: { https: "https://plan.uni.edu.tr/api/v1/calendar/feeds/sst_new/classes.ics" } });
      if (/^\/calendar\/subscriptions\/[^/]+\/rotate$/.test(path)) {
        if (api.rotate404) throw new real.HttpError(404, "Not Found");
        return parse({ id: 3, urls: { https: "https://plan.uni.edu.tr/api/v1/calendar/feeds/sst_rot/classes.ics" } });
      }
      if (/^\/calendar\/subscriptions\/[^/]+$/.test(path) && method === "DELETE") {
        api.subs = api.subs.filter((s) => `/calendar/subscriptions/${(s as { id: number }).id}` !== path);
        return undefined;
      }
      if (path.endsWith("/resync")) return parse({ queued: 4 });
      if (path === "/calendar/connectors/google" && method === "DELETE") return undefined;
      if (path.endsWith("/connect")) return parse({ authorize_url: "https://accounts.example/again" });
      throw new Error(`unexpected ${method} ${path}`);
    },
  };
});

import { CalendarExportManage, rowState } from "./manage-list";

const assign = vi.fn();
const fallback = createRef<HTMLButtonElement>();

function renderList() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="tr">
        <button ref={fallback} type="button">
          Takvimime ekle
        </button>
        <CalendarExportManage fallbackFocus={fallback} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

const now = new Date();
const minutesAgo = (m: number) => new Date(now.getTime() - m * 60_000).toISOString();

beforeEach(() => {
  api.calls = [];
  api.rotate404 = false;
  api.options = {
    enabled: true,
    scopes: [],
    channels: { link: true, file: true, push: [{ provider: "google", configured: true, connected: true, account_email: "ayse@uni.edu.tr", account_verified: "domain", legacy_scope: true, scopes: ["my_classes"] }] },
  };
  api.subs = [
    { id: 3, scope_kind: "department_classes", scope_id: 7, scope_label: "Psikoloji", channel: "link", last_used_at: minutesAgo(1) },
    { id: 4, scope_kind: "my_classes", channel: "push", provider: "google", last_synced_at: minutesAgo(2), pending_jobs: 0 },
    { id: 5, scope_kind: "my_bookings", channel: "link", last_used_at: null },
  ];
  assign.mockReset();
  Object.defineProperty(window, "location", { configurable: true, value: { ...window.location, assign } });
});

describe("rowState", () => {
  const t = (k: Parameters<typeof translate>[1], v?: Record<string, string | number>) => translate("tr", k, v);
  it("reads like the research doc", () => {
    const fixed = new Date("2026-10-17T12:00:00Z");
    expect(rowState(Subscription.parse({ id: 1, scope_kind: "my_classes", channel: "push", provider: "google", last_synced_at: "2026-10-17T11:05:00Z" }), t, "tr", fixed)).toBe("Google Takvim · Son eşitleme bugün 14:05");
    expect(rowState(Subscription.parse({ id: 2, scope_kind: "department_classes", channel: "link", last_used_at: "2026-10-17T10:10:00Z" }), t, "tr", fixed)).toBe("Bağlantı · Takviminiz en son 13:10'da çekti");
    expect(rowState(Subscription.parse({ id: 3, scope_kind: "my_bookings", channel: "link" }), t, "tr", fixed)).toBe("Bağlantı · Takviminiz bu bağlantıyı henüz çekmedi");
    expect(rowState(Subscription.parse({ id: 4, scope_kind: "my_classes", channel: "push", provider: "google", pending_jobs: 2, failed_jobs: 1 }), t, "tr", fixed)).toBe("Google Takvim · Henüz eşitlenmedi · 2 bekliyor · 1 başarısız");
  });
});

describe("CalendarExportManage", () => {
  it("lists push first by scope, then the links, with their states", async () => {
    renderList();
    const rows = within(await screen.findByTestId("cal-manage-rows")).getAllByRole("listitem");
    expect(rows.map((r) => r.getAttribute("data-row-id"))).toEqual(["4", "3", "5"]);
    expect(rows[0]).toHaveTextContent("Derslerim");
    expect(rows[1]).toHaveTextContent("Psikoloji dersleri");
    expect(screen.getByTestId("cal-row-state-3")).toHaveTextContent(/Bağlantı · Takviminiz en son \d\d:\d\d'(da|de|ta|te) çekti/);
    expect(screen.getByTestId("cal-sync-4")).toBeInTheDocument();
    expect(screen.getByTestId("cal-rotate-3")).toBeInTheDocument();
  });

  it("Kaldır asks first, deletes, and moves focus to the next row (never <body>)", async () => {
    const user = userEvent.setup();
    renderList();
    await user.click(await screen.findByTestId("cal-remove-4"));
    const dialog = await screen.findByTestId("cal-remove-dialog");
    expect(dialog).toHaveTextContent("Derslerim kaldırılsın mı?");
    expect(dialog).toHaveTextContent("Kaldırırsanız eklenen dersler takviminizden silinir. Bağlantı aboneliğini takvim uygulamanızdan da silin.");
    await user.click(screen.getByTestId("cal-remove-confirm"));
    await waitFor(() => expect(screen.queryByTestId("cal-row-4")).not.toBeInTheDocument());
    expect(api.calls.some((c) => c.method === "DELETE" && c.path === "/calendar/subscriptions/4")).toBe(true);
    await waitFor(() => expect(screen.getByTestId("cal-rotate-3")).toHaveFocus());
  });

  it("removing the last row moves focus to the Takvimime ekle button", async () => {
    api.subs = [{ id: 5, scope_kind: "my_bookings", channel: "link" }];
    const user = userEvent.setup();
    renderList();
    await user.click(await screen.findByTestId("cal-remove-5"));
    await user.click(await screen.findByTestId("cal-remove-confirm"));
    await waitFor(() => expect(fallback.current).toHaveFocus());
    expect(await screen.findByTestId("cal-manage-empty")).toHaveTextContent("Henüz takviminize bir şey eklemediniz.");
  });

  it("Bağlantıyı yenile shows the new link once; an older backend gets create + delete", async () => {
    api.rotate404 = true;
    const user = userEvent.setup();
    renderList();
    await user.click(await screen.findByTestId("cal-rotate-3"));
    const paths = () => api.calls.filter((c) => c.method !== "GET").map((c) => `${c.method} ${c.path}`);
    await waitFor(() => expect(paths()).toEqual(["POST /calendar/subscriptions/3/rotate", "POST /calendar/subscriptions", "DELETE /calendar/subscriptions/3"]));
    expect(api.calls.find((c) => c.method === "POST" && c.path === "/calendar/subscriptions")?.body).toEqual({ scope_kind: "department_classes", scope_id: 7, channel: "link" });
  });

  it("Şimdi eşitle queues a sync of the account", async () => {
    const user = userEvent.setup();
    renderList();
    await user.click(await screen.findByTestId("cal-sync-4"));
    await waitFor(() => expect(api.calls.some((c) => c.method === "POST" && c.path === "/calendar/connectors/google/resync")).toBe(true));
  });

  it("an old broad grant offers Daha az izinle yeniden bağlan; the account can be disconnected", async () => {
    const user = userEvent.setup();
    renderList();
    const account = await screen.findByTestId("cal-account-google");
    expect(account).toHaveTextContent("Google Takvim · ayse@uni.edu.tr");
    expect(account).toHaveTextContent("Doğrulanmış kurum hesabı");
    await user.click(within(account).getByTestId("cal-reconnect-google"));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://accounts.example/again"));
    expect(api.calls.find((c) => c.path === "/calendar/connectors/google/connect")?.body).toEqual({ return_path: "/profile", scopes: ["my_classes"] });
    await user.click(within(account).getByTestId("cal-disconnect-google"));
    expect(await screen.findByTestId("cal-disconnect-dialog-google")).toHaveTextContent("SmartSched – Derslerim");
    await user.click(screen.getByTestId("cal-disconnect-confirm-google"));
    await waitFor(() => expect(api.calls.some((c) => c.method === "DELETE" && c.path === "/calendar/connectors/google")).toBe(true));
  });
});
