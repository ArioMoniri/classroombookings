// AUX-06 / AUX-07 (docs/design/v3/auth.md §6): Profil › Giriş ve güvenlik — the rows, the SSO explanation, the 2FA
// setup in ≤ 3 steps with the codes and "Bitir" behind the tick, the 10-minute re-authentication, the sessions block
// (AU-15: no network shown, "Oturumu kapat", "Diğer cihazlardan çıkış yap") and the recovery-code file.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { forgetReauth, rememberedPassword } from "./reauth-dialog";
import { codesFileName, codesFileText } from "./recovery-codes";
import { SecuritySection } from "./security-section";
import { orderSessions } from "./sessions-list";
import { groupKey } from "./totp-setup";

const toasts = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }));
vi.mock("sonner", () => ({ toast: toasts }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }) }));
vi.mock("qrcode", () => ({ default: { toDataURL: async () => "data:image/png;base64,AAAA" } }));

const realMatchMedia = window.matchMedia;
afterAll(() => {
  window.matchMedia = realMatchMedia;
});
beforeAll(() => {
  // a 1440 px desktop: steps 1–2 side by side, the QR shown, the key behind the disclosure
  window.matchMedia = ((q: string) => ({ matches: q.includes("min-width: 1024px") || q.includes("reduce"), media: q, addEventListener: () => undefined, removeEventListener: () => undefined, addListener: () => undefined, removeListener: () => undefined })) as unknown as typeof window.matchMedia;
  if (!document.elementFromPoint) Object.defineProperty(document, "elementFromPoint", { value: () => null, configurable: true });
});

const STATUS = {
  available: true,
  reason: null,
  account_type: "local",
  policy: { mfa_policy: "optional", mfa_roles: ["ADMIN"], mfa_grace_days: 14, passkeys_enabled: true, passkey_first_factor: false, trusted_device_days: 30 },
  passkeys_available: true,
  required: false,
  grace_until: null,
  totp: { enabled: false, enabled_at: null },
  recovery_codes: { remaining: 0, total: 10 },
  passkeys: [],
  trusted_devices: [],
  locked_until: null,
  password_min_length: 12,
};
const SESSIONS = [
  { id: 2, created_at: "2026-10-17T08:00:00", last_seen_at: "2026-10-17T09:00:00", expires_at: "2026-10-18T08:00:00", device: "Safari, iPhone", network: "212.156.4.0/24", current: false },
  { id: 1, created_at: "2026-10-18T08:00:00", last_seen_at: "2026-10-18T09:00:00", expires_at: "2026-10-19T08:00:00", device: "Chrome, macOS", network: "88.1.2.0/24", current: true },
];
const START = { secret: "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP", otpauth_uri: "otpauth://totp/SmartSched:fatih?secret=JBSWY3DPEHPK3PXP", issuer: "Örnek Üniversitesi", account: "fatih", digits: 6, period: 30, algorithm: "SHA1", expires_in: 900 };
const CODES = Array.from({ length: 10 }, (_, i) => `AAAA-BBBB-CCCC-00${String(i).padStart(2, "0")}`);

