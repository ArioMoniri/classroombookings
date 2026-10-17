/** M-40 / F-11 S09: calendar sync is off with no sign-off; on needs the KVKK acknowledgement; the record shows. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

// user events on a shared, loaded host (load average above 20 on 4 cores during the CAL lanes)
vi.setConfig({ testTimeout: 20_000 });

const state = vi.hoisted(() => ({ settings: null as unknown, put: vi.fn(), status: null as unknown }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { method?: string; body?: unknown; schema?: { parse: (v: unknown) => unknown } } = {}) => {
    if (path === "/calendar/admin/status" && state.status) return opts.schema ? opts.schema.parse(state.status) : state.status;
    if (path !== "/calendar/admin/settings") throw new Error(`unexpected ${path}`);
    return opts.method === "PUT" ? state.put(opts.body) : state.settings;
  },
}));

import { CalendarSyncAdmin } from "./calendar-sync-admin";

const BASIS = "KVKK Art. 9 as amended by Law 7499 (cross-border transfer)";
const off = { calendar_sync_enabled: false, calendar_sync_signoff: null, webhooks_enabled: false, public_url: "https://plan.uni.edu.tr", feed_past_days: 30, feed_cancelled_grace_days: 7 };

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="en">
        <CalendarSyncAdmin />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("CalendarSyncAdmin", () => {
  beforeEach(() => {
    state.settings = off;
    state.status = null;
    state.put.mockReset();
    state.put.mockImplementation(async (b: { calendar_sync_enabled?: boolean; webhooks_enabled?: boolean }) => {
      const cur = state.settings as typeof off;
      const next = { ...cur, ...b } as Record<string, unknown>;
      if (b.calendar_sync_enabled !== undefined) next.calendar_sync_signoff = { enabled: b.calendar_sync_enabled, by: "Fatih Bey", by_user_id: 1, at: "2026-10-16T09:00:00Z", features: ["calendar_sync"], legal_basis: BASIS };
      state.settings = next;
      return next;
    });
  });

  it("is off with no sign-off on a fresh install", async () => {
    renderCard();
    expect(await screen.findByTestId("calendar-no-signoff")).toHaveTextContent("No sign-off recorded");
    expect(screen.getByTestId("calendar-status-pill")).toHaveTextContent("Off");
    expect(screen.getByTestId("calendar-sync-switch")).not.toHaveAttribute("data-checked");
  });

  it("shows the notice first, needs the acknowledgement, then shows who, when and the legal basis", async () => {
    renderCard();
    await userEvent.click(await screen.findByTestId("calendar-sync-switch"));
    expect(await screen.findByTestId("calendar-notice-text")).toHaveTextContent(/transfer of personal data abroad/);
    const confirm = screen.getByTestId("calendar-confirm");
    expect(confirm).toBeDisabled();
    expect(state.put).not.toHaveBeenCalled();
    await userEvent.click(screen.getByTestId("calendar-ack"));
    await userEvent.click(confirm);
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ calendar_sync_enabled: true }));
    expect(await screen.findByTestId("calendar-signoff")).toHaveTextContent(/Turned on by Fatih Bey on .*2026/);
    expect(screen.getByTestId("calendar-signoff")).toHaveTextContent(BASIS);
    expect(screen.getByTestId("calendar-status-pill")).toHaveTextContent("On");
  });

  it("reads the stored legal basis in Turkish", async () => {
    state.settings = { ...off, calendar_sync_enabled: true, calendar_sync_signoff: { enabled: true, by: "Fatih Bey", at: "2026-10-15T09:00:00Z", features: ["calendar_sync"], legal_basis: BASIS } };
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <I18nProvider initialLocale="tr">
          <CalendarSyncAdmin />
        </I18nProvider>
      </QueryClientProvider>,
    );
    const record = await screen.findByTestId("calendar-signoff");
    expect(record).toHaveTextContent("Hukuki dayanak: KVKK md. 9 (7499 sayılı Kanun ile değişik; yurt dışına aktarım)");
    expect(record).not.toHaveTextContent("as amended");
  });

  it("turns off without the acknowledgement and keeps a record", async () => {
    state.settings = { ...off, calendar_sync_enabled: true, calendar_sync_signoff: { enabled: true, by: "Fatih Bey", at: "2026-10-15T09:00:00Z", features: ["calendar_sync"], legal_basis: BASIS } };
    renderCard();
    await userEvent.click(await screen.findByTestId("calendar-sync-switch"));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ calendar_sync_enabled: false }));
    expect(screen.queryByTestId("calendar-notice-text")).toBeNull();
    expect(await screen.findByText(/Turned off by Fatih Bey/)).toBeInTheDocument();
  });
});

/** CAL-09: the calendar-export block under the sign-off (scopes, who may export a department, fields, horizon, status). */
describe("CalendarSyncAdmin › calendar export (CAL-09)", () => {
  const cal = {
    ...off,
    calendar_sync_enabled: true,
    export_scopes: { my_classes: true, department_classes: true, my_bookings: true },
    department_rule: { own: true, taught: true, permission: true },
    export_fields: { title: true, department: true, co_instructors: false, link: true },
    feed_future_days: 200,
  };
  beforeEach(() => {
    state.settings = cal;
    state.status = { active_links: 12, links_by_scope: { my_classes: 9, department_classes: 3 }, connections: [{ provider: "google", count: 4, by_scope: { my_classes: 4 } }], failed_jobs: 1, last_reconcile_at: null };
    state.put.mockReset();
    state.put.mockImplementation(async (b: Record<string, unknown>) => {
      state.settings = { ...(state.settings as object), ...b };
      return state.settings;
    });
  });

  it("is absent while the backend has no export settings", async () => {
    state.settings = off;
    renderCard();
    await screen.findByTestId("calendar-no-signoff");
    expect(screen.queryByTestId("cal-admin-export")).toBeNull();
  });

  it("shows the defaults: co-instructor names off, the rest on, and the status counts", async () => {
    renderCard();
    expect(await screen.findByTestId("cal-admin-export")).toHaveTextContent("Calendar export");
    expect(screen.getByTestId("cal-admin-field-co_instructors")).not.toHaveAttribute("data-checked");
    expect(screen.getByTestId("cal-admin-field-title")).toHaveAttribute("data-checked");
    expect(screen.getByTestId("cal-admin-scope-my_classes")).toHaveAttribute("data-checked");
    expect(await screen.findByTestId("cal-admin-links")).toHaveTextContent("12");
    expect(screen.getByTestId("cal-admin-connections-google")).toHaveTextContent("4");
    expect(screen.getByTestId("cal-admin-failed")).toHaveTextContent("1");
    expect(screen.getByTestId("cal-admin-reconcile")).toHaveTextContent("Has not run yet");
  });

  it("saves one switch with the whole map of its group", async () => {
    renderCard();
    await userEvent.click(await screen.findByTestId("cal-admin-scope-department_classes"));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ export_scopes: { my_classes: true, department_classes: false, my_bookings: true } }));
    await waitFor(() => expect(screen.getByTestId("cal-admin-rule-own")).toHaveAttribute("data-disabled"));
    await userEvent.click(screen.getByTestId("cal-admin-field-co_instructors"));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ export_fields: { title: true, department: true, co_instructors: true, link: true } }));
  });

  it("checks the horizon bounds before saving", async () => {
    renderCard();
    const future = await screen.findByTestId("cal-admin-feed_future_days");
    await userEvent.clear(future);
    await userEvent.type(future, "365");
    await userEvent.click(screen.getByTestId("cal-admin-horizon-save"));
    expect(screen.getByTestId("cal-admin-horizon-error")).toHaveTextContent("from 1 to 200");
    expect(state.put).not.toHaveBeenCalled();
    await userEvent.clear(future);
    await userEvent.type(future, "120");
    await userEvent.click(screen.getByTestId("cal-admin-horizon-save"));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ feed_past_days: 30, feed_future_days: 120, feed_cancelled_grace_days: 7 }));
  });

  it("reads in Turkish", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <I18nProvider initialLocale="tr">
          <CalendarSyncAdmin />
        </I18nProvider>
      </QueryClientProvider>,
    );
    const block = await screen.findByTestId("cal-admin-export");
    expect(block).toHaveTextContent("Takvim dışa aktarma");
    expect(block).toHaveTextContent("Bölüm derslerini kim dışa aktarabilir?");
    expect(block).toHaveTextContent("Bölüm ders takvimini dışa aktarma");
    expect(block).toHaveTextContent("Diğer öğretim elemanlarının adları");
  });
});
