/**
 * CAL-08 "Takvimime ekle": what → how → approve in three taps (+ the consent tick), scope reasons, only the
 * configured channels, the approval preview, the link / file / push done states, the KVKK-off quiet state.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

type Call = { path: string; method: string; body?: unknown };
const api = vi.hoisted(() => ({
  options: null as unknown,
  subs: [] as unknown[],
  calls: [] as Call[],
  fail: null as null | { path: string; status: number; detail: unknown },
}));

vi.mock("@/lib/api/client", async (orig) => {
  const real = await orig<typeof import("@/lib/api/client")>();
  return {
    ...real,
    request: async (path: string, opts: { method?: string; body?: unknown; schema?: { parse: (v: unknown) => unknown } } = {}) => {
      const method = opts.method ?? "GET";
      api.calls.push({ path, method, body: opts.body });
      if (api.fail && api.fail.path === path && method !== "GET") throw new real.HttpError(api.fail.status, "refused", { detail: api.fail.detail });
      const parse = (v: unknown) => (opts.schema ? opts.schema.parse(v) : v);
      if (path === "/calendar/export/options") return parse(api.options);
      if (path === "/calendar/subscriptions" && method === "GET") return parse(api.subs);
      if (path === "/calendar/subscriptions" && method === "POST")
        return parse({ id: 41, urls: { https: "https://plan.uni.edu.tr/api/v1/calendar/feeds/sst_abc/classes.ics" } });
      if (path === "/me/consents/calendar_sync") return parse([]);
      if (path.endsWith("/scopes")) return {};
      if (path.endsWith("/connect")) return parse({ authorize_url: "https://accounts.example/authorize?x=1" });
      throw new Error(`unexpected ${method} ${path}`);
    },
  };
});

import { CalendarExportSheet } from "./export-sheet";

// a three-step flow with real user events: generous on the shared, loaded host
vi.setConfig({ testTimeout: 20_000 });

const sample = { course_code: "PSY 262", section: "1", location: "A 308", starts_at: "2026-10-19T10:30:00Z", ends_at: "2026-10-19T12:50:00Z" };
function baseOptions(over: Record<string, unknown> = {}) {
  return {
    enabled: true,
    term: { id: 3, name: "2026 Bahar", slug: "2026-bahar" },
    linked: true,
    scopes: [
      { kind: "my_classes", available: true, upcoming: 28, hours: 42, sample },
      {
        kind: "department_classes",
        available: true,
        departments: [
          { id: 7, name: "Psikoloji", available: true, upcoming: 310 },
          { id: 9, name: "Sosyoloji", available: false, reason: "department_not_allowed" },
        ],
      },
      { kind: "my_bookings", available: true, upcoming: 2 },
    ],
    channels: {
      link: true,
      file: true,
      push: [
        { provider: "google", configured: true, connected: false },
        { provider: "microsoft", configured: false, connected: false },
      ],
    },
    consent: { purpose: "calendar_sync", required: true, granted: false },
    ...over,
  };
}

const assign = vi.fn();

function renderSheet(locale: "tr" | "en" = "tr") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>
        <CalendarExportSheet open onOpenChange={() => undefined} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  api.options = baseOptions();
  api.subs = [];
  api.calls = [];
  api.fail = null;
  assign.mockReset();
  Object.defineProperty(window, "location", { configurable: true, value: { ...window.location, assign } });
  try {
    window.sessionStorage.clear();
  } catch {
    /* jsdom */
  }
});

