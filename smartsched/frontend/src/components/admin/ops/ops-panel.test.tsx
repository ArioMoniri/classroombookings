/** W3-OPS operations panel: status cards, error groups (status flow, focus), chart, Grafana off / on, log tail. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({
  calls: [] as { path: string; method: string; query?: Record<string, unknown>; body?: unknown }[],
  perms: ["setup.settings"] as string[],
  grafanaUp: false,
  lokiUp: true,
  errors: [] as Record<string, unknown>[],
  statusPending: false,
  backup: undefined as Record<string, unknown> | undefined,
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/lib/permissions", async (orig) => {
  const real = await orig<typeof import("@/lib/permissions")>();
  return { ...real, usePermissions: () => ({ loading: false, perms: state.perms, can: (need: string | string[] | null) => real.hasPermission(state.perms, need), canAll: () => true, userId: 1, departmentId: null }) };
});
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { method?: string; body?: unknown; query?: Record<string, unknown> } = {}) => {
      const method = opts.method ?? "GET";
      state.calls.push({ path, method, query: opts.query, body: opts.body });
      if (path === "/ops/status") return state.statusPending ? new Promise(() => {}) : status();
      if (path === "/ops/requests") return { source: "process", points: [{ t: 60, requests: 10, errors: 1, p95_ms: 120 }, { t: 120, requests: 30, errors: 0, p95_ms: 80 }] };
      if (path === "/ops/errors" && method === "GET") {
        const st = String(opts.query?.status ?? "");
        const items = state.errors.filter((e) => !st || e.status === st);
        return { items, counts: { open: state.errors.filter((e) => e.status === "open").length }, retention_days: 90 };
      }
      const m = /^\/ops\/errors\/(\d+)(\/status)?$/.exec(path);
      if (m && method === "POST") {
        const e = state.errors.find((x) => x.id === Number(m[1]))!;
        e.status = (opts.body as { status: string }).status;
        return e;
      }
      if (m) return { ...state.errors.find((x) => x.id === Number(m[1])), sample_stack: "TypeError: x\n    at RoomCard (page.js:1:2)" };
      if (path === "/ops/dashboards") return dashboards();
      if (path === "/ops/logs") return state.lokiUp ? { service: opts.query?.service, services: [], available: true, lines: [{ ts: 1760000000000, service: "backend", line: `request failed request_id=${String(opts.query?.q ?? "")}` }] } : { service: "backend", services: [], available: false, lines: [], message_tr: "Loki yapılandırılmadı.", message_en: "Loki is not configured." };
      throw new Error(`unexpected ${method} ${path}`);
    },
  };
});

import { OpsPanel } from "./ops-panel";

function probe(up: boolean, configured = true) {
  return { configured, reachable: up, status: configured ? (up ? "ok" : "down") : "off", latency_ms: up ? 4 : undefined };
}
function status() {
  return {
    generated_at: "2026-10-17T20:00:00+03:00",
    release: { version: "0.1.0", sha: "0123456789abcdef", deployed_at: "2026-10-17T17:00:00Z", environment: "prod" },
    api: { status: "ok", uptime_s: 93784, workers: 2 },
    db: { status: "ok", latency_ms: 3.2, migrations: "head", dialect: "postgresql" },
    queues: { status: "warn", queued: 1, running: 2, failed_24h: 1 },
    mail: { status: "ok", pending: 0, failed: 0, unsent: 4, sent: 10, oldest_pending_min: null },
    deliveries: { status: "ok", failed: 0 },
    disk: { status: "ok", total_bytes: 100 * 2 ** 30, used_bytes: 40 * 2 ** 30, free_bytes: 60 * 2 ** 30, used_pct: 40 },
    errors: { status: "warn", open: 1, seen_24h: 2 },
    ...(state.backup ? { backup: state.backup } : {}),
    services: { grafana: probe(state.grafanaUp), prometheus: probe(false, false), loki: probe(state.lokiUp) },
    grafana_path: "/grafana/",
    podci: { ...probe(true), last_run: { state: "success", branch: "main", sha: "abc1234", started: "2026-10-17 18:00:00 UTC" } },
    alerts: [{ name: "SmartSchedHigh5xx", severity: "warning", summary_tr: "İsteklerin %2'sinden fazlası 5xx ile bitiyor (10 dk).", summary_en: "More than 2 % of requests end in 5xx (10 min)." }],
  };
}
function dashboards() {
  const d = (uid: string, tr: string) => ({ uid, title_tr: tr, title_en: uid, url: `/grafana/d/${uid}/x?orgId=1`, panels: [{ id: 1, title_tr: `${tr} panel`, title_en: "panel", embed: `/grafana/d-solo/${uid}/x?orgId=1&panelId=1` }] });
  return { grafana: { ...probe(state.grafanaUp), path: "/grafana/" }, dashboards: [d("smartsched-health", "Servis sağlığı"), d("smartsched-api", "API")] };
}
function group(id: number, status = "open", extra: Record<string, unknown> = {}) {
  return { id, fingerprint: `fp${id}`, source: "frontend", kind: "TypeError", message: "Cannot read properties of undefined", route: "/rooms/:id", method: null, status_code: null, user_role: "TEACHER", release: "0123456789", count: 3, first_seen: "2026-10-17T10:00:00", last_seen: "2026-10-17T11:00:00", status, reopened: 0, last_request_id: null, ...extra };
}

function renderIt(locale: "tr" | "en" = "tr") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>
        <OpsPanel />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("OpsPanel", () => {
  beforeEach(() => {
    state.calls = [];
    state.perms = ["setup.settings"];
    state.grafanaUp = false;
    state.lokiUp = true;
    state.errors = [group(1), group(2, "acknowledged", { source: "backend", kind: "RuntimeError", route: "/api/v1/runs/{run_id}", method: "POST", status_code: 500, last_request_id: "req-42" })];
    toast.success.mockReset();
    state.backup = undefined;
  });

  it("backup card: 'Son yedek' with the time, a warning past 26 h, and no crash on an older backend", async () => {
    state.backup = { status: "ok", last_success_at: "2026-10-17T23:30:00Z", age_h: 3.2, source: "textfile", stale_after_h: 26 };
    const first = renderIt();
    const card = await screen.findByTestId("ops-card-backup");
    expect(card).toHaveAttribute("data-status", "ok");
    expect(card).toHaveTextContent(/Son yedek: \d/);
    expect(card).not.toHaveTextContent("26 saatten eski");
    first.unmount();

    state.backup = { status: "warn", last_success_at: "2026-10-16T02:30:00Z", age_h: 30.5, source: "textfile", stale_after_h: 26 };
    const second = renderIt();
    const stale = await screen.findByTestId("ops-card-backup");
    expect(stale).toHaveAttribute("data-status", "warn");
    expect(stale).toHaveTextContent("Son yedek 26 saatten eski (31 sa önce).");
    second.unmount();

    state.backup = undefined;
    renderIt("en");
    const none = await screen.findByTestId("ops-card-backup");
    expect(none).toHaveAttribute("data-status", "unknown");
    expect(none).toHaveTextContent("No backup recorded yet");
    expect(screen.getByTestId("ops-panel").textContent).not.toMatch(/ops\.|textfile/);
  });

  it("shows every service card in Turkish with its state, the release and the pod CI run", async () => {
    renderIt();
    const api = await screen.findByTestId("ops-card-api");
    expect(api).toHaveAttribute("data-status", "ok");
    expect(api).toHaveTextContent("Açık kalma: 1 g 2 sa");
    expect(api).toHaveTextContent("Sürüm 01234567");
    expect(screen.getByTestId("ops-card-queues")).toHaveTextContent("1 bekliyor · 2 çalışıyor");
    expect(screen.getByTestId("ops-card-disk")).toHaveTextContent("%40 dolu");
    expect(screen.getByTestId("ops-card-grafana")).toHaveAttribute("data-status", "down");
    expect(screen.getByTestId("ops-card-prometheus")).toHaveTextContent("Yapılandırılmadı");
    expect(screen.getByTestId("ops-card-podci")).toHaveTextContent("Son çalışma: başarılı · abc1234");
    expect(screen.getByTestId("ops-alerts")).toHaveTextContent("İsteklerin %2'sinden fazlası");
    // no raw enum keys in the UI
    expect(screen.getByTestId("ops-panel").textContent).not.toMatch(/ops\.|acknowledged|unmanaged/);
  });

  it("refuses people without the ops permission", async () => {
    state.perms = ["setup.rooms"];
    renderIt();
    expect(await screen.findByText(/Kurum ayarları/)).toBeInTheDocument();
    expect(state.calls.some((c) => c.path === "/ops/status")).toBe(false);
  });

  it("error groups: acknowledge / resolve move the group and focus returns to the list heading", async () => {
    renderIt();
    const row = await screen.findByTestId("ops-error-1");
    expect(row).toHaveTextContent("Yeni");
    expect(row).toHaveTextContent("Tarayıcı");
    expect(row).toHaveTextContent("3 kez");
    await userEvent.click(within(row).getByTestId("ops-error-resolved-1"));
    await waitFor(() => expect(state.calls.some((c) => c.path === "/ops/errors/1/status" && (c.body as { status: string }).status === "resolved")).toBe(true));
    expect(toast.success).toHaveBeenCalledWith("Çözüldü olarak işaretlendi.");
    await waitFor(() => expect(screen.queryByTestId("ops-error-1")).toBeNull());
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Hata grupları" }));
    expect(document.activeElement).not.toBe(document.body);
    expect(screen.getByTestId("ops-errors-empty")).toHaveTextContent("Yeni hata yok.");
  });

  it("details show the scrubbed stack; 'find in logs' fills the log tail with the request id", async () => {
    renderIt();
    await userEvent.click(await screen.findByTestId("ops-errors-filter-acknowledged"));
    const row = await screen.findByTestId("ops-error-2");
    await userEvent.click(within(row).getByTestId("ops-error-toggle-2"));
    expect(await within(row).findByTestId("ops-error-stack-2")).toHaveTextContent("RoomCard");
    await userEvent.click(within(row).getByTestId("ops-error-logs-2"));
    expect(await screen.findByTestId("ops-logs-lines")).toHaveTextContent("request_id=req-42");
    expect(screen.getByTestId("ops-logs-q")).toHaveValue("req-42");
    expect(state.calls.find((c) => c.path === "/ops/logs")?.query).toMatchObject({ service: "backend", q: "req-42" });
  });

  it("CH12-F04 (FIX-G): a database-locked error reads as one Turkish line; the raw class and SQL wait behind Ayrıntı", async () => {
    state.errors = [group(3, "open", { source: "backend", kind: "OperationalError", message: "(sqlite3.OperationalError) database is locked [SQL: UPDATE password_reset_tokens SET used_at=?]" })];
    renderIt();
    const row = await screen.findByTestId("ops-error-3");
    expect(within(row).getByTestId("ops-error-kind-3")).toHaveTextContent("Veritabanı meşgul: işlem tamamlanamadı, yeniden denenmeli.");
    expect(row).not.toHaveTextContent("sqlite3");
    await userEvent.click(within(row).getByTestId("ops-error-toggle-3"));
    expect(await within(row).findByTestId("ops-error-stack-3")).toHaveTextContent("OperationalError: (sqlite3.OperationalError) database is locked");
  });

  it("E2EA-F09 (FIX-K): an unknown error class shows one Turkish line; its raw message waits behind Ayrıntı", async () => {
    state.errors = [group(4, "open", { source: "backend", kind: "KeyError", message: "no_autoflush last_login_at" })];
    renderIt();
    const row = await screen.findByTestId("ops-error-4");
    expect(row).toHaveTextContent("Beklenmeyen bir hata. Teknik metin Ayrıntı içinde.");
    expect(row).not.toHaveTextContent("no_autoflush");
    await userEvent.click(within(row).getByTestId("ops-error-toggle-4"));
    expect(await within(row).findByTestId("ops-error-stack-4")).toHaveTextContent("KeyError: no_autoflush last_login_at");
  });

  it("log tail without Loki says why, in the reader's language", async () => {
    state.lokiUp = false;
    renderIt("en");
    await userEvent.click(await screen.findByTestId("ops-logs-fetch"));
    expect(await screen.findByTestId("ops-logs-off")).toHaveTextContent("Loki is not configured.");
  });

  it("Grafana off: links disabled and a hint; on: links + same-origin embedded panels", async () => {
    const { unmount } = renderIt();
    expect(await screen.findByTestId("ops-grafana-off")).toHaveTextContent("./deploy.sh --observability");
    expect(screen.getByTestId("ops-dash-smartsched-health")).toHaveAttribute("aria-disabled", "true");
    expect(document.querySelector("iframe")).toBeNull();
    unmount();
    state.grafanaUp = true;
    renderIt();
    const link = await screen.findByTestId("ops-dash-smartsched-health");
    await waitFor(() => expect(link).not.toHaveAttribute("aria-disabled"));
    expect(link).toHaveAttribute("href", "/grafana/d/smartsched-health/x?orgId=1");
    await waitFor(() => expect(document.querySelectorAll("iframe").length).toBe(2));
    expect(document.querySelector("iframe")?.getAttribute("src")).toMatch(/^\/grafana\/d-solo\/smartsched-health/);
    expect(document.querySelector("iframe")?.getAttribute("title")).toBe("Servis sağlığı panel");
  });

  it("the mini chart sums the window and names its source", async () => {
    renderIt();
    await waitFor(() => expect(screen.getByTestId("ops-chart-summary")).toHaveTextContent("40 istek · 1 hata (%2,5) · en yüksek p95 120 ms"));
    expect(screen.getByTestId("ops-chart")).toHaveTextContent("Kaynak: bu API işlemi");
    // CH-06: the shared ChartCard (title, one summary, the table twin with the three measures)
    const fig = screen.getByRole("figure", { name: "İstekler ve gecikme" });
    expect(fig).toHaveAccessibleDescription(/Dakikada ort\. 20 istek; en çok 5xx \d\d:\d\d \(1\)\./);
    expect(within(within(fig).getByRole("table")).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Saat", "İstek", "5xx", "p95 (ms)"]);
    await userEvent.click(screen.getByTestId("ops-range-180"));
    await waitFor(() => expect(state.calls.some((c) => c.path === "/ops/requests" && c.query?.minutes === 180)).toBe(true));
  });
});

describe("mobile-b phase 2 · CLS: the status cards keep their place while /ops/status loads", () => {
  it("renders one placeholder per card in the cards' grid, not a one-line spinner that ~1,000 px of cards replace", async () => {
    state.statusPending = true;
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <I18nProvider initialLocale="tr">
          <OpsPanel />
        </I18nProvider>
      </QueryClientProvider>,
    );
    const grid = await screen.findByTestId("ops-cards-loading");
    expect(grid.className).toContain("grid-cols-1");
    expect(grid.querySelectorAll("li")).toHaveLength(11); // 10 cards + the backup card (sweep 2026-10-18)
    state.statusPending = false;
  });
});
