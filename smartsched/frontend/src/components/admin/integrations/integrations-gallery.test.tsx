/** W3-HUB integrations gallery: areas and status words, summary + "Dikkat isteyen", tabs, search, switches through
 *  the owning area's endpoint, read-only planning admins, the setup sheet (focus in and back), the guided n8n setup
 *  (save, secret, copy, test event) and the phone rows. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useSyncExternalStore } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({
  calls: [] as { path: string; method: string; body?: unknown }[],
  perms: ["setup.settings"] as string[],
  phone: false,
  url: "",
  listeners: new Set<() => void>(),
  pushed: [] as string[],
  hooks: [] as Record<string, unknown>[],
  deliveries: [] as Record<string, unknown>[],
  webhooksEnabled: false,
  zapierRef: null as number | null,
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("@/components/bookings/use-is-phone", () => ({ useIsPhone: () => state.phone, useIsCompact: () => state.phone }));
vi.mock("next/navigation", () => {
  const setUrl = (u: string) => {
    state.url = u.includes("?") ? u.split("?")[1] : "";
    state.listeners.forEach((l) => l());
  };
  return {
    useRouter: () => ({ replace: (u: string) => setUrl(u), push: (u: string) => state.pushed.push(u) }),
    useSearchParams: () => {
      const url = useSyncExternalStore(
        (cb) => {
          state.listeners.add(cb);
          return () => state.listeners.delete(cb);
        },
        () => state.url,
      );
      return new URLSearchParams(url);
    },
  };
});
vi.mock("next/link", () => ({ default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => <a href={href} {...rest}>{children}</a> }));
// the embedded area panels have their own tests; here they are stand-ins
vi.mock("@/components/identity/identity-providers-panel", () => ({ IdentityProvidersPanel: ({ initialSetup }: { initialSetup: string | null }) => <div data-testid="embed-idp">providers {String(initialSetup)}</div> }));
vi.mock("@/components/admin/email-settings", () => ({ EmailSettingsPanel: () => <div data-testid="embed-email">SMTP</div> }));
vi.mock("@/components/settings/calendar-push-admin", () => ({ CalendarPushAdmin: () => <div data-testid="embed-calendar-push">push</div> }));
vi.mock("@/components/settings/calendar-sync-admin", () => ({ CalendarSyncAdmin: () => <div data-testid="embed-calendar-sync">sync</div> }));
vi.mock("@/components/channels/channels-admin", () => ({ ChannelsAdmin: () => <div data-testid="embed-channels">channels</div> }));
vi.mock("@/components/settings/webhooks-admin", () => ({ WebhooksAdmin: () => <div data-testid="embed-webhooks">webhooks</div> }));
vi.mock("@/lib/permissions", async (orig) => {
  const real = await orig<typeof import("@/lib/permissions")>();
  return { ...real, usePermissions: () => ({ loading: false, perms: state.perms, can: (need: string | string[] | null) => real.hasPermission(state.perms, need), canAll: () => true, userId: 1, departmentId: null }) };
});
vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { method?: string; body?: unknown } = {}) => {
      const method = opts.method ?? "GET";
      state.calls.push({ path, method, body: opts.body });
      if (path === "/integrations/status") return status();
      if (path === "/webhooks" && method === "GET") return state.hooks;
      if (path === "/webhooks" && method === "POST") {
        const b = opts.body as { url: string; events: string[]; description: string };
        const hook = { id: 7, url: b.url, description: b.description, events: b.events, active: true, consecutive_failures: 0, secret_hint: "…wxyz" };
        state.hooks = [hook];
        state.zapierRef = 7; // the next status answer links the Zapier card to the new webhook
        return { ...hook, secret: "whsec_test_secret_wxyz" };
      }
      if (path === "/webhooks/7/test") {
        state.deliveries = [{ id: 31, status: "SENT", response_status: 200, event_type: "ping" }];
        return { delivery_id: 31 };
      }
      if (path === "/webhooks/7/deliveries") return state.deliveries;
      if (path === "/calendar/admin/settings" && method === "GET") return calendarSettings();
      if (method === "PUT") return {};
      throw new Error(`unexpected ${method} ${path}`);
    },
  };
});

import { IntegrationsGallery } from "./integrations-gallery";

function c(key: string, name: string, status: string, extra: Record<string, unknown> = {}) {
  const area = key.split(".")[0];
  return { key, area, name_tr: name, name_en: name, summary_tr: `${name} bağlantısı.`, summary_en: `${name} connection.`, status, setup_href: `/admin/integrations?tab=${area}&setup=${key}`, source: "builtin", ...extra };
}
function status() {
  return {
    generated_at: "2026-10-17T20:00:00Z",
    counts: { connected: 2, error: 1, not_configured: 3, disabled: 1, unknown: 1 },
    asks: [{ area: "identity", lane: "W3-IDP", function: "app.services.identity.integration_status(session) -> list[dict]" }],
    areas: [
      { key: "identity", label_tr: "Kimlik", label_en: "Identity", cards: [c("identity.providers", "Kimlik sağlayıcıları", "unknown", { source: "missing", detail_tr: "Bu alanın durumu şu an okunamıyor." })] },
      { key: "email", label_tr: "E-posta", label_en: "E-mail", cards: [c("email.smtp", "E-posta (SMTP)", "connected", { source: "contract", last_check_at: "2026-10-17T19:00:00Z", last_check_ok: true, changed_by: "Ayşe Yılmaz", changed_at: "2026-10-17T17:00:00Z" })] },
      {
        key: "calendar",
        label_tr: "Takvim",
        label_en: "Calendar",
        cards: [
          c("calendar.google", "Google Takvim", "disabled", { enabled: false, changed_by: "Mehmet Kaya", changed_at: "2026-10-17T16:40:00Z", toggle: { method: "PUT", path: "/calendar/admin/settings", field: "calendar_sync_enabled", enable_in_setup: true } }),
          c("calendar.microsoft", "Microsoft 365 takvimi", "not_configured"),
        ],
      },
      { key: "channels", label_tr: "Kanallar", label_en: "Channels", cards: [c("channels.telegram", "Telegram", "connected", { enabled: true, toggle: { method: "PUT", path: "/channels/admin/telegram", field: "enabled", enable_in_setup: true } })] },
      {
        key: "automation",
        label_tr: "Webhook ve otomasyon",
        label_en: "Webhooks and automation",
        cards: [c("automation.webhooks", "Webhook gönderimi", "not_configured"), c("automation.n8n", "n8n", "error", { enabled: true, detail_tr: "Son gönderim başarısız oldu.", ref: { webhook_id: 3 }, toggle: { method: "PUT", path: "/webhooks/3", field: "active", enable_in_setup: false } }), state.zapierRef ? c("automation.zapier", "Zapier", "disabled", { enabled: true, ref: { webhook_id: state.zapierRef }, toggle: { method: "PUT", path: `/webhooks/${state.zapierRef}`, field: "active", enable_in_setup: false } }) : c("automation.zapier", "Zapier", "not_configured")],
      },
      { key: "ai", label_tr: "Yapay zekâ", label_en: "AI", cards: [c("ai.providers", "Yapay zekâ sağlayıcıları", "connected", { setup_href: "/admin/ai" })] },
    ],
  };
}
function calendarSettings() {
  const client = { client_id: "", client_secret: { set: false, masked: null }, configured: false, redirect_uri: "" };
  return { calendar_sync_enabled: false, calendar_sync_signoff: null, webhooks_enabled: state.webhooksEnabled, public_url: "https://planlama.uni.edu.tr", public_url_source: "setting", feed_past_days: 90, feed_cancelled_grace_days: 14, google: client, microsoft: { ...client, tenant: "organizations" } };
}

function renderIt(url = "", locale: "tr" | "en" = "tr") {
  state.url = url;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>
        <IntegrationsGallery />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("IntegrationsGallery", () => {
  beforeEach(() => {
    state.calls = [];
    state.perms = ["setup.settings"];
    state.phone = false;
    state.pushed = [];
    state.hooks = [];
    state.deliveries = [];
    state.webhooksEnabled = false;
    state.zapierRef = null;
    toast.success.mockReset();
    toast.error.mockReset();
  });

  it("shows every area in Tümü, in the backend's order, with Turkish status words, summary and last change", async () => {
    renderIt();
    const gallery = await screen.findByTestId("integrations-gallery");
    await screen.findByTestId("connector-email.smtp");
    const areas = within(gallery).getAllByRole("heading", { level: 2 }).map((h) => h.textContent);
    expect(areas).toEqual(expect.arrayContaining(["Kimlik", "E-posta", "Takvim", "Kanallar", "Webhook ve otomasyon", "Yapay zekâ"]));
    expect(screen.getByTestId("integrations-summary")).toHaveTextContent("2 bağlı · 1 hata · 3 yapılandırılmadı");
    expect(within(screen.getByTestId("connector-email.smtp")).getByTestId("connector-status")).toHaveTextContent("Bağlı");
    expect(within(screen.getByTestId("connector-calendar.microsoft")).getByTestId("connector-status")).toHaveTextContent("Yapılandırılmadı");
    expect(within(screen.getByTestId("connector-calendar.google")).getByTestId("connector-status")).toHaveTextContent("Kapalı");
    expect(within(screen.getByTestId("connector-identity.providers")).getByTestId("connector-status")).toHaveTextContent("Bilinmiyor");
    expect(screen.getByTestId("connector-email.smtp")).toHaveTextContent("Son değişiklik: Ayşe Yılmaz,");
    expect(screen.getByTestId("connector-calendar.microsoft")).toHaveTextContent("Henüz kurulmadı");
    // fixed order inside an area (an error card is not moved to the top)
    const auto = within(screen.getByTestId("integrations-area-automation")).getAllByRole("article").map((a) => a.getAttribute("data-testid"));
    expect(auto).toEqual(["connector-automation.webhooks", "connector-automation.n8n", "connector-automation.zapier"]);
    expect(within(screen.getByTestId("connector-calendar.microsoft")).getByTestId("connector-primary")).toHaveTextContent("Kur");
    expect(within(screen.getByTestId("connector-email.smtp")).getByTestId("connector-primary")).toHaveTextContent("Yönet");
    expect(gallery.textContent).not.toMatch(/integrations\.|not_configured|W3-IDP/);
    expect(screen.getByTestId("integrations-tab-identity")).toHaveTextContent("Kimlik1");
  });

  it("pins cards in error under Dikkat isteyen; Sorunu gider opens the sheet with focus on its heading", async () => {
    const user = userEvent.setup();
    renderIt();
    const row = await screen.findByTestId("integrations-attention");
    expect(row).toHaveTextContent("Dikkat isteyen");
    expect(row).toHaveTextContent("n8n · Son gönderim başarısız oldu.");
    await user.click(within(row).getByRole("button", { name: "n8n: sorunu gider" }));
    expect(state.url).toBe("setup=automation.n8n");
    const sheet = await screen.findByTestId("setup-sheet");
    await waitFor(() => expect(within(sheet).getByTestId("setup-title")).toHaveFocus());
    expect(within(sheet).getByTestId("guided-webhook")).toBeInTheDocument();
  });

  it("switches through the owning area's endpoint: off asks first, KVKK-gated on goes to the setup", async () => {
    const user = userEvent.setup();
    renderIt();
    const tg = await screen.findByTestId("connector-channels.telegram");
    await user.click(within(tg).getByRole("switch", { name: "Telegram: Kullanımda" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("Telegram kapatılsın mı?");
    expect(state.calls.some((x) => x.method === "PUT")).toBe(false);
    // the dialog's own ✕ (rendered last) is also named "Kapat"; the destructive action comes first
    await user.click(within(dialog).getAllByRole("button", { name: "Kapat" })[0]);
    await waitFor(() => expect(state.calls).toContainEqual({ path: "/channels/admin/telegram", method: "PUT", body: { enabled: false } }));
    expect(toast.success).toHaveBeenCalledWith("Telegram kapatıldı");
    await waitFor(() => expect(within(tg).getByTestId("connector-primary")).toHaveFocus());

    const google = screen.getByTestId("connector-calendar.google");
    await user.click(within(google).getByRole("switch", { name: "Google Takvim: Kullanımda" }));
    expect(state.url).toBe("setup=calendar.google");
    expect(state.calls.some((x) => x.path === "/calendar/admin/settings" && x.method === "PUT")).toBe(false);
    const sheet = await screen.findByTestId("setup-sheet");
    expect(within(sheet).getByTestId("embed-calendar-sync")).toBeInTheDocument();
    expect(within(sheet).getByTestId("embed-calendar-push")).toBeInTheDocument();
    // Bitti closes the sheet and focus returns to the card
    await user.click(within(sheet).getByTestId("setup-done"));
    expect(state.url).toBe("");
    await waitFor(() => expect(within(google).getByTestId("connector-primary")).toHaveFocus());
  });

  it("planning admins see the same cards read-only (no switches, Yalnız görüntüleme)", async () => {
    state.perms = ["planning.admin"];
    renderIt();
    await screen.findByTestId("connector-email.smtp");
    expect(screen.queryAllByRole("switch")).toHaveLength(0);
    expect(screen.queryAllByTestId("connector-primary")).toHaveLength(0);
    expect(screen.getAllByTestId("connector-readonly")[0]).toHaveTextContent("Yalnız görüntüleme");
  });

  it("refuses people without the hub permissions and never asks the backend", async () => {
    state.perms = ["setup.rooms"];
    renderIt();
    expect(await screen.findByText(/Kurum ayarları/)).toBeInTheDocument();
    expect(state.calls.some((x) => x.path === "/integrations/status")).toBe(false);
  });

  it("filters by tab (in the URL) and by a Turkish search", async () => {
    const user = userEvent.setup();
    renderIt();
    await screen.findByTestId("connector-email.smtp");
    await user.click(screen.getByTestId("integrations-tab-channels"));
    expect(state.url).toBe("area=channels");
    await waitFor(() => expect(screen.queryByTestId("connector-email.smtp")).not.toBeInTheDocument());
    expect(screen.getByTestId("connector-channels.telegram")).toBeInTheDocument();
    await user.click(screen.getByTestId("integrations-tab-all"));
    await user.type(screen.getByTestId("integrations-search"), "TAKVİM");
    expect(screen.getByTestId("connector-calendar.google")).toBeInTheDocument();
    expect(screen.queryByTestId("connector-channels.telegram")).not.toBeInTheDocument();
    await user.clear(screen.getByTestId("integrations-search"));
    await user.type(screen.getByTestId("integrations-search"), "zzz");
    expect(screen.getByText("\"zzz\" ile eşleşen entegrasyon yok.")).toBeInTheDocument();
  });

  it("opens the AI screen for the card it owns", async () => {
    const user = userEvent.setup();
    renderIt("area=ai");
    const ai = await screen.findByTestId("connector-ai.providers");
    await user.click(within(ai).getByRole("button", { name: "Yapay zekâ sağlayıcıları: Yapay zekâ ekranında yönet" }));
    expect(state.pushed).toEqual(["/admin/ai"]);
  });

  it("embeds W3-IDP's identity providers panel (and the e-mail panel) in the sheet", async () => {
    renderIt("area=identity&setup=identity.providers");
    const sheet = await screen.findByTestId("setup-sheet");
    expect(await within(sheet).findByTestId("embed-idp")).toHaveTextContent("providers null");
    expect(within(sheet).getByText(/yeni kurulum ekranı hazırlanıyor/)).toBeInTheDocument();
  });

  it("accepts an area's short setup name and opens its provider in the identity panel", async () => {
    renderIt("area=identity&setup=providers");
    const sheet = await screen.findByTestId("setup-sheet");
    await waitFor(() => expect(within(sheet).getByTestId("setup-title")).toHaveTextContent("Kimlik sağlayıcıları"));
    expect(await within(sheet).findByTestId("embed-idp")).toBeInTheDocument();
  });

  it("opens the e-mail card's SMTP panel", async () => {
    renderIt("area=email&setup=email.smtp");
    const sheet = await screen.findByTestId("setup-sheet");
    expect(await within(sheet).findByTestId("embed-email")).toBeInTheDocument();
    expect(within(sheet).getByTestId("setup-lines")).toHaveTextContent("Son değişiklik: Ayşe Yılmaz,");
  });

  it("guided n8n setup: paste the URL, save, copy the secret once, send a test event and see it arrive", { timeout: 30_000 }, async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    renderIt("area=automation&setup=automation.zapier");
    const sheet = await screen.findByTestId("setup-sheet");
    const guided = await within(sheet).findByTestId("guided-webhook");
    expect(guided).toHaveTextContent("Catch Raw Hook");
    expect(await within(guided).findByText("Webhook gönderimi kapalı: test olayı gider, rezervasyon olayları gönderilmez.")).toBeInTheDocument();
    const url = within(guided).getByTestId("guided-url");
    await user.type(url, "https://example.org/x");
    expect(guided).toHaveTextContent("Bu adres bir Zapier adresine benzemiyor");
    await user.clear(url);
    await user.type(url, "https://hooks.zapier.com/hooks/catch/1/abc/");
    await user.click(within(guided).getByTestId("guided-save"));
    await waitFor(() => expect(state.calls).toContainEqual({ path: "/webhooks", method: "POST", body: { url: "https://hooks.zapier.com/hooks/catch/1/abc/", events: ["*"], description: "zapier akışı" } }));
    // the status refresh after saving links the card to webhook 7: the sheet must keep the one-time secret
    await waitFor(() => expect(state.calls.filter((x) => x.path === "/integrations/status").length).toBeGreaterThan(1));
    const secret = await within(guided).findByTestId("guided-secret");
    expect(within(secret).getByRole("textbox")).toHaveValue("whsec_test_secret_wxyz");
    expect(guided).toHaveTextContent("Bu anahtar yalnızca şimdi gösterilir.");
    await user.click(within(secret).getByRole("button", { name: "İmza anahtarı kopyala" }));
    expect(writeText).toHaveBeenCalledWith("whsec_test_secret_wxyz");
    expect(within(secret).getByTestId("guided-secret-copy")).toHaveTextContent("Kopyalandı");
    expect(toast.success).not.toHaveBeenCalledWith("Kopyalandı"); // in place, no toast
    await user.click(within(guided).getByTestId("guided-test"));
    await waitFor(() => expect(within(guided).getByTestId("guided-result")).toHaveTextContent("Test olayı ulaştı (HTTP 200)."));
    expect(state.calls).toContainEqual({ path: "/webhooks/7/test", method: "POST", body: undefined });
  });

  it("copy falls back to selecting the value when the clipboard is unavailable", async () => {
    const user = userEvent.setup();
    Object.defineProperty(navigator, "clipboard", { value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) }, configurable: true });
    renderIt("area=automation&setup=automation.n8n");
    const snippet = await screen.findByTestId("guided-snippet");
    await user.click(within(snippet).getByRole("button", { name: "İmza doğrulama kodu kopyala" }));
    expect(await within(snippet).findByText("Kopyalanamadı; değer seçildi, Ctrl+C ile kopyalayın.")).toBeInTheDocument();
  });

  it("phones: 64 px rows without switches; the switch is in the full-screen sheet with a back button", async () => {
    state.phone = true;
    const user = userEvent.setup();
    renderIt();
    const row = await screen.findByTestId("connector-channels.telegram");
    expect(row.tagName).toBe("BUTTON");
    expect(row).toHaveAccessibleName("Telegram, Bağlı");
    expect(screen.queryAllByRole("switch")).toHaveLength(0);
    await user.click(row);
    const sheet = await screen.findByTestId("setup-sheet");
    expect(within(sheet).getByRole("switch", { name: "Telegram: Kullanımda" })).toBeChecked();
    await user.click(within(sheet).getByTestId("setup-back"));
    expect(state.url).toBe("");
    await act(async () => undefined);
  });

  it("phones: the guided setup goes one step per screen with Adım n / 4", async () => {
    state.phone = true;
    const user = userEvent.setup();
    renderIt("area=automation&setup=automation.zapier");
    const guided = await screen.findByTestId("guided-webhook");
    expect(within(guided).getByTestId("guided-step")).toHaveTextContent("Adım 1 / 4");
    expect(within(guided).queryByTestId("guided-url")).not.toBeInTheDocument();
    await user.click(within(guided).getByTestId("guided-next"));
    expect(within(guided).getByTestId("guided-step")).toHaveTextContent("Adım 2 / 4");
    expect(within(guided).getByTestId("guided-url")).toBeInTheDocument();
    expect(within(guided).getByTestId("guided-prev")).toBeInTheDocument();
  });

  it("speaks English too", async () => {
    renderIt("", "en");
    expect(await screen.findByTestId("integrations-summary")).toHaveTextContent("2 connected · 1 with errors · 3 not set up");
    expect(within(screen.getByTestId("connector-calendar.microsoft")).getByTestId("connector-primary")).toHaveTextContent("Set up");
  });
});
