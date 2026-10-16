/** M-40 / F-11 S09: calendar sync is off with no sign-off; on needs the KVKK acknowledgement; the record shows. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({ settings: null as unknown, put: vi.fn() }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { method?: string; body?: unknown } = {}) => {
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
    state.put.mockReset();
    state.put.mockImplementation(async (b: { calendar_sync_enabled?: boolean; webhooks_enabled?: boolean }) => {
      const cur = state.settings as typeof off;
      const next = { ...cur, ...b } as Record<string, unknown>;
      if (b.calendar_sync_enabled !== undefined) next.calendar_sync_signoff = { enabled: b.calendar_sync_enabled, by: "Fatih Bey", by_user_id: 1, at: "2026-10-16T09:00:00Z", features: ["calendar_sync"], legal_basis: BASIS };
      state.settings = next;
      return next;
    });
  });

  it("is off with no sign-off on a fresh install; webhooks off too", async () => {
    renderCard();
    expect(await screen.findByTestId("calendar-no-signoff")).toHaveTextContent("No sign-off recorded");
    expect(screen.getByTestId("calendar-status-pill")).toHaveTextContent("Off");
    expect(screen.getByTestId("calendar-sync-switch")).not.toHaveAttribute("data-checked");
    expect(screen.getByTestId("webhooks-switch")).not.toHaveAttribute("data-checked");
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

  it("turns off without the acknowledgement and keeps a record", async () => {
    state.settings = { ...off, calendar_sync_enabled: true, calendar_sync_signoff: { enabled: true, by: "Fatih Bey", at: "2026-10-15T09:00:00Z", features: ["calendar_sync"], legal_basis: BASIS } };
    renderCard();
    await userEvent.click(await screen.findByTestId("calendar-sync-switch"));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ calendar_sync_enabled: false }));
    expect(screen.queryByTestId("calendar-notice-text")).toBeNull();
    expect(await screen.findByText(/Turned off by Fatih Bey/)).toBeInTheDocument();
  });
});
