// AUX-04 (docs/design/v3/auth.md §5): the second step and the enrolment notice.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { EnrolNotice } from "./enrol-notice";
import { MfaStep } from "./mfa-step";

const nav = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }));
const toasts = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav, useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api/crbs", () => ({ useAppVersion: () => ({ data: "1.4.0" }), crbs: { org: { i18n: () => Promise.reject(new Error("x")) } } }));
vi.mock("@/components/bookings/use-booking-format", () => ({ applySessionLanguage: vi.fn() }));
vi.mock("sonner", () => ({ toast: toasts }));

beforeAll(() => {
  if (!document.elementFromPoint) Object.defineProperty(document, "elementFromPoint", { value: () => null, configurable: true });
  window.matchMedia ??= ((q: string) => ({ matches: q.includes("reduce"), media: q, addEventListener: () => undefined, removeEventListener: () => undefined })) as unknown as typeof window.matchMedia;
});

const resp = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  Object.values(nav).forEach((f) => f.mockReset());
  Object.values(toasts).forEach((f) => f.mockReset());
  fetchMock = vi.fn(async () => resp(200, { status: "none" }));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const wrap = (ui: React.ReactNode) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="tr">{ui}</I18nProvider>
    </QueryClientProvider>,
  );

const paste = (el: HTMLElement, text: string) => fireEvent.paste(el, { clipboardData: { getData: () => text } });
const bodyOf = (i: number) => JSON.parse(String((fetchMock.mock.calls[i] as [string, RequestInit])[1].body));

