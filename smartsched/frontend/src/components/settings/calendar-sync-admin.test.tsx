/** M-40 / F-11 S09: calendar sync is off with no sign-off; on needs the KVKK acknowledgement; the record shows. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

// user events on a shared, loaded host (load average above 20 on 4 cores during the CAL lanes)
vi.setConfig({ testTimeout: 20_000 });

const state = vi.hoisted(() => ({ settings: null as unknown, put: vi.fn(), exp: null as unknown, expPut: vi.fn() }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { method?: string; body?: unknown; schema?: { parse: (v: unknown) => unknown } } = {}) => {
    if (path === "/calendar/admin/export-settings") {
      if (!state.exp) throw new Error("404 on an older backend");
      const v = opts.method === "PUT" ? await state.expPut(opts.body) : state.exp;
      return opts.schema ? opts.schema.parse(v) : v;
    }
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
    state.exp = null;
    state.put.mockReset();
    state.put.mockImplementation(async (b: { calendar_sync_enabled?: boolean; webhooks_enabled?: boolean }) => {
      const cur = state.settings as typeof off;
      const next = { ...cur, ...b } as Record<string, unknown>;
      if (b.calendar_sync_enabled !== undefined) next.calendar_sync_signoff = { enabled: b.calendar_sync_enabled, by: "Fatih Bey", by_user_id: 1, at: "2026-10-16T09:00:00Z", features: ["calendar_sync"], legal_basis: BASIS };
      state.settings = next;
      return next;
    });
  });

  it("CAL10-F02: without the panel address the card warns that links cannot work and points to the address field", async () => {
    state.settings = { ...off, public_url: null };
    renderCard();
    const warn = await screen.findByTestId("calendar-sync-no-url");
    expect(warn).toHaveTextContent("Panel address missing");
    expect(warn).toHaveTextContent("only download the .ics file");
    expect(screen.getByRole("link", { name: "Enter the panel address" })).toHaveAttribute("href", "#cp-public-url");
  });

  it("CAL10-F02: no warning once the address is set", async () => {
    renderCard();
    await screen.findByTestId("calendar-no-signoff");
    expect(screen.queryByTestId("calendar-sync-no-url")).toBeNull();
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

/** CAL-09 (contract: CAL-B API.md `GET/PUT /calendar/admin/export-settings`): scopes and fields up front; the
 * department rule, the time range and the status counts under a closed "Advanced". */
describe("CalendarSyncAdmin › calendar export (CAL-09)", () => {
  const exp = {
    export_my_classes: true,
    export_department_classes: true,
    export_my_bookings: true,
    export_field_course_title: true,
    export_field_department: true,
    export_field_co_instructors: false,
    export_field_link: true,
    push_verified_only: true,
    push_allowed_domains: ["uni.edu.tr"],
    calendar_client_source: "own",
    fields_always: ["course_code", "section", "room", "time"],
    identity_clients: { google: false, microsoft: true },
    status: { links: { my_classes: 9, department_classes: 3, legacy: 40 }, connections: { google: 4, microsoft: 1 }, connections_by_scope: { my_classes: 4 }, needs_attention: 1, least_privilege_flagged: 2, failed_jobs: 1, nightly_reconcile: null },
  };
  beforeEach(() => {
    state.settings = { ...off, calendar_sync_enabled: true };
    state.exp = exp;
    state.put.mockReset();
    state.put.mockImplementation(async (b: Record<string, unknown>) => {
      state.settings = { ...(state.settings as object), ...b };
      return state.settings;
    });
    state.expPut.mockReset();
    state.expPut.mockImplementation(async (b: Record<string, unknown>) => {
      state.exp = { ...(state.exp as object), ...b };
      return state.exp;
    });
  });

  it("is absent while the backend has no export settings", async () => {
    state.exp = null;
    renderCard();
    await screen.findByTestId("calendar-sync-switch");
    await waitFor(() => expect(screen.queryByTestId("cal-admin-export")).toBeNull());
  });

  it("shows the defaults: co-instructor names off, the rest on; the rest under a closed Advanced", async () => {
    renderCard();
    expect(await screen.findByTestId("cal-admin-export")).toHaveTextContent("Calendar export");
    expect(screen.getByTestId("cal-admin-field-co_instructors")).not.toHaveAttribute("data-checked");
    expect(screen.getByTestId("cal-admin-field-title")).toHaveAttribute("data-checked");
    expect(screen.getByTestId("cal-admin-scope-my_classes")).toHaveAttribute("data-checked");
    const adv = screen.getByTestId("cal-admin-advanced");
    expect(adv).not.toHaveAttribute("open");
    for (const id of ["cal-admin-who", "cal-admin-horizon", "cal-admin-status"]) expect(adv).toContainElement(await screen.findByTestId(id));
    expect(screen.getByTestId("cal-admin-links")).toHaveTextContent("52");
    expect(screen.getByTestId("cal-admin-connections-google")).toHaveTextContent("4");
    expect(screen.getByTestId("cal-admin-attention")).toHaveTextContent("1");
    expect(screen.getByTestId("cal-admin-failed")).toHaveTextContent("1");
    expect(screen.getByTestId("cal-admin-reconcile")).toHaveTextContent("Has not run yet");
  });

  it("saves one switch with just its own flat key", async () => {
    renderCard();
    await userEvent.click(await screen.findByTestId("cal-admin-scope-department_classes"));
    await waitFor(() => expect(state.expPut).toHaveBeenCalledWith({ export_department_classes: false }));
    await userEvent.click(screen.getByTestId("cal-admin-field-co_instructors"));
    await waitFor(() => expect(state.expPut).toHaveBeenCalledWith({ export_field_co_instructors: true }));
  });

  it("checks the time range before saving it to the KVKK card's endpoint", async () => {
    renderCard();
    const past = await screen.findByTestId("cal-admin-feed_past_days");
    await userEvent.clear(past);
    await userEvent.type(past, "999");
    await userEvent.click(screen.getByTestId("cal-admin-horizon-save"));
    expect(screen.getByTestId("cal-admin-horizon-error")).toHaveTextContent("from 0 to 730");
    expect(state.put).not.toHaveBeenCalled();
    await userEvent.clear(past);
    await userEvent.type(past, "60");
    await userEvent.click(screen.getByTestId("cal-admin-horizon-save"));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ feed_past_days: 60, feed_cancelled_grace_days: 7 }));
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
    expect(block).toHaveTextContent("Gelişmiş");
    expect(block).toHaveTextContent("Bölüm derslerini kimler dışa aktarabilir?");
    expect(block).toHaveTextContent("Bölüm ders takvimini dışa aktarma");
    expect(block).toHaveTextContent("Diğer öğretim elemanlarının adları");
  });
});
