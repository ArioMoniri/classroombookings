/** Consent UI (consent gates 2026-10-16): the calendar-sync consent step before "create link" / "reset" / "connect"
 * and the 409 `consent_required` link; the Gizlilik AI text by `ai_personal_default` + `ai_excluded`; Admin › KVKK
 * `kvkk.ai_personal_default` (GET / PUT /settings, 422 next to the field); an erasure's `failures[]` and `calendar[]`. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => "/my-bookings",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), message: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

type Call = { path: string; method: string; body?: unknown; query?: Record<string, unknown> };
const api = vi.hoisted(() => ({
  calls: [] as Call[],
  sync: null as unknown,
  privacy: null as unknown,
  aiDefault: "included" as string,
  putError: null as unknown,
  createError: null as unknown,
  queue: [] as unknown[],
}));

vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  const made = { id: 7, label: "SmartSched", token: "sst_x", hint: "abcd", urls: { mine: "/api/v1/calendar/feeds/sst_x/mine.ics", room: "/api/v1/calendar/feeds/sst_x/room/{id}.ics", department: "/api/v1/calendar/feeds/sst_x/department/{id}.ics" } };
  return {
    ...real,
    request: async (path: string, opts: { method?: string; body?: unknown; query?: Record<string, unknown> } = {}) => {
      const method = opts.method ?? "GET";
      api.calls.push({ path, method, body: opts.body, query: opts.query });
      if (path === "/auth/me") return { id: 5, username: "ayse", email: "ayse@uni.edu.tr", department_id: null };
      if (path === "/calendar/sync") return api.sync;
      if (path === "/calendar/feeds/options") return { rooms: [], room_groups: [], departments: [] };
      if (path === "/me/consents/calendar_sync" && method === "POST") {
        api.sync = { ...(api.sync as object), consent: { purpose: "calendar_sync", required: true, granted: true } };
        return [{ purpose: "calendar_sync", label_tr: "Takvim", label_en: "Calendar", granted: true }];
      }
      if (path === "/calendar/feeds/tokens" || path === "/calendar/feeds/reset") {
        if (api.createError) throw new real.HttpError(409, "409", { detail: api.createError });
        return made;
      }
      if (path.endsWith("/connect")) return { authorize_url: "https://accounts.google.com/o/oauth2/v2/auth?x=1" };
      if (path === "/me/privacy") return api.privacy;
      if (path === "/settings" && method === "GET") return { anthropic_model: "claude", "kvkk.ai_personal_default": api.aiDefault };
      if (path === "/settings" && method === "PUT") {
        if (api.putError) throw new real.HttpError(422, "422", { detail: api.putError });
        api.aiDefault = (opts.body as { extra: Record<string, string> }).extra["kvkk.ai_personal_default"]!;
        return { "kvkk.ai_personal_default": api.aiDefault };
      }
      if (path === "/admin/dsr") return api.queue;
      throw new Error(`unexpected ${method} ${path}`);
    },
  };
});

import { CalendarSyncPanel } from "@/components/bookings/calendar-sync";
import { AiDefaultEditor } from "@/components/kvkk/ai-default";
import { DsrQueue } from "@/components/kvkk/dsr-queue";
import { erasureCalendars, erasureFailures } from "@/lib/api/kvkk";
import { consentRefusal, needsCalendarConsent } from "./calendar-consent";
import { aiConsentText, PrivacySection } from "./privacy-section";
import { HttpError } from "@/lib/api/client";

function renderIt(ui: React.ReactNode, locale: "en" | "tr" = "en") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>{ui}</I18nProvider>
    </QueryClientProvider>,
  );
}

const google = { provider: "google", label: "Google Calendar", configured: true, connected: false };
const sync = (consent?: { required: boolean; granted: boolean }, tokens: unknown[] = []) => ({
  enabled: true,
  feeds: { tokens, url_templates: { mine: "", room: "", department: "" } },
  connectors: [google],
  ...(consent ? { consent: { purpose: "calendar_sync", ...consent } } : {}),
});
const posts = () => api.calls.filter((c) => c.method !== "GET").map((c) => `${c.method} ${c.path}`);
const refusal409 = { code: "consent_required", message: 'This needs your consent "Calendar sync".', message_en: 'This needs your consent "Calendar sync". You can give it under Profile › Privacy.', message_tr: 'Bunun için "Takvim eşitleme" rızanız gerekir.', purpose: "calendar_sync", grant_path: "/profile#privacy", grant_api: "POST /api/v1/me/consents/calendar_sync" };

const assign = vi.fn();
beforeEach(() => {
  api.calls = [];
  api.createError = null;
  api.putError = null;
  api.aiDefault = "included";
  toast.success.mockReset();
  toast.error.mockReset();
  window.sessionStorage.clear();
  Object.defineProperty(window, "location", { configurable: true, value: { ...window.location, origin: "https://rez.uni.edu.tr", assign } });
  assign.mockReset();
});

describe("calendar consent helpers", () => {
  it("asks only while the consent is required and not granted", () => {
    expect(needsCalendarConsent(undefined)).toBe(false);
    expect(needsCalendarConsent({ consent: undefined })).toBe(false);
    expect(needsCalendarConsent({ consent: { purpose: "calendar_sync", required: false, granted: false } })).toBe(false);
    expect(needsCalendarConsent({ consent: { purpose: "calendar_sync", required: true, granted: true } })).toBe(false);
    expect(needsCalendarConsent({ consent: { purpose: "calendar_sync", required: true, granted: false } })).toBe(true);
  });

  it("reads a 409 consent_required in the reader's language with its grant_path; anything else is null", () => {
    const e = new HttpError(409, "409", { detail: refusal409 });
    expect(consentRefusal(e, "tr")).toEqual({ text: 'Bunun için "Takvim eşitleme" rızanız gerekir.', href: "/profile#privacy", purpose: "calendar_sync" });
    expect(consentRefusal(e, "en")?.text).toContain("under Profile › Privacy");
    expect(consentRefusal(new HttpError(409, "409", { detail: { ...refusal409, grant_path: "https://evil.example/x" } }), "en")?.href).toBe("/profile#privacy");
    expect(consentRefusal(new HttpError(409, "409", { detail: { code: "duplicate", message: "x" } }), "en")).toBeNull();
  });
});

describe("CalendarSyncPanel consent step", () => {
  it("makes the link at once when no consent is needed", async () => {
    const user = userEvent.setup();
    api.sync = sync({ required: true, granted: true });
    renderIt(<CalendarSyncPanel />);
    await user.click(await screen.findByTestId("sync-create"));
    expect(await screen.findByTestId("sync-url-mine")).toHaveValue("https://rez.uni.edu.tr/api/v1/calendar/feeds/sst_x/mine.ics");
    expect(posts()).toEqual(["POST /calendar/feeds/tokens"]);
    expect(screen.queryByTestId("calendar-consent-step")).toBeNull();
  });

  it("asks for the calendar_sync consent before Create link, gives it, then makes the link", async () => {
    const user = userEvent.setup();
    api.sync = sync({ required: true, granted: false });
    renderIt(<CalendarSyncPanel />);
    await user.click(await screen.findByTestId("sync-create"));
    const step = await screen.findByTestId("calendar-consent-step");
    expect(step).toHaveTextContent("Calendar sync needs your consent");
    expect(step).toHaveTextContent("explicit consent (KVKK)");
    expect(within(step).getByRole("link", { name: "Go to Privacy" })).toHaveAttribute("href", "/profile#privacy");
    expect(step).toHaveFocus();
    expect(posts()).toEqual([]);
    await user.click(within(step).getByTestId("calendar-consent-grant"));
    expect(await screen.findByTestId("sync-url-mine")).toHaveValue("https://rez.uni.edu.tr/api/v1/calendar/feeds/sst_x/mine.ics");
    expect(posts()).toEqual(["POST /me/consents/calendar_sync", "POST /calendar/feeds/tokens"]);
    expect(screen.queryByTestId("calendar-consent-step")).toBeNull();
  });

  it("Not now / Escape closes the step without asking the server", async () => {
    const user = userEvent.setup();
    api.sync = sync({ required: true, granted: false });
    renderIt(<CalendarSyncPanel />, "tr");
    await user.click(await screen.findByTestId("sync-create"));
    await user.click(await screen.findByRole("button", { name: "Şimdi değil" }));
    expect(screen.queryByTestId("calendar-consent-step")).toBeNull();
    await user.click(screen.getByTestId("sync-create"));
    await screen.findByTestId("calendar-consent-step");
    await user.keyboard("{Escape}");
    expect(screen.queryByTestId("calendar-consent-step")).toBeNull();
    expect(posts()).toEqual([]);
  });

  it("Reset with links made earlier: consent first, then the usual confirmation", async () => {
    const user = userEvent.setup();
    api.sync = sync({ required: true, granted: false }, [{ id: 1, hint: "wxyz" }]);
    renderIt(<CalendarSyncPanel />);
    await user.click(await screen.findByTestId("sync-reset"));
    await user.click(within(await screen.findByTestId("calendar-consent-step")).getByTestId("calendar-consent-grant"));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /Reset/ }));
    await waitFor(() => expect(posts()).toEqual(["POST /me/consents/calendar_sync", "POST /calendar/feeds/reset"]));
  });

  it("Connect a configured provider: consent first, then the browser goes to the authorize URL", async () => {
    const user = userEvent.setup();
    api.sync = sync({ required: true, granted: false });
    renderIt(<CalendarSyncPanel />);
    await user.click(await screen.findByTestId("sync-connect-google"));
    await user.click(within(await screen.findByTestId("sync-consent-google")).getByTestId("calendar-consent-grant"));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://accounts.google.com/o/oauth2/v2/auth?x=1"));
    expect(posts()).toEqual(["POST /me/consents/calendar_sync", "POST /calendar/connectors/google/connect"]);
  });

  it("a 409 consent_required shows the backend's sentence with a link to grant_path", async () => {
    const user = userEvent.setup();
    api.sync = sync({ required: true, granted: true });
    api.createError = refusal409;
    renderIt(<CalendarSyncPanel />, "tr");
    await user.click(await screen.findByTestId("sync-create"));
    const alert = await screen.findByTestId("calendar-consent-refused");
    expect(alert).toHaveTextContent('Bunun için "Takvim eşitleme" rızanız gerekir.');
    expect(within(alert).getByRole("link", { name: "Gizlilik bölümüne git" })).toHaveAttribute("href", "/profile#privacy");
    expect(toast.error).not.toHaveBeenCalled();
  });
});

describe("Gizlilik: the AI consent text", () => {
  const ai = (granted: boolean, withdrawn_at: string | null = null) => ({ purpose: "ai_personal", label_tr: "Yapay zekâ", label_en: "AI assistant", granted, granted_at: granted ? "2026-10-01T09:00:00" : null, withdrawn_at });

  it("picks the reason from the default and the person's state", () => {
    expect(aiConsentText(ai(true), "included", false)).toEqual({ out: false, key: "privacy.ai.includedDefault" });
    expect(aiConsentText(ai(false), "included", false)).toEqual({ out: false, key: "privacy.ai.includedDefault" });
    expect(aiConsentText(ai(false, "2026-10-02T09:00:00"), "included", true)).toEqual({ out: true, key: "privacy.ai.excludedWithdrawn" });
    expect(aiConsentText(ai(false), "excluded", true)).toEqual({ out: true, key: "privacy.ai.excludedDefault" });
    expect(aiConsentText(ai(false, "2026-10-02T09:00:00"), "excluded", true)).toEqual({ out: true, key: "privacy.ai.excludedWithdrawn" });
    expect(aiConsentText(ai(true), "excluded", false)).toEqual({ out: false, key: "privacy.ai.includedConsent" });
  });

  it("says the person is kept out and why (not given, institution counts it as no)", async () => {
    api.privacy = { notice: null, needs_ack: false, consents: [ai(false)], requests: [], due_days: 30, ai_personal_default: "excluded", ai_excluded: true };
    renderIt(<PrivacySection />, "tr");
    const state = await screen.findByTestId("consent-ai-state");
    expect(state).toHaveTextContent("Şu an: yapay zekâ isteklerinin dışındasınız");
    expect(state).toHaveAttribute("data-excluded", "true");
    expect(screen.getByTestId("consent-ai-text")).toHaveTextContent("Bu rızayı vermediğiniz ve kurumunuz bunu hayır saydığı için dışarıdasınız");
  });

  it("an older backend without the fields reads as included unless withdrawn", async () => {
    api.privacy = { notice: null, needs_ack: false, consents: [ai(true)], requests: [], due_days: 30 };
    renderIt(<PrivacySection />);
    expect(await screen.findByTestId("consent-ai-state")).toHaveTextContent("Now: your name and e-mail can go into AI requests");
    expect(screen.getByTestId("consent-ai-text")).toHaveTextContent("includes everyone in AI assistant requests unless they withdraw");
  });
});

describe("Admin › KVKK: kvkk.ai_personal_default", () => {
  it("reads the stored value, explains both options and saves the other one through PUT /settings extra", async () => {
    const user = userEvent.setup();
    renderIt(<AiDefaultEditor />);
    const included = await screen.findByTestId("kvkk-ai-included");
    expect(included).toBeChecked();
    expect(screen.getByTestId("kvkk-ai-option-included")).toHaveTextContent("Saved setting");
    expect(screen.getByTestId("kvkk-ai-option-excluded")).toHaveTextContent("kept out until they give the AI consent");
    expect(screen.getByTestId("kvkk-ai-save")).toBeDisabled();
    await user.click(screen.getByTestId("kvkk-ai-excluded"));
    await user.click(screen.getByTestId("kvkk-ai-save"));
    await waitFor(() => expect(api.calls).toContainEqual({ path: "/settings", method: "PUT", body: { extra: { "kvkk.ai_personal_default": "excluded" } }, query: undefined }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Saved. Everyone's Privacy page now explains the new meaning."));
    expect(screen.getByTestId("kvkk-ai-option-excluded")).toHaveTextContent("Saved setting");
    expect(screen.getByTestId("kvkk-ai-save")).toBeDisabled();
  });

  it("shows a 422 message_tr next to the field", async () => {
    const user = userEvent.setup();
    api.putError = { code: "ai_personal_default", field: "kvkk.ai_personal_default", message: "x", message_en: "kvkk.ai_personal_default is included or excluded", message_tr: "kvkk.ai_personal_default değeri included ya da excluded olabilir", allowed: ["included", "excluded"] };
    renderIt(<AiDefaultEditor />, "tr");
    await user.click(await screen.findByTestId("kvkk-ai-excluded"));
    await user.click(screen.getByTestId("kvkk-ai-save"));
    expect(await screen.findByTestId("kvkk-ai-error")).toHaveTextContent("included ya da excluded olabilir");
    expect(screen.getByRole("group")).toHaveAttribute("aria-invalid", "true");
  });
});

describe("KVKK queue: an erasure's failures and calendars", () => {
  const result = {
    counts: { calendar_connections: 2, consents: 1 },
    calendar: [
      { provider: "google", events: 4, events_removed: 3, events_failed: 1, revoke: "failed", errors: ["HTTP 500"] },
      { provider: "microsoft", events: 2, events_removed: 2, events_failed: 0, revoke: "not_supported", errors: [] },
    ],
    failures: [
      { provider: "google", code: "events_not_removed", message_en: "1 event(s) SmartSched had added to the person's Google Calendar could not be removed", message_tr: "kişinin Google Calendar takvimine SmartSched'in eklediği 1 etkinlik silinemedi", count: 1, error: "HTTP 500" },
      { provider: "google", code: "revoke_failed", message_en: "the Google Calendar grant could not be revoked at the provider", message_tr: "Google Calendar yetkisi sağlayıcıda iptal edilemedi", error: "HTTP 500" },
    ],
    partial: true,
  };

  it("parses failures[] and calendar[] defensively", () => {
    expect(erasureFailures(result)).toHaveLength(2);
    expect(erasureFailures({ failures: [null, 3, { code: "x" }, { message_tr: "yalnız TR" }] })).toEqual([{ provider: "", code: "", message_en: "yalnız TR", message_tr: "yalnız TR" }]);
    expect(erasureFailures(null)).toEqual([]);
    expect(erasureCalendars(result)[0]).toEqual({ provider: "google", events: 4, events_removed: 3, events_failed: 1, revoke: "failed" });
    expect(erasureCalendars({ calendar: [{ events: 1 }] })).toEqual([]);
  });

  it("the result panel lists each failure (provider, code, TR text) and what happened to each calendar", async () => {
    const user = userEvent.setup();
    api.queue = [{ id: 4, kind: "erase", status: "DONE", created_at: "2026-10-10T09:00:00", handled_at: "2026-10-16T09:00:00", subject: "Ayrılan Kişi", result, downloadable: false }];
    renderIt(<DsrQueue />, "tr");
    await user.click(await screen.findByTestId("dsr-filter-done"));
    await user.click(await screen.findByRole("button", { name: "Silinenleri göster" }));
    const failures = await screen.findByTestId("dsr-failures");
    expect(failures).toHaveTextContent("2 adım ilginizi bekliyor");
    const first = within(failures).getByTestId("dsr-failure-google-events_not_removed");
    expect(first).toHaveTextContent("Google Takvim");
    expect(first).toHaveTextContent("etkinlik silinemedi");
    expect(first).toHaveTextContent("events_not_removed");
    expect(first).toHaveTextContent("Sağlayıcının yanıtı: HTTP 500");
    const cal = screen.getByTestId("dsr-calendar");
    expect(within(cal).getByTestId("dsr-calendar-google")).toHaveTextContent("4 etkinliğin 3 tanesi silindi · 1 tanesi silinemedi · erişimin iptali başarısız oldu");
    expect(within(cal).getByTestId("dsr-calendar-microsoft")).toHaveAttribute("data-revoke", "not_supported");
  });
});