describe("MfaStep", () => {
  it("focus starts in the code; the remember tick is off; pasting submits once", async () => {
    fetchMock.mockResolvedValueOnce(resp(200, { status: "signed_in", user: { id: 1, permissions: ["planning.view"] } }));
    wrap(<MfaStep methods={["totp", "recovery"]} masked="ay•••@ornek.edu.tr" next={null} rememberDays={30} />);
    const input = screen.getByRole("textbox", { name: "Doğrulama kodu" });
    await waitFor(() => expect(input).toHaveFocus());
    expect(screen.getByTestId("mfa-account")).toHaveTextContent("ay•••@ornek.edu.tr olarak giriş yapılıyor");
    expect(screen.getByRole("checkbox", { name: "Bu cihazı 30 gün hatırla" })).not.toBeChecked();
    paste(input, "123 456");
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/dashboard"));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/mfa/verify");
    expect(bodyOf(0)).toEqual({ method: "totp", code: "123456", trust_device: false, next: null });
  });

  it("a wrong code clears the slots, shows the message and keeps focus; the 2nd adds the clock hint", async () => {
    fetchMock.mockResolvedValue(resp(401, { detail: { code: "invalid_code" } }));
    wrap(<MfaStep methods={["totp"]} masked={null} next={null} rememberDays={30} />);
    const input = screen.getByRole("textbox", { name: "Doğrulama kodu" });
    paste(input, "111111");
    await screen.findByText("Kod doğru değil. Uygulamadaki güncel kodu girin.");
    expect(input).toHaveValue("");
    expect(input).toHaveFocus();
    expect(input).toHaveAttribute("aria-invalid", "true");
    paste(input, "222222");
    await screen.findByText(/saatine bağlıdır/);
  });

  it("5 failures go back to /login with the notice", async () => {
    fetchMock.mockResolvedValue(resp(401, { detail: { code: "invalid_code" } }));
    wrap(<MfaStep methods={["totp"]} masked={null} next={null} rememberDays={30} />);
    const input = screen.getByRole("textbox", { name: "Doğrulama kodu" });
    for (let i = 0; i < 5; i++) {
      paste(input, `${i}${i}${i}${i}${i}${i}`);
      await waitFor(() => expect(fetchMock.mock.calls.filter((c) => String(c[0]).endsWith("/verify")).length).toBe(i + 1));
      await act(async () => undefined);
    }
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/login?method=local&mfa=tooMany"));
  });

  it("the lockout goes back with the minutes", async () => {
    fetchMock.mockResolvedValueOnce(resp(429, { detail: { code: "mfa_locked", retry_after: 900 } }));
    wrap(<MfaStep methods={["totp"]} masked={null} next={null} rememberDays={30} />);
    paste(screen.getByRole("textbox", { name: "Doğrulama kodu" }), "123456");
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/login?method=local&mfa=locked&min=15"));
  });

  it("recovery code: from 'Başka bir yöntem', the remaining-count toast with 'Yeni kodlar oluştur' at ≤ 3; remember sent", async () => {
    fetchMock.mockResolvedValueOnce(resp(200, { status: "signed_in", user: { id: 1, permissions: [] }, recovery_codes_remaining: 2 }));
    wrap(<MfaStep methods={["totp", "recovery"]} masked={null} next="/bookings" rememberDays={30} />);
    fireEvent.click(screen.getByTestId("mfa-other-toggle"));
    fireEvent.click(screen.getByTestId("mfa-use-recovery"));
    const field = screen.getByRole("textbox", { name: "Kurtarma kodu" });
    fireEvent.change(field, { target: { value: "abcd-efgh-jkmn-pqrs" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /hatırla/ }));
    await act(async () => {
      fireEvent.click(screen.getByTestId("mfa-submit"));
    });
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/bookings"));
    expect(bodyOf(0)).toMatchObject({ method: "recovery", code: "ABCD-EFGH-JKMN-PQRS", trust_device: true });
    expect(toasts.warning).toHaveBeenCalledWith("Bir kurtarma kodu kullandınız. 2 kod kaldı.", expect.objectContaining({ action: expect.objectContaining({ label: "Yeni kodlar oluştur" }) }));
  });

  it("a wrong recovery code keeps the field", async () => {
    fetchMock.mockResolvedValueOnce(resp(401, { detail: { code: "invalid_code" } }));
    wrap(<MfaStep methods={["totp", "recovery"]} masked={null} next={null} rememberDays={0} />);
    expect(screen.queryByRole("checkbox")).toBeNull();
    fireEvent.click(screen.getByTestId("mfa-other-toggle"));
    fireEvent.click(screen.getByTestId("mfa-use-recovery"));
    const field = screen.getByRole("textbox", { name: "Kurtarma kodu" });
    fireEvent.change(field, { target: { value: "ABCD-EFGH-JKMN-PQRT" } });
    await act(async () => {
      fireEvent.click(screen.getByTestId("mfa-submit"));
    });
    await screen.findByText("Bu kurtarma kodu geçerli değil ya da daha önce kullanıldı.");
    expect(field).toHaveValue("ABCD-EFGH-JKMN-PQRT");
  });
});

describe("EnrolNotice", () => {
  it("grace: the deadline and 'Daha sonra ({n} gün kaldı)'", () => {
    const until = new Date(Date.now() + 14 * 86_400_000 - 60_000).toISOString();
    wrap(<EnrolNotice mode="grace" graceUntil={until} methods={["totp", "passkey"]} org="Örnek Üniversitesi" next={null} account="ayse" permissions={["planning.view"]} />);
    expect(screen.getByTestId("enrol-deadline")).toHaveTextContent("tarihine kadar süreniz var");
    expect(screen.getByTestId("enrol-later")).toHaveTextContent("Daha sonra (14 gün kaldı)");
    fireEvent.click(screen.getByTestId("enrol-later"));
    expect(nav.replace).toHaveBeenCalledWith("/dashboard");
    expect(screen.getByTestId("enrol-passkey")).toBeInTheDocument();
  });
  it("enforced: no 'Daha sonra', set up now", () => {
    wrap(<EnrolNotice mode="enforced" graceUntil="2026-01-01T00:00:00" methods={["totp"]} org={null} next={null} account="ayse" />);
    expect(screen.queryByTestId("enrol-later")).toBeNull();
    expect(screen.getByTestId("enrol-deadline")).toHaveTextContent("Devam etmek için şimdi kurun.");
    expect(screen.getByTestId("enrol-now")).toHaveTextContent("Şimdi kur");
  });
});
