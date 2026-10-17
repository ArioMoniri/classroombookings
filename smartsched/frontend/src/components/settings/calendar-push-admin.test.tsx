/** Google / Microsoft 365 OAuth client card: write-only secret, "configured" from the backend, the redirect URI to
 * register (built from the panel address), the calendar-sync KVKK state and the request bodies it sends. */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";

const state = vi.hoisted(() => ({ settings: null as unknown, put: vi.fn() }));
vi.mock("@/lib/api/client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api/client")>()),
  request: async (path: string, opts: { method?: string; body?: unknown } = {}) => {
    if (path !== "/calendar/admin/settings") throw new Error(`unexpected ${path}`);
    return opts.method === "PUT" ? state.put(opts.body) : state.settings;
  },
}));

import { CalendarPushAdmin, clientBody, redirectUsable } from "./calendar-push-admin";
import { afKeys } from "@/lib/api/approval-first";

const PANEL = "https://rezervasyon.uni.edu.tr";
const unset = { client_id: "", client_secret: { set: false, masked: "" }, configured: false };
function fresh(publicUrl: string | null = PANEL) {
  const base = publicUrl ?? "";
  return {
    calendar_sync_enabled: false,
    calendar_sync_signoff: null,
    webhooks_enabled: false,
    public_url: base,
    public_url_source: publicUrl ? "setting" : null,
    feed_past_days: 30,
    feed_cancelled_grace_days: 7,
    google: { ...unset, redirect_uri: `${base}/api/v1/calendar/connectors/google/callback` },
    microsoft: { ...unset, redirect_uri: `${base}/api/v1/calendar/connectors/microsoft/callback`, tenant: "organizations" },
  };
}

function renderCard(locale: "en" | "tr" = "en") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nProvider initialLocale={locale}>
        <CalendarPushAdmin />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("clientBody / redirectUsable", () => {
  it("sends only what changed and never a blank secret", () => {
    const stored = { client_id: "abc.apps.googleusercontent.com", client_secret: { set: true, masked: "…f00d" }, configured: true, redirect_uri: "x" };
    expect(clientBody("google", { id: " abc.apps.googleusercontent.com ", secret: "  " }, stored)).toBeNull();
    expect(clientBody("google", { id: "new-id", secret: "" }, stored)).toEqual({ google_client_id: "new-id" });
    expect(clientBody("google", { id: "abc.apps.googleusercontent.com", secret: " s3cret " }, stored)).toEqual({ google_client_secret: "s3cret" });
    expect(clientBody("microsoft", { id: "m", secret: "x", tenant: "" }, { ...stored, client_id: "m", tenant: "contoso.edu.tr" })).toEqual({ microsoft_client_secret: "x", microsoft_tenant: "organizations" });
  });
  it("has a query key the calendar_sync consent withdrawal refreshes (Gizlilik's /calendar|connector/ predicate)", () => {
    expect(afKeys.integrations.some((k) => /calendar|connector/i.test(k))).toBe(true);
  });
  it("treats a redirect URI without a panel address as unusable", () => {
    expect(redirectUsable("/api/v1/calendar/connectors/google/callback")).toBe(false);
    expect(redirectUsable(`${PANEL}/api/v1/calendar/connectors/google/callback`)).toBe(true);
  });
});

