/** Profil › Takvim aktarımı: states (off, not configured, connected, re-auth), the connect URL hand-off, the
 * redirect result and disconnect. No live provider: the backend's authorize URL is what the browser is sent to. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { HttpError } from "@/lib/api/client";

const nav = vi.hoisted(() => ({ params: new URLSearchParams(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => nav.params,
  usePathname: () => "/profile",
  useRouter: () => ({ replace: nav.replace, push: vi.fn() }),
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), message: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const api = vi.hoisted(() => ({ options: null as unknown, sync: null as unknown, calls: [] as { path: string; method: string; body?: unknown }[], connect: vi.fn() }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { method?: string; body?: unknown } = {}) => {
    const method = opts.method ?? "GET";
    api.calls.push({ path, method, body: opts.body });
    if (path === "/calendar/sync") return api.sync;
    if (path === "/calendar/export/options" && api.options) return api.options;
    if (path.endsWith("/connect")) return api.connect(path, opts.body);
    if (path === "/me/consents/calendar_sync") return [{ purpose: "calendar_sync", label_tr: "Takvim", label_en: "Calendar", granted: true }];
    if (path === "/calendar/connectors/google/calendars") return [{ id: "primary", name: "ayse@uni.edu.tr", primary: true }, { id: "c2", name: "Dersler" }];
    if (method === "DELETE") return undefined;
    if (path.endsWith("/resync")) return { queued: 12 };
    if (method === "PUT") return { provider: "google", label: "Google Calendar", configured: true, connected: true };
    throw new Error(`unexpected ${method} ${path}`);
  },
}));

import { translate } from "@/lib/i18n";
import { CalendarConnectionsSection, connectErrorText, connectResult } from "./calendar-connections";

const google = { provider: "google", label: "Google Calendar", configured: true, connected: false };
const microsoft = { provider: "microsoft", label: "Microsoft 365", configured: false, connected: false };
const sync = (connectors: unknown[], enabled = true) => ({ enabled, feeds: { tokens: [], url_templates: { mine: "", room: "", department: "" } }, connectors });

function renderSection(locale: "en" | "tr" = "en") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>
        <CalendarConnectionsSection />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

const assign = vi.fn();
beforeEach(() => {
  api.calls = [];
  api.options = null;
  api.connect.mockReset();
  nav.params = new URLSearchParams();
  nav.replace.mockReset();
  toast.success.mockReset();
  toast.error.mockReset();
  Object.defineProperty(window, "location", { configurable: true, value: { ...window.location, assign } });
  assign.mockReset();
});
afterEach(() => vi.clearAllMocks());

describe("connectResult", () => {
  it("reads the backend's redirect query", () => {
    expect(connectResult(new URLSearchParams("calendar=connected&provider=google"))).toEqual({ ok: true, provider: "google", reason: null });
    expect(connectResult(new URLSearchParams("calendar=error&provider=microsoft&reason=denied"))).toEqual({ ok: false, provider: "microsoft", reason: "denied" });
    expect(connectResult(new URLSearchParams("tab=x"))).toBeNull();
  });
});

describe("CalendarConnectionsSection", () => {
  it("says sync is off and offers nothing while the KVKK switch is off", async () => {
    api.sync = sync([google, microsoft], false);
    renderSection();
    expect(await screen.findByTestId("calendar-connections-off")).toHaveTextContent("turned off");
    expect(screen.queryByTestId("calendar-connect-google")).toBeNull();
  });

  it("offers Connect only for a configured provider and sends the browser to the backend's authorize URL", async () => {
    const user = userEvent.setup();
    api.sync = sync([google, microsoft]);
    const url = "https://accounts.google.com/o/oauth2/v2/auth?client_id=1234-abc.apps.googleusercontent.com&redirect_uri=https%3A%2F%2Frezervasyon.uni.edu.tr%2Fapi%2Fv1%2Fcalendar%2Fconnectors%2Fgoogle%2Fcallback&response_type=code&code_challenge_method=S256&code_challenge=x&state=y";
    api.connect.mockResolvedValue({ authorize_url: url });
    renderSection();
    const ms = await screen.findByTestId("calendar-connection-microsoft");
    expect(ms).toHaveAttribute("data-state", "not-configured");
    expect(within(ms).queryByRole("button")).toBeNull();
    await user.click(screen.getByTestId("calendar-connect-google"));
    await waitFor(() => expect(assign).toHaveBeenCalledWith(url));
    expect(api.connect).toHaveBeenCalledWith("/calendar/connectors/google/connect", { return_path: "/profile", scopes: ["my_bookings"] });
  });

  it("shows the backend's refusal with a link to Privacy when consent is missing", async () => {
    const user = userEvent.setup();
    api.sync = sync([google]);
    api.connect.mockRejectedValue(new HttpError(409, "consent", { detail: { code: "consent_required", message: "Give the calendar sync consent first", message_tr: "Önce takvim eşitleme iznini verin" } }));
    renderSection("tr");
    await user.click(await screen.findByTestId("calendar-connect-google"));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Önce takvim eşitleme iznini verin");
    expect(within(alert).getByRole("link", { name: "Gizlilik bölümüne git" })).toHaveAttribute("href", "/profile#privacy");
    expect(assign).not.toHaveBeenCalled();
  });

  it("lists the account, lets the user pick a calendar, push again and disconnect", async () => {
    const user = userEvent.setup();
    api.sync = sync([{ ...google, connected: true, status: "ACTIVE", account_email: "ayse@uni.edu.tr", calendar_id: "primary", last_synced_at: "2026-02-16T08:00:00", pending_jobs: 2, failed_jobs: 0 }]);
    renderSection();
    const row = await screen.findByTestId("calendar-connection-google");
    expect(row).toHaveAttribute("data-state", "connected");
    expect(row).toHaveTextContent("Connected as ayse@uni.edu.tr");
    expect(screen.getByTestId("calendar-sync-state-google")).toHaveTextContent("2 pending");
    await user.selectOptions(await screen.findByTestId("calendar-choose-google"), "c2");
    await waitFor(() => expect(api.calls).toContainEqual({ path: "/calendar/connectors/google", method: "PUT", body: { calendar_id: "c2", calendar_name: "Dersler" } }));
    await user.click(screen.getByRole("button", { name: /Push everything again/ }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("12 bookings queued"));
    await user.click(screen.getByTestId("calendar-disconnect-google"));
    await user.click(await screen.findByRole("button", { name: "Disconnect" }));
    await waitFor(() => expect(api.calls.some((c) => c.method === "DELETE" && c.path === "/calendar/connectors/google")).toBe(true));
  });

  it("asks for the calendar_sync consent in an inline step before Connect, gives it, then connects", async () => {
    const user = userEvent.setup();
    api.sync = { ...sync([google]), consent: { purpose: "calendar_sync", required: true, granted: false } };
    api.connect.mockResolvedValue({ authorize_url: "https://login.example/authorize" });
    renderSection();
    const notice = await screen.findByTestId("calendar-connections-consent");
    expect(notice).toHaveTextContent("asks for your calendar sync consent first");
    expect(within(notice).getByRole("link", { name: "Go to Privacy" })).toHaveAttribute("href", "/profile#privacy");
    await user.click(screen.getByTestId("calendar-connect-google"));
    const step = await screen.findByTestId("calendar-consent-google");
    expect(step).toHaveTextContent("Calendar sync needs your consent");
    expect(api.connect).not.toHaveBeenCalled();
    await user.click(within(step).getByTestId("calendar-consent-grant"));
    await waitFor(() => expect(assign).toHaveBeenCalledWith("https://login.example/authorize"));
    const order = api.calls.filter((c) => c.method === "POST").map((c) => c.path);
    expect(order).toEqual(["/me/consents/calendar_sync", "/calendar/connectors/google/connect"]);
  });

  it("asks to reconnect when the provider revoked the grant", async () => {
    api.sync = sync([{ ...google, connected: true, status: "REAUTH", account_email: "ayse@uni.edu.tr" }]);
    renderSection();
    expect(await screen.findByTestId("calendar-connect-google")).toHaveTextContent("Reconnect");
    expect(screen.getByTestId("calendar-connection-google")).toHaveAttribute("data-state", "reauth");
  });

  it("reads the redirect result once and clears it from the address bar", async () => {
    nav.params = new URLSearchParams("calendar=error&provider=google&reason=denied");
    api.sync = sync([google]);
    renderSection();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Could not connect: access was not granted"));
    expect(nav.replace).toHaveBeenCalledWith("/profile", { scroll: false });
  });

  it("says which account to use when the provider's account is not the institution's verified one (CAL-07)", async () => {
    nav.params = new URLSearchParams("calendar=error&provider=google&reason=account_not_verified&domain=uni.edu.tr");
    api.sync = sync([google]);
    renderSection("tr");
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Bu hesap kurumunuzun doğrulanmış hesabı değil. uni.edu.tr uzantılı hesabınızla bağlanın."));
  });

  it("is the older panel, closed under Gelişmiş, once the new export options answer", async () => {
    api.options = { enabled: true, scopes: [], channels: { link: true, file: true, push: [] } };
    api.sync = sync([google]);
    renderSection("tr");
    const adv = await screen.findByTestId("calendar-connections-advanced");
    expect(adv).not.toHaveAttribute("open");
    expect(within(adv).getByTestId("calendar-connections-advanced-toggle")).toHaveTextContent("Gelişmiş");
    expect(await within(adv).findByTestId("calendar-connect-google")).toBeInTheDocument();
    expect(screen.getByTestId("calendar-connections")).toHaveTextContent("Takvimime ekle");
  });
});

describe("connectErrorText", () => {
  const t = (k: Parameters<typeof translate>[1], v?: Record<string, string | number>) => translate("tr", k, v);
  it("never shows a code: known reasons in words, the refused account with its domain or 'kurumsal'", () => {
    expect(connectErrorText(new URLSearchParams("calendar=error&reason=account_not_verified&domain=uni.edu.tr"), t)).toBe("Bu hesap kurumunuzun doğrulanmış hesabı değil. uni.edu.tr uzantılı hesabınızla bağlanın.");
    expect(connectErrorText(new URLSearchParams("calendar=error&reason=account_not_verified&domain="), t)).toBe("Bu hesap kurumunuzun doğrulanmış hesabı değil. Kurumsal hesabınızla bağlanın.");
    expect(connectErrorText(new URLSearchParams("calendar=error&reason=denied"), t)).toBe("Bağlanılamadı: izin verilmedi");
    expect(connectErrorText(new URLSearchParams("calendar=error&reason=weird_code"), t)).not.toMatch(/weird_code/);
  });
});
