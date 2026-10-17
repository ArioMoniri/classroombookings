/** A4 Profil › Gizlilik: no notice = a plain sentence; SMS / photo / calendar withdrawals say what goes and ask first, the
 * toast shows the server's `effects[]`; AI withdraws at once; requests. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { HttpError } from "@/lib/api/client";

const state = vi.hoisted(() => ({ privacy: null as unknown, calls: [] as { path: string; method: string; body?: unknown }[] }));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
const effect = (code: string, count: number | null, en: string, tr: string) => ({ code, count, message_en: en, message_tr: tr });
const WITHDRAWN: Record<string, unknown> = {
  sms: { removed_channels: 2, removed_photo: 0, revoked_feeds: 0, disconnected_calendars: 0, ai_excluded: false, effects: [effect("phones_deleted", 2, "2 linked phone number(s) deleted", "bağlı 2 telefon numarası silindi")], consents: [] },
  photo: { removed_channels: 0, removed_photo: 1, revoked_feeds: 0, disconnected_calendars: 0, ai_excluded: false, effects: [effect("photo_deleted", 1, "your profile photo was deleted", "profil fotoğrafınız silindi")], consents: [] },
  calendar_sync: {
    removed_channels: 0,
    removed_photo: 0,
    revoked_feeds: 2,
    disconnected_calendars: 1,
    ai_excluded: false,
    effects: [effect("feeds_revoked", 2, "2 calendar subscription link(s) revoked; calendars using them stop updating", "2 takvim abonelik bağlantısı iptal edildi; bunları kullanan takvimler artık güncellenmez"), effect("calendars_disconnected", 1, "1 Google / Microsoft calendar connection(s) removed", "1 Google / Microsoft takvim bağlantısı kaldırıldı")],
    consents: [],
  },
  ai_personal: { removed_channels: 0, removed_photo: 0, revoked_feeds: 0, disconnected_calendars: 0, ai_excluded: true, effects: [effect("ai_excluded", null, "from now on your name and e-mail are replaced by a placeholder", "bundan sonra adınız ve e-postanız yer tutucuyla değiştirilir")], consents: [] },
};
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { method?: string; body?: unknown } = {}) => {
      const method = opts.method ?? "GET";
      state.calls.push({ path, method, body: opts.body });
      if (path === "/me/privacy") return state.privacy;
      const purpose = /^\/me\/consents\/(\w+)$/.exec(path)?.[1];
      if (purpose && method === "DELETE") return WITHDRAWN[purpose];
      if (path === "/me/data-requests" && (opts.body as { kind: string }).kind === "erase") throw new real.HttpError(409, "dup", { detail: { code: "duplicate", message: "you have an open request of this kind", message_tr: "bu türde açık bir talebiniz var", id: 4 } });
      if (path === "/me/data-requests") return { id: 9, kind: "export", status: "DONE", downloadable: true, created_at: "2026-10-16T06:00:00", download_expires_at: "2026-10-23T06:00:00" };
      throw new Error(`unexpected ${method} ${path}`);
    },
  };
});

import { PrivacySection } from "./privacy-section";

const consents = ["sms", "photo", "calendar_sync", "ai_personal"].map((p) => ({ purpose: p, label_tr: p, label_en: `Purpose ${p}`, granted: true, granted_at: "2026-10-01T09:00:00", withdrawn_at: null }));

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
    toast.success.mockReset();
    toast.error.mockReset();
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
    // the toast says what the server did, in its own words (capitalised, full stop)
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Consent withdrawn", expect.objectContaining({ description: "2 linked phone number(s) deleted." })));
  });

  it("photo and calendar sync: the immediate effect is written, withdrawing asks first, the toast lists every effect (Turkish)", async () => {
    renderIt("tr");
    const photo = await screen.findByTestId("consent-photo");
    expect(photo).toHaveTextContent("kayıtlı profil fotoğrafınız hemen silinir");
    await userEvent.click(within(photo).getByRole("switch"));
    expect(await screen.findByText("Fotoğraf rızası geri alınsın mı?")).toBeInTheDocument();
    expect(state.calls.some((c) => c.method === "DELETE")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Geri al ve fotoğrafı sil" }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Rıza geri alındı", expect.objectContaining({ description: "Profil fotoğrafınız silindi." })));

    const cal = screen.getByTestId("consent-calendar_sync");
    expect(cal).toHaveTextContent("takvim abonelik bağlantılarınız hemen iptal edilir");
    await userEvent.click(within(cal).getByRole("switch"));
    await userEvent.click(await screen.findByRole("button", { name: "Geri al ve bağlantıları kaldır" }));
    await waitFor(() =>
      expect(toast.success).toHaveBeenLastCalledWith(
        "Rıza geri alındı",
        expect.objectContaining({ description: "2 takvim abonelik bağlantısı iptal edildi; bunları kullanan takvimler artık güncellenmez. 1 Google / Microsoft takvim bağlantısı kaldırıldı." }),
      ),
    );
  });

  it("AI: withdrawing applies at once (nothing is deleted) and says names are replaced from now on", async () => {
    renderIt();
    const row = await screen.findByTestId("consent-ai_personal");
    expect(row).toHaveTextContent("replaces your name and e-mail with a placeholder");
    await userEvent.click(within(row).getByRole("switch"));
    await waitFor(() => expect(state.calls.some((c) => c.path === "/me/consents/ai_personal" && c.method === "DELETE")).toBe(true));
    expect(screen.queryByRole("alertdialog")).toBeNull();
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Consent withdrawn", expect.objectContaining({ description: "From now on your name and e-mail are replaced by a placeholder." })));
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
