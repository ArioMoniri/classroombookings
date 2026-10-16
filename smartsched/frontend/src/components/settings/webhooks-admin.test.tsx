/** Settings › Entegrasyonlar › Giden webhook'lar: create (secret shown once), the backend's SSRF refusal next to the field. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { HttpError } from "@/lib/api/client";

const state = vi.hoisted(() => ({ list: [] as unknown[], create: vi.fn(), settings: { calendar_sync_enabled: false, calendar_sync_signoff: null, webhooks_enabled: false } as Record<string, unknown>, put: vi.fn() }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { method?: string; body?: unknown } = {}) => {
    if (path === "/webhooks" && opts.method === "POST") return state.create(opts.body);
    if (path === "/webhooks") return state.list;
    if (path === "/webhooks/event-types") return ["booking.created", "approval.rejected", "ping"];
    if (path === "/calendar/admin/settings") return opts.method === "PUT" ? state.put(opts.body) : state.settings;
    throw new Error(`unexpected ${path}`);
  },
}));

import { WebhooksAdmin } from "./webhooks-admin";

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="tr">
        <WebhooksAdmin />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("WebhooksAdmin", () => {
  beforeEach(() => {
    state.list = [];
    state.create.mockReset();
    state.settings = { calendar_sync_enabled: false, calendar_sync_signoff: null, webhooks_enabled: false };
    state.put.mockReset();
    state.put.mockImplementation(async (b: Record<string, unknown>) => (state.settings = { ...state.settings, ...b }));
  });

  it("heads the card with the delivery switch, off by default; turning it on saves webhooks_enabled", async () => {
    renderCard();
    const sw = await screen.findByTestId("webhooks-switch");
    await waitFor(() => expect(sw).not.toHaveAttribute("data-disabled"));
    expect(sw).not.toHaveAttribute("data-checked");
    expect(screen.getByText("Webhook gönderimi")).toBeInTheDocument();
    await userEvent.click(sw);
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ webhooks_enabled: true }));
    await waitFor(() => expect(screen.getByTestId("webhooks-switch")).toHaveAttribute("data-checked"));
  });

  it("starts empty; a new webhook shows its secret once", async () => {
    state.create.mockImplementation(async (b: { url: string; events: string[] }) => {
      const w = { id: 1, url: b.url, events: b.events, active: true, consecutive_failures: 0, secret_hint: "…ab12", description: null };
      state.list = [w];
      return { ...w, secret: "shown-once-value" };
    });
    renderCard();
    expect(await screen.findByTestId("webhooks-empty")).toHaveTextContent("Henüz webhook yok.");
    await userEvent.click(screen.getByTestId("webhook-new"));
    await userEvent.type(await screen.findByTestId("webhook-url"), "https://hooks.uni.edu.tr/smartsched");
    await userEvent.click(screen.getByTestId("webhook-save"));
    await waitFor(() => expect(state.create).toHaveBeenCalledWith({ url: "https://hooks.uni.edu.tr/smartsched", events: ["*"], description: null, active: true }));
    expect(await screen.findByTestId("webhook-secret")).toHaveTextContent("shown-once-value");
    expect(await screen.findByTestId("webhook-1")).toHaveTextContent("Etkin");
  });

  it("shows the backend's refusal of a private address next to the field", async () => {
    state.create.mockRejectedValue(new HttpError(422, "the address resolves to a private or loopback network"));
    renderCard();
    await userEvent.click(await screen.findByTestId("webhook-new"));
    await userEvent.type(await screen.findByTestId("webhook-url"), "http://127.0.0.1/x");
    await userEvent.click(screen.getByTestId("webhook-save"));
    expect(await screen.findByTestId("webhook-error")).toHaveTextContent(/private or loopback/);
  });
});