type Route = (body: unknown) => Response | Promise<Response>;
const res = (status: number, body?: unknown) => new Response(body === undefined ? null : JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
let routes: Record<string, Route>;
let calls: { key: string; body: unknown }[];

beforeEach(() => {
  forgetReauth();
  calls = [];
  Object.values(toasts).forEach((f) => f.mockReset());
  routes = {
    "GET /api/v1/auth/mfa": () => res(200, STATUS),
    "GET /api/v1/org/public": () => res(200, { name: "Örnek Üniversitesi" }),
    "GET /api/v1/auth/sessions": () => res(200, SESSIONS),
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      const key = `${init?.method ?? "GET"} ${String(url).split("?")[0]}`;
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      calls.push({ key, body });
      const r = routes[key];
      return r ? r(body) : res(404, { detail: "not found" });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const wrap = () =>
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <I18nProvider initialLocale="tr">
        <SecuritySection />
      </I18nProvider>
    </QueryClientProvider>,
  );

describe("SecuritySection", () => {
  it("local account: five subjects, one primary ('Aç'), sessions without any network", async () => {
    wrap();
    await screen.findByTestId("security-mfa");
    for (const id of ["security-password", "security-mfa", "security-passkeys", "security-sessions", "security-history"]) expect(screen.getByTestId(id)).toBeInTheDocument();
    expect(screen.getByTestId("mfa-turn-on")).toHaveTextContent("Aç");
    const rows = await screen.findAllByTestId("session-row");
    // the current one first, tagged; no "Oturumu kapat" on it
    expect(rows[0]).toHaveTextContent("Chrome, macOS");
    expect(within(rows[0]!).getByTestId("session-current")).toHaveTextContent("Bu cihaz");
    expect(within(rows[0]!).queryByTestId("session-end")).toBeNull();
    expect(within(rows[1]!).getByTestId("session-end")).toHaveTextContent("Oturumu kapat");
    expect(screen.getByTestId("security-section").textContent).not.toMatch(/212\.156|88\.1\.2|\/24/);
    expect(screen.getByTestId("session-list").tagName).toBe("UL");
  });

  it("SSO account: the explanation row replaces Parola, 2FA and passkeys; sessions and history stay", async () => {
    routes["GET /api/v1/auth/mfa"] = () => res(200, { ...STATUS, available: false, reason: "sso_account", account_type: "sso" });
    wrap();
    expect(await screen.findByTestId("security-sso")).toHaveTextContent("kurum hesabınızla");
    expect(screen.queryByTestId("security-mfa")).toBeNull();
    expect(screen.queryByTestId("security-passkeys")).toBeNull();
    expect(screen.queryByTestId("security-password")).toBeNull();
    expect(screen.getByTestId("security-sessions")).toBeInTheDocument();
    expect(screen.getByTestId("security-history")).toBeInTheDocument();
  });

  it("turning 2FA on: re-auth once, key behind 'QR kodunu tarayamıyor musunuz?', code → codes; Bitir after the tick", async () => {
    let starts = 0;
    routes["POST /api/v1/auth/mfa/totp/start"] = (b) => {
      starts += 1;
      return (b as { password: string }).password === "doğru-parola" ? res(200, START) : res(403, { detail: { code: "reauth_failed" } });
    };
    routes["POST /api/v1/auth/mfa/totp/confirm"] = () => res(200, { enabled: true, recovery_codes: CODES });
    wrap();
    fireEvent.click(await screen.findByTestId("mfa-turn-on"));
    // older than 10 minutes: the dialog asks for the password
    const pw = await screen.findByTestId("reauth-password");
    fireEvent.change(pw, { target: { value: "doğru-parola" } });
    fireEvent.click(screen.getByTestId("reauth-submit"));
    const sheet = await screen.findByTestId("mfa-setup-sheet");
    expect(within(sheet).getByTestId("mfa-setup-step")).toHaveTextContent("Adım 1–2 / 3");
    expect(await within(sheet).findByTestId("setup-qr")).toBeInTheDocument();
    expect(within(sheet).queryByTestId("setup-key")).toBeNull();
    fireEvent.click(within(sheet).getByTestId("setup-cant-scan"));
    expect(within(sheet).getByTestId("setup-key")).toHaveTextContent("JBSW Y3DP EHPK 3PXP JBSW Y3DP EHPK 3PXP");
    // the sheet used the re-authenticated answer: no second start
    expect(starts).toBe(2);
    const otp = within(sheet).getByRole("textbox", { name: "Doğrulama kodu" });
    fireEvent.paste(otp, { clipboardData: { getData: () => "123 456" } });
    expect(await within(sheet).findByTestId("setup-step-3")).toBeInTheDocument();
    expect(within(sheet).getByTestId("mfa-setup-step")).toHaveTextContent("Adım 3 / 3");
    expect(within(sheet).getAllByRole("listitem")).toHaveLength(10);
    const finish = within(sheet).getByTestId("codes-finish");
    expect(finish).toBeDisabled();
    fireEvent.click(within(sheet).getByTestId("codes-saved"));
    expect(finish).toBeEnabled();
    expect(calls.find((c) => c.key === "POST /api/v1/auth/mfa/totp/confirm")?.body).toEqual({ code: "123456" });
    // the password is kept in memory for the 10-minute window
    expect(rememberedPassword()).toBe("doğru-parola");
    expect(rememberedPassword(Date.now() + 11 * 60_000)).toBeUndefined();
  });

  it("closing at step 3 without the tick asks first", async () => {
    forgetReauth();
    routes["POST /api/v1/auth/mfa/totp/start"] = () => res(200, START);
    routes["POST /api/v1/auth/mfa/totp/confirm"] = () => res(200, { enabled: true, recovery_codes: CODES });
    wrap();
    fireEvent.click(await screen.findByTestId("mfa-turn-on"));
    const sheet = await screen.findByTestId("mfa-setup-sheet");
    fireEvent.paste(await within(sheet).findByRole("textbox", { name: "Doğrulama kodu" }), { clipboardData: { getData: () => "654321" } });
    await within(sheet).findByTestId("setup-step-3");
    fireEvent.keyDown(sheet, { key: "Escape" });
    expect(await screen.findByTestId("mfa-setup-close-confirm")).toHaveTextContent("Kodları kaydetmeden kapatılsın mı?");
  });

  it("'Oturumu kapat' ends one session; 'Diğer cihazlardan çıkış yap' confirms and revokes the others", async () => {
    routes["DELETE /api/v1/auth/sessions/2"] = () => new Response(null, { status: 204 });
    routes["POST /api/v1/auth/sessions/revoke-others"] = () => res(200, { revoked: 1 });
    wrap();
    const rows = await screen.findAllByTestId("session-row");
    fireEvent.click(within(rows[1]!).getByTestId("session-end"));
    await waitFor(() => expect(calls.some((c) => c.key === "DELETE /api/v1/auth/sessions/2")).toBe(true));
    fireEvent.click(screen.getByTestId("sessions-end-others"));
    expect(await screen.findByTestId("sessions-end-others-dialog")).toHaveTextContent("Bu cihaz dışındaki tüm oturumlar kapatılır");
    fireEvent.click(screen.getByTestId("sessions-end-others-confirm"));
    await waitFor(() => expect(calls.some((c) => c.key === "POST /api/v1/auth/sessions/revoke-others")).toBe(true));
    await waitFor(() => expect(toasts.success).toHaveBeenCalledWith("Diğer oturumlar kapatıldı (1)."));
  });
});

describe("Uygulamayı değiştir (AU-18)", () => {
  const ON = { ...STATUS, totp: { enabled: true, enabled_at: "2026-10-01T09:00:00", change_pending: false }, recovery_codes: { remaining: 8, total: 10 } };

  it("starts with replacing: true, says the old app keeps working, and ends without step 3 or new codes", async () => {
    routes["GET /api/v1/auth/mfa"] = () => res(200, ON);
    routes["POST /api/v1/auth/mfa/totp/start"] = () => res(200, { ...START, replacing: true });
    routes["POST /api/v1/auth/mfa/totp/confirm"] = () => res(200, { enabled: true, changed: true, recovery_codes: [] });
    wrap();
    fireEvent.click(await screen.findByTestId("mfa-manage"));
    fireEvent.click(await screen.findByTestId("mfa-change-app"));
    const sheet = await screen.findByTestId("mfa-setup-sheet");
    expect(sheet).toHaveTextContent("Doğrulama uygulamasını değiştirin");
    expect(within(sheet).getByTestId("mfa-setup-step")).toHaveTextContent("Adım 1–2 / 2");
    expect(await within(sheet).findByTestId("setup-replacing")).toHaveTextContent("Eski uygulamanız, yenisinin kodu doğrulanana kadar çalışmaya devam eder");
    fireEvent.paste(within(sheet).getByRole("textbox", { name: "Doğrulama kodu" }), { clipboardData: { getData: () => "222333" } });
    await waitFor(() => expect(toasts.success).toHaveBeenCalledWith("Doğrulama uygulaması değiştirildi. Kurtarma kodlarınız ve hatırlanan cihazlarınız değişmedi."));
    expect(screen.queryByTestId("setup-step-3")).toBeNull();
    expect(screen.queryByTestId("recovery-codes")).toBeNull();
  });

  it("a code of the old app is refused with the 'new app' sentence; a pending change shows its note", async () => {
    routes["GET /api/v1/auth/mfa"] = () => res(200, { ...ON, totp: { ...ON.totp, change_pending: true } });
    routes["POST /api/v1/auth/mfa/totp/start"] = () => res(200, { ...START, replacing: true });
    routes["POST /api/v1/auth/mfa/totp/confirm"] = () => res(422, { detail: { code: "invalid_code" } });
    wrap();
    expect(await screen.findByTestId("mfa-change-pending")).toHaveTextContent("Yeni bir uygulama bağlanmayı bekliyor");
    fireEvent.click(screen.getByTestId("mfa-manage"));
    fireEvent.click(await screen.findByTestId("mfa-change-app"));
    const sheet = await screen.findByTestId("mfa-setup-sheet");
    await within(sheet).findByTestId("setup-replacing");
    fireEvent.paste(within(sheet).getByRole("textbox", { name: "Doğrulama kodu" }), { clipboardData: { getData: () => "111111" } });
    expect(await within(sheet).findByText("Kod doğru değil. Yeni uygulamanın gösterdiği güncel kodu girin.")).toBeInTheDocument();
  });
});

describe("helpers", () => {
  it("orders the current session first, then by last activity", () => {
    expect(orderSessions(SESSIONS).map((s) => s.id)).toEqual([1, 2]);
  });
  it("groups the key by 4 and names the .txt after the org", () => {
    expect(groupKey("ABCDEFGHIJKL")).toBe("ABCD EFGH IJKL");
    expect(codesFileName("Örnek Üniversitesi", "tr")).toBe("smartsched-kurtarma-kodlari-ornek-universitesi.txt");
    expect(codesFileName(null, "en")).toBe("smartsched-recovery-codes-smartsched.txt");
    const txt = codesFileText(CODES.slice(0, 2), { header: "SmartSched kurtarma kodları", org: "Örnek", accountLabel: "Hesap", account: "fatih", dateLabel: "Tarih", date: "18 Ekim 2026", note: "Her kod bir kez kullanılır." });
    expect(txt.split("\n")).toEqual(["SmartSched kurtarma kodları — Örnek", "Hesap: fatih", "Tarih: 18 Ekim 2026", "", ` 1. ${CODES[0]}`, ` 2. ${CODES[1]}`, "", "Her kod bir kez kullanılır.", ""]);
  });
});
