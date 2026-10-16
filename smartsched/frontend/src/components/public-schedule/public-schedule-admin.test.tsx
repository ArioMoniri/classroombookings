/** V2: the public day view is off with no sign-off; on needs the acknowledgement; the record shows who and when. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({ settings: null as unknown, put: vi.fn() }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { method?: string; body?: unknown } = {}) => {
    if (path !== "/public-schedule/admin/settings") throw new Error(`unexpected ${path}`);
    return opts.method === "PUT" ? state.put(opts.body) : state.settings;
  },
}));

import { PublicScheduleAdmin } from "./public-schedule-admin";
import { PUBLIC_LEGAL_BASIS } from "@/lib/api/public-schedule";

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="tr">
        <PublicScheduleAdmin />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("PublicScheduleAdmin", () => {
  beforeEach(() => {
    state.settings = { enabled: false, signoff: null, show_bookings: "busy" };
    state.put.mockReset();
    state.put.mockImplementation(async (b: { enabled?: boolean }) => {
      const next = { ...(state.settings as object), ...b } as Record<string, unknown>;
      if (b.enabled !== undefined) next.signoff = { enabled: b.enabled, by: "Fatih Bey", by_user_id: 1, at: "2026-10-16T09:00:00Z", features: ["public_schedule"], legal_basis: PUBLIC_LEGAL_BASIS };
      state.settings = next;
      return next;
    });
  });

  it("is off and never signed on a fresh install", async () => {
    renderCard();
    expect(await screen.findByTestId("public-no-signoff")).toHaveTextContent("Hiç açılmadı");
    expect(screen.getByTestId("public-status-pill")).toHaveTextContent("Kapalı");
  });

  it("switching on shows what is published, needs the acknowledgement, then records the sign-off in Turkish", async () => {
    renderCard();
    await userEvent.click(await screen.findByTestId("public-schedule-switch"));
    const text = await screen.findByTestId("public-notice-text");
    expect(text).toHaveTextContent("Asla gösterilmeyenler");
    expect(screen.getByTestId("public-confirm")).toBeDisabled();
    await userEvent.click(screen.getByTestId("public-ack"));
    await userEvent.click(screen.getByTestId("public-confirm"));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ enabled: true }));
    const record = await screen.findByTestId("public-signoff");
    expect(record).toHaveTextContent("Fatih Bey");
    expect(record).toHaveTextContent("veri en aza indirme");
  });

  it("switching off needs no acknowledgement", async () => {
    state.settings = { enabled: true, signoff: { enabled: true, by: "Fatih Bey", at: "2026-10-16T09:00:00Z", features: [], legal_basis: PUBLIC_LEGAL_BASIS }, show_bookings: "busy" };
    renderCard();
    await userEvent.click(await screen.findByTestId("public-schedule-switch"));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ enabled: false }));
  });
});