describe("CalendarPushAdmin", () => {
  beforeEach(() => {
    state.settings = fresh();
    state.put.mockReset();
    state.put.mockImplementation(async (b: Record<string, string>) => {
      const cur = state.settings as ReturnType<typeof fresh>;
      const next = structuredClone(cur);
      for (const p of ["google", "microsoft"] as const) {
        if (b[`${p}_client_id`] !== undefined) next[p].client_id = b[`${p}_client_id`]!;
        if (b[`${p}_client_secret`] !== undefined) next[p].client_secret = { set: b[`${p}_client_secret`] !== "", masked: b[`${p}_client_secret`] ? `…${b[`${p}_client_secret`]!.slice(-4)}` : "" };
        next[p].configured = !!next[p].client_id && next[p].client_secret.set && !!next.public_url;
      }
      if (b.microsoft_tenant) next.microsoft.tenant = b.microsoft_tenant;
      state.settings = next;
      return next;
    });
  });

  it("shows not configured, the redirect URIs to register and the KVKK state", async () => {
    renderCard();
    expect(await screen.findByTestId("calendar-push-google-state")).toHaveTextContent("Not configured");
    expect(screen.getByTestId("calendar-push-microsoft-state")).toHaveTextContent("Not configured");
    expect(screen.getByTestId("calendar-push-google-redirect")).toHaveValue(`${PANEL}/api/v1/calendar/connectors/google/callback`);
    expect(screen.getByTestId("calendar-push-microsoft-redirect")).toHaveValue(`${PANEL}/api/v1/calendar/connectors/microsoft/callback`);
    expect(screen.getByTestId("calendar-push-kvkk")).toHaveTextContent("users cannot connect until the KVKK sign-off");
    expect(screen.getByTestId("calendar-push-google-secret-hint")).toHaveTextContent("Not entered yet");
  });

  it("asks for the panel address before it offers a redirect URI", async () => {
    state.settings = fresh(null);
    renderCard();
    expect(await screen.findByTestId("calendar-push-google-no-redirect")).toHaveTextContent("Enter the panel's public address first");
    expect(screen.queryByTestId("calendar-push-google-redirect")).toBeNull();
    expect(screen.getByTestId("calendar-push-url-source")).toHaveTextContent("No public address");
  });

  it("saves the client, keeps the secret write-only and turns configured", async () => {
    const user = userEvent.setup();
    renderCard();
    const google = await screen.findByTestId("calendar-push-google");
    await user.click(within(google).getByTestId("calendar-push-google-save"));
    expect(within(google).getByRole("alert")).toHaveTextContent("The client ID is required");
    await user.type(within(google).getByTestId("calendar-push-google-id"), "1234-abc.apps.googleusercontent.com");
    await user.click(within(google).getByTestId("calendar-push-google-save"));
    expect(within(google).getByRole("alert")).toHaveTextContent("needs the client secret");
    await user.type(within(google).getByTestId("calendar-push-google-secret"), "GOCSPX-secret-f00d");
    await user.click(within(google).getByTestId("calendar-push-google-save"));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ google_client_id: "1234-abc.apps.googleusercontent.com", google_client_secret: "GOCSPX-secret-f00d" }));
    expect(await screen.findByTestId("calendar-push-google-state")).toHaveTextContent("Configured");
    // the secret is never read back into the field
    expect(screen.getByTestId("calendar-push-google-secret")).toHaveValue("");
    expect(screen.getByTestId("calendar-push-google-secret-hint")).toHaveTextContent("Stored (…f00d)");
    expect(screen.getByTestId("calendar-push-google-secret")).toHaveAttribute("type", "password");
  });

  it("removes a client with a confirmation", async () => {
    const user = userEvent.setup();
    const s = fresh();
    s.microsoft = { ...s.microsoft, client_id: "11111111-2222", client_secret: { set: true, masked: "…beef" }, configured: true };
    state.settings = s;
    renderCard("tr");
    expect(await screen.findByTestId("calendar-push-microsoft-state")).toHaveTextContent("Yapılandırıldı");
    await user.click(screen.getByTestId("calendar-push-microsoft-remove"));
    await user.click(await screen.findByRole("button", { name: "İstemciyi kaldır" }));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ microsoft_client_id: "", microsoft_client_secret: "" }));
    expect(await screen.findByTestId("calendar-push-microsoft-state")).toHaveTextContent("Yapılandırılmadı");
  });
});

/** CAL-09: the push rules under the public address: verified accounts only + domains, client source, Google scope mode. */
describe("CalendarPushAdmin › push rules (CAL-09)", () => {
  beforeEach(() => {
    state.settings = { ...fresh(), calendar_sync_enabled: true, push_verified_only: true, push_allowed_domains: ["uni.edu.tr"], calendar_client_source: "own", google_scope_mode: "app_created" };
    state.put.mockReset();
    state.put.mockImplementation(async (b: Record<string, unknown>) => {
      state.settings = { ...(state.settings as object), ...b };
      return state.settings;
    });
  });

  it("is absent while the backend has no push rules", async () => {
    state.settings = fresh();
    renderCard();
    await screen.findByTestId("calendar-push-google");
    expect(screen.queryByTestId("cal-admin-push")).toBeNull();
  });

  it("shows verified-only on, the domains, the client source and the recommended Google scope", async () => {
    renderCard();
    expect(await screen.findByTestId("cal-admin-verified")).toHaveAttribute("data-checked");
    expect(screen.getByTestId("cal-admin-domains")).toHaveValue("uni.edu.tr");
    expect(screen.getByTestId("cal-admin-source-own")).toBeChecked();
    expect(screen.getByTestId("cal-admin-gscope-app_created")).toBeChecked();
  });

  it("validates and saves the domains, lower-cased and without @", async () => {
    renderCard();
    const input = await screen.findByTestId("cal-admin-domains");
    await userEvent.clear(input);
    await userEvent.type(input, "Uni.edu.tr, @ogr.uni.edu.tr, not a domain");
    await userEvent.click(screen.getByTestId("cal-admin-domains-save"));
    expect(screen.getByTestId("cal-admin-domains-error")).toHaveTextContent("Not a domain: not");
    expect(state.put).not.toHaveBeenCalled();
    await userEvent.clear(input);
    await userEvent.type(input, "Uni.edu.tr, @ogr.uni.edu.tr");
    await userEvent.click(screen.getByTestId("cal-admin-domains-save"));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ push_allowed_domains: ["uni.edu.tr", "ogr.uni.edu.tr"] }));
  });

  it("switches the Google scope mode and verified-only with their own keys", async () => {
    renderCard();
    await userEvent.click(await screen.findByTestId("cal-admin-gscope-events"));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ google_scope_mode: "events" }));
    await userEvent.click(screen.getByTestId("cal-admin-verified"));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ push_verified_only: false }));
  });

  it("keeps the shared cache shape of the KVKK / push panels after a save", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <I18nProvider initialLocale="tr">
          <CalendarPushAdmin />
        </I18nProvider>
      </QueryClientProvider>,
    );
    await userEvent.click(await screen.findByTestId("cal-admin-source-identity"));
    await waitFor(() => expect(state.put).toHaveBeenCalledWith({ calendar_client_source: "identity" }));
    const cached = qc.getQueryData(afKeys.integrations) as { google?: { client_id: string }; calendar_client_source?: string };
    expect(cached.google?.client_id).toBe("");
    expect(cached.calendar_client_source).toBe("identity");
    expect(screen.getByText("Oturum açma sağlayıcısının istemcisini kullan")).toBeInTheDocument();
  });
});