describe("CalendarExportSheet", () => {
  it("opens on step 1 with focus on the heading and three scope cards with reasons", async () => {
    renderSheet();
    const heading = await screen.findByRole("heading", { name: "Neyi eklemek istiyorsunuz?" });
    await waitFor(() => expect(heading).toHaveFocus());
    expect(screen.getByTestId("cal-step")).toHaveTextContent("Adım 1/3");
    expect(screen.getByTestId("cal-scope-my_classes")).toHaveTextContent("Derslerim");
    expect(screen.getByTestId("cal-scope-my_classes")).toHaveTextContent("bu dönem 42 ders saati");
    expect(screen.getByTestId("cal-scope-department_classes:7")).toHaveTextContent("Psikoloji bölümünün tüm dersleri");
    expect(screen.getByTestId("cal-scope-my_bookings")).toHaveTextContent("Rezervasyonlarım");
    const closed = screen.getByTestId("cal-scope-department_classes:9");
    expect(closed).toHaveAttribute("aria-disabled", "true");
    expect(closed.tagName).toBe("DIV");
    expect(closed).toHaveTextContent("Bu bölümün derslerini dışa aktarma yetkiniz yok. Bölüm başkanınızdan isteyin.");
  }, 15_000);

  it("link: Derslerim → Takvim bağlantısı → Onayla ve ekle, consent ticked first; shows webcal, Google, Outlook and copy", async () => {
    const user = userEvent.setup();
    renderSheet();
    await user.click(await screen.findByTestId("cal-scope-my_classes")); // tap 1
    expect(await screen.findByRole("heading", { name: "Nasıl eklemek istiyorsunuz?" })).toBeInTheDocument();
    // only configured channels: Google (recommended), the link, the file; Microsoft is not configured
    const channels = within(screen.getByTestId("cal-channels")).getAllByRole("button");
    expect(channels.map((b) => b.getAttribute("data-testid"))).toEqual(["cal-channel-push:google", "cal-channel-link", "cal-channel-file"]);
    expect(screen.getByTestId("cal-channel-push:google")).toHaveTextContent("Önerilen");
    expect(screen.getByTestId("cal-channel-file")).toHaveTextContent("Güncellenmez");
    // the simplicity principle: refresh times sit behind a closed "Gelişmiş"; the cards read without jargon
    const how = screen.getByTestId("cal-how-advanced");
    expect(how.tagName).toBe("DETAILS");
    expect(how).not.toHaveAttribute("open");
    expect(screen.getByTestId("cal-how-advanced-toggle")).toHaveTextContent("Gelişmiş");
    expect(within(how).getByTestId("cal-refresh-times")).toHaveTextContent("Google Takvim: genellikle 12 saate kadar");
    expect(screen.getByTestId("cal-channels")).not.toHaveTextContent(/webcal|token|ics dosyası|REFRESH/i);
    expect(screen.getByTestId("cal-channel-link")).toHaveTextContent("Abonelik bağlantısı");
    expect(screen.getByTestId("cal-channel-file")).toHaveTextContent("Dosya olarak indir");
    await user.click(screen.getByTestId("cal-channel-link")); // tap 2

    expect(await screen.findByRole("heading", { name: "Takviminize şunlar gönderilecek" })).toBeInTheDocument();
    const fields = screen.getByTestId("cal-fields");
    expect(fields).toHaveTextContent("Ders kodu ve şube");
    expect(fields).toHaveTextContent("Derslik");
    expect(fields).toHaveTextContent("Gün ve saat");
    expect(fields).toHaveTextContent("Bölüm adı");
    expect(screen.getByTestId("cal-never")).toHaveTextContent("Öğrenci bilgisi, not ve diğer öğretim elemanlarının adları gönderilmez.");
    expect(screen.getByTestId("cal-sample")).toHaveTextContent("PSY 262 · Şube 1");
    expect(screen.getByTestId("cal-sample")).toHaveTextContent("A 308 — Pzt 13:30–15:50");

    // the consent is missing: submitting without the tick says so, sends nothing, focuses the box
    await user.click(screen.getByTestId("cal-submit"));
    expect(screen.getByTestId("cal-error")).toHaveTextContent("Devam etmek için onay kutusunu işaretleyin.");
    expect(screen.getByTestId("cal-consent-tick")).toHaveFocus();
    expect(api.calls.some((c) => c.method === "POST")).toBe(false);

    await user.click(screen.getByTestId("cal-consent-tick"));
    await user.click(screen.getByTestId("cal-submit")); // tap 3
    expect(await screen.findByTestId("cal-link")).toBeInTheDocument();
    const posts = api.calls.filter((c) => c.method === "POST").map((c) => c.path);
    expect(posts).toEqual(["/me/consents/calendar_sync", "/calendar/subscriptions"]);
    expect(api.calls.find((c) => c.path === "/calendar/subscriptions" && c.method === "POST")?.body).toEqual({ scope_kind: "my_classes", scope_id: null, channel: "link" });
    expect(screen.getByTestId("cal-link-apple")).toHaveAttribute("href", "webcal://plan.uni.edu.tr/api/v1/calendar/feeds/sst_abc/classes.ics");
    expect(screen.getByTestId("cal-link-google").getAttribute("href")).toContain("calendar.google.com/calendar/r?cid=webcal");
    expect(screen.getByTestId("cal-link-outlook").getAttribute("href")).toContain("addfromweb?url=https");
    // one copy button by default; the raw https / webcal addresses only under "Gelişmiş"
    expect(screen.getByTestId("cal-link-copy")).toHaveTextContent("Bağlantıyı kopyala");
    const adv = screen.getByTestId("cal-link-advanced");
    expect(adv).not.toHaveAttribute("open");
    expect(within(adv).getByTestId("cal-link-webcal-value")).toBeInTheDocument();
    await user.click(screen.getByTestId("cal-link-advanced-toggle"));
    expect(adv).toHaveAttribute("open");
    expect(within(adv).getByTestId("cal-link-https-copy")).toHaveTextContent("Bağlantıyı kopyala");
    expect(screen.getByTestId("cal-link-note")).toHaveTextContent("Bağlantıyı açmayın, abone olun");
    await waitFor(() => expect(screen.getByRole("heading", { name: "Bağlantınız hazır" })).toHaveFocus());
  });

  it("department scope sends its department id and no consent box when the consent is given", async () => {
    api.options = baseOptions({ consent: { purpose: "calendar_sync", required: true, granted: true } });
    const user = userEvent.setup();
    renderSheet();
    await user.click(await screen.findByTestId("cal-scope-department_classes:7"));
    await user.click(await screen.findByTestId("cal-channel-link"));
    expect(screen.queryByTestId("cal-consent")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("cal-submit"));
    await screen.findByTestId("cal-link");
    expect(api.calls.find((c) => c.path === "/calendar/subscriptions" && c.method === "POST")?.body).toEqual({ scope_kind: "department_classes", scope_id: 7, channel: "link" });
    expect(api.calls.some((c) => c.path === "/me/consents/calendar_sync")).toBe(false);
  });

  it("shows the backend's refusal (403 department_not_allowed) in Turkish", async () => {
    api.options = baseOptions({ consent: null });
    api.fail = { path: "/calendar/subscriptions", status: 403, detail: { code: "department_not_allowed", message: "not allowed" } };
    const user = userEvent.setup();
    renderSheet();
    await user.click(await screen.findByTestId("cal-scope-department_classes:7"));
    await user.click(await screen.findByTestId("cal-channel-link"));
    await user.click(screen.getByTestId("cal-submit"));
    expect(await screen.findByTestId("cal-error")).toHaveTextContent("Bu bölümün derslerini dışa aktarma yetkiniz yok.");
  });

  it("file: downloads the one-off .ics and says it does not update", async () => {
    api.options = baseOptions({ consent: null });
    const fetchMock = vi.fn(async () => new Response("BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", { status: 200, headers: { "Content-Type": "text/calendar", "Content-Disposition": 'attachment; filename="derslerim-2026-bahar.ics"' } }));
    vi.stubGlobal("fetch", fetchMock);
    const createObjectURL = vi.fn(() => "blob:x");
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    const user = userEvent.setup();
    renderSheet();
    await user.click(await screen.findByTestId("cal-scope-my_classes"));
    await user.click(await screen.findByTestId("cal-channel-file"));
    expect(screen.getByTestId("cal-submit")).toHaveTextContent("Onayla ve indir");
    await user.click(screen.getByTestId("cal-submit"));
    expect(await screen.findByTestId("cal-file-done")).toHaveTextContent("derslerim-2026-bahar.ics indirildi.");
    expect(screen.getByTestId("cal-file-done")).toHaveTextContent("Güncel kalmasını istiyorsanız bağlantı ya da hesap seçeneğini kullanın.");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/calendar/export/classes.ics", expect.objectContaining({ credentials: "same-origin" }));
    vi.unstubAllGlobals();
  });

  it("push, not connected: stores the scope and goes to the provider with it", async () => {
    api.options = baseOptions({ consent: null });
    const user = userEvent.setup();
    renderSheet();
    await user.click(await screen.findByTestId("cal-scope-my_classes"));
    await user.click(await screen.findByTestId("cal-channel-push:google"));
    await user.click(screen.getByTestId("cal-submit"));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://accounts.example/authorize?x=1"));
    expect(api.calls.find((c) => c.path === "/calendar/connectors/google/connect")?.body).toEqual({ return_path: "/profile", scopes: ["my_classes"] });
    expect(JSON.parse(window.sessionStorage.getItem("smartsched.calendarExport.pending") ?? "{}")).toMatchObject({ provider: "google", kind: "my_classes" });
    expect(screen.getByTestId("cal-push-redirect")).toHaveTextContent("Google Takvim hesabınıza yönlendiriliyorsunuz…");
  });

  it("push, connected: adds the scope to the account and follows the progress until Son eşitleme", async () => {
    api.options = baseOptions({ consent: null, channels: { link: true, file: true, push: [{ provider: "google", configured: true, connected: true, account_email: "ayse@uni.edu.tr", scopes: ["my_bookings"] }] } });
    api.subs = [{ id: 9, scope_kind: "my_classes", channel: "push", provider: "google", synced: 12, total: 28, pending_jobs: 1 }];
    const user = userEvent.setup();
    renderSheet();
    await user.click(await screen.findByTestId("cal-scope-my_classes"));
    expect(screen.getByTestId("cal-channel-push:google")).toHaveTextContent("Bağlı hesap: ayse@uni.edu.tr");
    await user.click(screen.getByTestId("cal-channel-push:google"));
    await user.click(screen.getByTestId("cal-submit"));
    expect(await screen.findByTestId("cal-push-done")).toHaveTextContent("Derslerim Google Takvim takviminize ekleniyor… 12/28");
    expect(api.calls.find((c) => c.path === "/calendar/connectors/google/scopes")?.body).toEqual({ scopes: ["my_bookings", "my_classes"] });
    api.subs = [{ id: 9, scope_kind: "my_classes", channel: "push", provider: "google", synced: 28, total: 28, pending_jobs: 0, last_synced_at: new Date().toISOString() }];
    await act(async () => {
      await new Promise((r) => setTimeout(r, 3200));
    });
    await waitFor(() => expect(screen.getByTestId("cal-push-done")).toHaveTextContent(/Eklendi · Son eşitleme: bugün \d\d:\d\d/));
  }, 10_000);

  it("back returns to the previous step", async () => {
    const user = userEvent.setup();
    renderSheet();
    await user.click(await screen.findByTestId("cal-scope-my_classes"));
    await user.click(await screen.findByTestId("cal-back"));
    expect(await screen.findByRole("heading", { name: "Neyi eklemek istiyorsunuz?" })).toBeInTheDocument();
  });

  it("not linked: Derslerim closed with the reason and a write-to-the-office action", async () => {
    api.options = baseOptions({ linked: false, contact_email: "planlama@uni.edu.tr", scopes: [{ kind: "my_classes", available: false, reason: "not_linked" }, { kind: "my_bookings", available: true }] });
    renderSheet();
    expect(await screen.findByTestId("cal-scope-reason-my_classes")).toHaveTextContent("Hesabınız bir öğretim elemanı kaydına bağlı değil; planlama ofisine başvurun.");
    expect(screen.getByTestId("cal-write-office").getAttribute("href")).toMatch(/^mailto:planlama@uni\.edu\.tr\?subject=/);
  });

  it("KVKK switch off: a quiet sentence, no cards and no buttons", async () => {
    api.options = baseOptions({ enabled: false });
    renderSheet();
    expect(await screen.findByTestId("cal-off")).toHaveTextContent("Takvim aktarımı kurumunuzda kapalı.");
    expect(screen.queryByTestId("cal-scopes")).not.toBeInTheDocument();
  });

  it("reads the CAL-B contract (reason object, preview, provider map) and its own sample line", async () => {
    api.options = {
      enabled: true,
      consent: { purpose: "calendar_sync", required: true, granted: true },
      linked: true,
      scopes: [
        {
          kind: "my_classes",
          label_tr: "Derslerim",
          available: true,
          reason: null,
          preview: {
            upcoming_count: 28,
            sample: { summary: "PSY 262 · Şube 1", location: "A 308", start: "2026-10-19T13:30:00", end: "2026-10-19T15:50:00", text_tr: "PSY 262 · Şube 1 — A 308 — Pzt 13:30–15:50", text_en: "PSY 262 · Section 1 — A 308 — Mon 13:30–15:50" },
            fields: [{ key: "course_code" }, { key: "section" }, { key: "room" }, { key: "time" }, { key: "department" }, { key: "course_title" }, { key: "link" }],
          },
        },
        { kind: "department_classes", available: false, reason: { code: "department_not_allowed", message_tr: "Bu bölümün derslerini dışa aktarma yetkiniz yok. Bölüm başkanınızdan isteyin.", message_en: "no" }, departments: [], default_department_id: null },
        { kind: "my_bookings", available: true, reason: null, preview: { upcoming_count: 0, sample: null, fields: [{ key: "room" }, { key: "time" }] } },
      ],
      channels: { push: { google: { label: "Google", configured: false }, microsoft: { label: "Microsoft 365", configured: true }, freshness_tr: "x" }, link: { available: true }, file: { available: true } },
    };
    const user = userEvent.setup();
    renderSheet();
    expect(await screen.findByTestId("cal-scope-department_classes")).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByTestId("cal-scope-reason-department_classes")).toHaveTextContent("Bu bölümün derslerini dışa aktarma yetkiniz yok.");
    await user.click(screen.getByTestId("cal-scope-my_classes"));
    expect(within(screen.getByTestId("cal-channels")).getAllByRole("button").map((b) => b.getAttribute("data-testid"))).toEqual(["cal-channel-push:microsoft", "cal-channel-link", "cal-channel-file"]);
    await user.click(screen.getByTestId("cal-channel-link"));
    const fields = within(screen.getByTestId("cal-fields")).getAllByRole("listitem").map((li) => li.textContent);
    expect(fields).toEqual(["Ders kodu ve şube", "Derslik", "Gün ve saat", "Bölüm adı", "Ders adı", "SmartSched bağlantısı"]);
    expect(screen.getByTestId("cal-sample")).toHaveTextContent("PSY 262 · Şube 1");
    expect(screen.getByTestId("cal-sample")).toHaveTextContent("A 308 — Pzt 13:30–15:50");
  });

  it("reads in English", async () => {
    renderSheet("en");
    expect(await screen.findByRole("heading", { name: "What would you like to add?" })).toBeInTheDocument();
    expect(await screen.findByTestId("cal-scope-my_classes")).toHaveTextContent("42 teaching hours this term");
  });
});
