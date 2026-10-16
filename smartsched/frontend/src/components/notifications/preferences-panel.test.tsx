/** F-01 S11: Profile › Bildirimler — the event × channel matrix of /me/notification-preferences. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import type { NotificationPrefs } from "@/lib/api/approval-first";

const state = vi.hoisted(() => ({ prefs: null as unknown, put: vi.fn() }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { method?: string; body?: unknown } = {}) => {
    if (path !== "/me/notification-preferences") throw new Error(`unexpected ${path}`);
    return opts.method === "PUT" ? state.put(opts.body) : state.prefs;
  },
}));

import { NotificationPreferencesPanel } from "./preferences-panel";

const base = (): NotificationPrefs => ({
  channels: [
    { name: "in_app", label_tr: "Uygulama içi", label_en: "In the app", enabled: true, available: true, default_enabled: true },
    { name: "email", label_tr: "E-posta", label_en: "E-mail", enabled: true, available: true, default_enabled: true },
    { name: "telegram", label_tr: "Telegram", label_en: "Telegram", enabled: false, available: false, default_enabled: false },
  ],
  events: [
    { event: "approval.approved", label_tr: "Talebim onaylandı", label_en: "My request was approved", channels: { in_app: true, email: true, telegram: false } },
    { event: "approval.rejected", label_tr: "Talebim reddedildi (gerekçesiyle)", label_en: "My request was declined (with the reason)", channels: { in_app: true, email: true, telegram: false } },
  ],
});

function renderPanel() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="tr">
        <NotificationPreferencesPanel />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("NotificationPreferencesPanel", () => {
  beforeEach(() => {
    state.prefs = base();
    state.put.mockReset();
    state.put.mockImplementation(async (b: { events?: Record<string, Record<string, boolean>>; channels?: Record<string, boolean> }) => {
      const p = state.prefs as NotificationPrefs;
      for (const [ev, chans] of Object.entries(b.events ?? {})) Object.assign(p.events.find((e) => e.event === ev)!.channels, chans);
      for (const [c, on] of Object.entries(b.channels ?? {})) p.channels.find((x) => x.name === c)!.enabled = on;
      return structuredClone(p);
    });
  });

  it("lists the backend's events and channels in Turkish", async () => {
    renderPanel();
    expect(await screen.findByText("Talebim onaylandı")).toBeInTheDocument();
    expect(screen.getByText("Talebim reddedildi (gerekçesiyle)")).toBeInTheDocument();
    expect(screen.getByTestId("pref-channel-in_app")).toHaveAttribute("data-checked");
    expect(screen.getByTestId("pref-approval.approved-email")).toHaveAttribute("data-checked");
  });

  it("switches e-mail off for one event with a partial PUT", async () => {
    renderPanel();
    await userEvent.click(await screen.findByTestId("pref-approval.approved-email"));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ events: { "approval.approved": { email: false } } }));
    await waitFor(() => expect(screen.getByTestId("pref-approval.approved-email")).not.toHaveAttribute("data-checked"));
    expect(screen.getByTestId("pref-approval.rejected-email")).toHaveAttribute("data-checked");
  });

  it("sums up the channels that cannot reach the user in one line, never one switch per event", async () => {
    state.prefs = { ...base(), channels: base().channels.map((c) => (c.name === "email" ? { ...c, available: false } : c)) };
    renderPanel();
    const line = await screen.findByTestId("prefs-unreachable");
    expect(line).toHaveTextContent("E-posta: hesabınızda e-posta adresi yok.");
    expect(line).toHaveTextContent("Telegram: bağlı değil — Profil › Bağlı kanallar");
    expect(screen.getByTestId("prefs-link-channels")).toHaveAttribute("href", "/profile#channels");
    expect(screen.queryByTestId("pref-channel-email")).toBeNull();
    expect(screen.queryByTestId("pref-channel-telegram")).toBeNull();
    expect(screen.queryByTestId("pref-approval.approved-email")).toBeNull();
    expect(screen.queryByTestId("pref-approval.approved-telegram")).toBeNull();
    expect(screen.getByTestId("pref-approval.approved-in_app")).toBeInTheDocument();
  });

  it("groups events in sections with an all on / off switch per group", async () => {
    state.prefs = {
      ...base(),
      events: [...base().events, { event: "booking.cancelled", label_tr: "Rezervasyonum iptal edildi", label_en: "My booking was cancelled", channels: { in_app: true, email: true, telegram: false } }],
    };
    renderPanel();
    const approvals = await screen.findByTestId("prefs-group-approvals");
    expect(approvals).toHaveTextContent("Onaylar");
    expect(approvals).toHaveTextContent("2 olay");
    expect(screen.getByTestId("prefs-group-bookings")).toHaveTextContent("Rezervasyonlar");
    expect(screen.getByTestId("pref-group-approvals")).toHaveAttribute("data-checked");
    await userEvent.click(screen.getByTestId("pref-group-approvals"));
    await waitFor(() =>
      expect(state.put).toHaveBeenCalledWith({ events: { "approval.approved": { in_app: false, email: false }, "approval.rejected": { in_app: false, email: false } } }),
    );
    await waitFor(() => expect(screen.getByTestId("pref-approval.rejected-email")).not.toHaveAttribute("data-checked"));
    expect(screen.getByTestId("pref-booking.cancelled-email")).toHaveAttribute("data-checked");
  });

  it("a channel's master switch turns it off for every event", async () => {
    renderPanel();
    await userEvent.click(await screen.findByTestId("pref-channel-email"));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ channels: { email: false } }));
    await waitFor(() => expect(screen.getByTestId("pref-approval.rejected-email")).toHaveAttribute("data-disabled"));
  });
});
