/** A4 Profil › Gizlilik: no notice = a plain sentence; SMS withdrawal says the numbers go and asks first; requests. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { HttpError } from "@/lib/api/client";

const state = vi.hoisted(() => ({ privacy: null as unknown, calls: [] as { path: string; method: string; body?: unknown }[] }));
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { method?: string; body?: unknown } = {}) => {
      const method = opts.method ?? "GET";
      state.calls.push({ path, method, body: opts.body });
      if (path === "/me/privacy") return state.privacy;
      if (path === "/me/consents/sms" && method === "DELETE") return { removed_channels: 2, consents: [] };
      if (path === "/me/data-requests" && (opts.body as { kind: string }).kind === "erase") throw new real.HttpError(409, "dup", { detail: { code: "duplicate", message: "you have an open request of this kind", message_tr: "bu türde açık bir talebiniz var", id: 4 } });
      if (path === "/me/data-requests") return { id: 9, kind: "export", status: "DONE", downloadable: true, created_at: "2026-10-16T06:00:00", download_expires_at: "2026-10-23T06:00:00" };
      throw new Error(`unexpected ${method} ${path}`);
    },
  };
});

import { PrivacySection } from "./privacy-section";

const consents = ["sms", "photo", "calendar_sync", "ai_personal"].map((p) => ({ purpose: p, label_tr: p, label_en: `Purpose ${p}`, granted: p === "sms", granted_at: p === "sms" ? "2026-10-01T09:00:00" : null, withdrawn_at: null }));

function renderIt(locale: "en" | "tr" = "en") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>
        <PrivacySection />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("PrivacySection", () => {
  beforeEach(() => {
    state.calls = [];
    state.privacy = { notice: null, needs_ack: false, consents, requests: [], due_days: 30 };
  });

  it("says plainly that no notice is published (no placeholder text)", async () => {
    renderIt("tr");
    expect(await screen.findByTestId("privacy-no-notice")).toHaveTextContent("Kurumunuz henüz bir aydınlatma metni yayımlamadı");
  });

  it("shows a published notice with 'I have read it' until acknowledged", async () => {
    state.privacy = { ...(state.privacy as object), notice: { id: 3, version: 2, language: "en", title: "Privacy notice v2", body_md: "# Who we are\n\n- the university", published_at: "2026-10-15T09:00:00" }, needs_ack: true };
    renderIt();
    const card = await screen.findByTestId("privacy-notice");
    expect(card).toHaveTextContent("Privacy notice v2");
    expect(within(card).getByRole("heading", { name: "Who we are" })).toBeInTheDocument();
    expect(screen.getByTestId("privacy-ack")).toBeInTheDocument();
  });

  it("SMS: the consequence is written next to the switch and withdrawing asks first", async () => {
    renderIt();
    const row = await screen.findByTestId("consent-sms");
    expect(row).toHaveTextContent("deletes your linked phone numbers");
    await userEvent.click(within(row).getByRole("switch"));
    expect(await screen.findByText("Withdraw the SMS / WhatsApp consent?")).toBeInTheDocument();
    expect(state.calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Withdraw and delete numbers" }));
    await waitFor(() => expect(state.calls.some((c) => c.path === "/me/consents/sms" && c.method === "DELETE")).toBe(true));
  });

  it("an export is self-service; a duplicate erasure says so", async () => {
    renderIt();
    await userEvent.click(await screen.findByTestId("privacy-request-send"));
    await waitFor(() => expect(state.calls.some((c) => c.path === "/me/data-requests" && (c.body as { kind: string }).kind === "export")).toBe(true));
    await userEvent.selectOptions(screen.getByTestId("privacy-request-kind"), "erase");
    await userEvent.click(screen.getByTestId("privacy-request-send"));
    await userEvent.click(await screen.findByRole("button", { name: "Request erasure" }));
    expect(await screen.findByTestId("privacy-request-error")).toHaveTextContent("You already have an open request of this kind.");
  });

  it("lists my requests with the due date and the download while valid", async () => {
    state.privacy = {
      ...(state.privacy as object),
      requests: [
        { id: 9, kind: "export", status: "DONE", downloadable: true, created_at: "2026-10-16T06:00:00", download_expires_at: "2026-10-23T06:00:00" },
        { id: 4, kind: "erase", status: "OPEN", overdue: false, days_left: 12, created_at: "2026-10-04T06:00:00", due_at: "2026-11-03T06:00:00" },
      ],
    };
    renderIt();
    expect(await screen.findByTestId("privacy-download-9")).toBeInTheDocument();
    expect(screen.getByTestId("privacy-request-4")).toHaveTextContent("12 days left");
  });
});

void HttpError;
