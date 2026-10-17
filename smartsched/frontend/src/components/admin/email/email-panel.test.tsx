/** W3-MAIL UI: the panel's tabs, the SMTP wizard (preset fills, secrets write-only, KVKK acknowledgement, the test
 *  with its transcript), the template preview (sandboxed iframe, desktop / phone width) and focus after each step. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({ calls: [] as { path: string; method: string; body: unknown }[], settings: {} as Record<string, unknown> }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock("@/components/bookings/use-booking-format", () => ({ useBookingFormat: () => ({ dateTime: (x: string) => `T(${x})` }) }));

const PRESETS = [
  {
    id: "microsoft365_oauth2",
    label: "Microsoft 365 / Exchange Online (OAuth2)",
    host: "smtp.office365.com",
    port: 587,
    security: "starttls",
    auth_mode: "xoauth2",
    username_hint_tr: "Gönderen posta kutusu",
    username_hint_en: "Mailbox",
    password_label_tr: "Parola",
    password_label_en: "Password",
    oauth_provider: "microsoft",
    console_url: "https://entra.microsoft.com/",
    hosts: ["smtp.office365.com"],
    steps: [{ tr: "Uygulama izni: SMTP.SendAsApp", en: "Application permission: SMTP.SendAsApp", copy: "SMTP.SendAsApp" }],
    notes_tr: "Exchange Online, parola ile SMTP girişini Aralık 2026'dan itibaren kapatıyor (MC786329).",
    notes_en: "",
    extra: {},
    abroad: false,
  },
  { id: "amazon_ses", label: "Amazon SES", host: "email-smtp.eu-central-1.amazonaws.com", port: 587, security: "starttls", auth_mode: "password", username_hint_tr: "", username_hint_en: "", password_label_tr: "SES SMTP parolası", password_label_en: "", oauth_provider: "", console_url: "", hosts: ["email-smtp.eu-central-1.amazonaws.com", "email-smtp.eu-west-1.amazonaws.com"], steps: [{ tr: "Alan adını doğrulayın", en: "Verify", copy: null }], notes_tr: "", notes_en: "", extra: {}, abroad: true },
];
const BASE = {
  provider: "",
  host: "",
  port: 587,
  security: "starttls",
  auth_mode: "password",
  username: "",
  password: { set: true, masked: "smtp********izli" },
  oauth_client_secret: { set: false, masked: null },
  oauth_refresh_token: { set: false, masked: null },
  from_address: "",
  configured: false,
  status: "not_configured",
  last_change: { by: "Gözde Ayrancıgil", at: "2026-10-17T20:41:00Z", key: "host" },
  unsent: 0,
};
const TEMPLATES = [
  {
    kind: "approval_rejected",
    label_tr: "Talep reddedildi (gerekçe ve öneriler)",
    label_en: "Request declined",
    audience_tr: "Talep eden",
    audience_en: "The requester",
    tone: "danger",
    sender: "wired",
    owner: "W3-MAIL",
    placeholders: ["name", "org", "what", "who", "reason"],
    shipped: { tr: { subject: "Oda talebiniz reddedildi: {what}", intro: "{who} talebinizi reddetti" }, en: { subject: "Your room request was declined: {what}", intro: "" } },
    overrides: { tr: { subject: null, intro: null }, en: { subject: null, intro: null } },
  },
];

vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { method?: string; body?: unknown } = {}) => {
      const method = opts.method ?? "GET";
      state.calls.push({ path, method, body: opts.body });
      if (path === "/mail/settings" && method === "GET") return state.settings;
      if (path === "/mail/settings" && method === "PUT") {
        state.settings = { ...state.settings, ...(opts.body as object), password: state.settings.password };
        return state.settings;
      }
      if (path === "/mail/presets") return PRESETS;
      if (path === "/mail/templates") return TEMPLATES;
      if (path.endsWith("/preview")) return { subject: "Oda talebiniz reddedildi: A 201", html: "<!DOCTYPE html><html lang=\"tr\"><body><h1>Reddedildi</h1></body></html>", text: "Gözde Ayrancıgil talebinizi reddetti", preheader: "Gerekçe" };
      if (path === "/mail/test")
        return { ok: true, status: "SENT", error: null, hint_tr: null, hint_en: null, transcript: ["S: 220 sink", "C: AUTH PLAIN ********", "S: 235 ok"], duration_ms: 42, outbox_id: 1 };
      if (path === "/booking-admin/outbox") return [];
      throw new Error(`unexpected ${method} ${path}`);
    },
  };
});

import { EmailSettingsPanel } from "../email-settings";

function mount() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale="tr">
        <EmailSettingsPanel />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  state.calls = [];
  state.settings = { ...BASE };
});

describe("EmailSettingsPanel", () => {
  it("shows the shared status line with the last change", async () => {
    mount();
    const status = await screen.findByTestId("mail-status");
    expect(status.textContent).toContain("Yapılandırılmadı");
    expect(status.textContent).toContain("Son değişiklik: Gözde Ayrancıgil");
    expect(screen.getByText("Ayarlar kurumdaki tüm yöneticilerle paylaşılır.")).toBeTruthy();
  });

  it("fills the Microsoft 365 preset, shows the console steps and saves only what changed, never the masked secret", async () => {
    mount();
    fireEvent.click(await screen.findByTestId("mail-preset-microsoft365_oauth2"));
    expect(screen.getByTestId("mail-preset-microsoft365_oauth2").getAttribute("aria-checked")).toBe("true");
    fireEvent.click(screen.getByTestId("mail-next"));
    await waitFor(() => expect(state.calls.some((c) => c.method === "PUT")).toBe(true));
    const put = state.calls.find((c) => c.method === "PUT")!.body as Record<string, unknown>;
    expect(put).toMatchObject({ provider: "microsoft365_oauth2", host: "smtp.office365.com", auth_mode: "xoauth2", oauth_provider: "microsoft" });
    expect(put).not.toHaveProperty("password");
    // step 2: the heading takes focus, the copy value and the Basic-auth note are there
    const heading = await screen.findByRole("heading", { name: "Bağlantı" });
    await waitFor(() => expect(document.activeElement).toBe(heading));
    expect(screen.getAllByDisplayValue("SMTP.SendAsApp").length).toBeGreaterThan(0);
    expect(screen.getByText(/MC786329/)).toBeTruthy();
    expect(screen.getByLabelText("Dizin (kiracı) kimliği")).toBeTruthy();
  });

  it("keeps a saved secret write-only until Değiştir", async () => {
    state.settings = { ...BASE, provider: "custom", host: "smtp.uni.edu.tr" };
    mount();
    fireEvent.click(await screen.findByTestId("mail-step-connection"));
    expect(await screen.findByText("•••••••• kayıtlı")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Değiştir" }));
    expect(screen.getByLabelText("Parola")).toBeTruthy();
  });

  it("asks for the KVKK md. 9 acknowledgement for a provider abroad", async () => {
    state.settings = { ...BASE, provider: "amazon_ses", host: "email-smtp.eu-central-1.amazonaws.com" };
    mount();
    fireEvent.click(await screen.findByTestId("mail-step-sender"));
    const box = await screen.findByTestId("mail-abroad");
    expect(box.textContent).toContain("KVKK md. 9");
    expect(within(box).getByRole("checkbox")).toBeTruthy();
  });

  it("sends the test e-mail and shows the transcript without secrets", async () => {
    state.settings = { ...BASE, provider: "custom", host: "smtp.uni.edu.tr", from_address: "bildirim@uni.edu.tr", configured: true, status: "connected" };
    mount();
    const to = await screen.findByLabelText("Deneme gönderilecek adres");
    fireEvent.change(to, { target: { value: "hoca@uni.edu.tr" } });
    fireEvent.click(screen.getByTestId("mail-test-send"));
    const result = await screen.findByTestId("mail-test-result");
    expect(result.textContent).toContain("Gönderildi: sunucu iletiyi kabul etti (42 ms).");
    expect(screen.getByTestId("mail-transcript").textContent).toContain("C: AUTH PLAIN ********");
    expect(state.calls.find((c) => c.path === "/mail/test")!.body).toEqual({ to: "hoca@uni.edu.tr", locale: "tr" });
  });

  it("previews a template in a sandboxed iframe at desktop and phone width", async () => {
    mount();
    fireEvent.click(await screen.findByRole("tab", { name: "Şablonlar" }));
    fireEvent.click(await screen.findByTestId("mail-tpl-approval_rejected"));
    const frame = (await screen.findByTestId("mail-tpl-frame")) as HTMLIFrameElement;
    expect(frame.getAttribute("sandbox")).toBe("");
    expect(frame.style.width).toBe("640px");
    fireEvent.click(screen.getByRole("radio", { name: "Telefon" }));
    expect(((await screen.findByTestId("mail-tpl-frame")) as HTMLIFrameElement).style.width).toBe("390px");
    expect(screen.getByText("Kullanılabilir alanlar: {name}, {org}, {what}, {who}, {reason}")).toBeTruthy();
    expect(screen.getByTestId("mail-tpl-preview-subject").textContent).toBe("Oda talebiniz reddedildi: A 201");
  });
});
