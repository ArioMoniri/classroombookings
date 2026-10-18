// AUX-05 (docs/design/v3/auth.md §4.5, D12): one field, no repeat field, errors linked, the expired copy, and
// signing in afterwards (the enrolment when the policy requires 2FA).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { passwordProblem, SetPasswordForm } from "./set-password-form";

const nav = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav }));
vi.mock("@/lib/api/crbs", () => ({ crbs: { org: { i18n: () => Promise.reject(new Error("x")) } } }));
vi.mock("@/components/bookings/use-booking-format", () => ({ applySessionLanguage: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), warning: vi.fn() } }));

const resp = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  Object.values(nav).forEach((f) => f.mockReset());
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

const view = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="tr">
        <SetPasswordForm mode="reset" token="abcdefgh1234" username="ayse.yilmaz" org="Örnek Üniversitesi" />
      </I18nProvider>
    </QueryClientProvider>,
  );

describe("SetPasswordForm", () => {
  it("one new-password field (no repeat), a hidden username, the hint and the counter", () => {
    view();
    expect(document.querySelectorAll('input[type="password"]')).toHaveLength(1);
    const field = screen.getByLabelText("Yeni parola");
    expect(field).toHaveAttribute("autocomplete", "new-password");
    expect(field.getAttribute("passwordrules")).toBe("minlength: 12;");
    expect(document.querySelector('input[autocomplete="username"]')).toHaveValue("ayse.yilmaz");
    fireEvent.change(field, { target: { value: "kisa" } });
    expect(screen.getByTestId("set-password-count")).toHaveTextContent("4/12");
    expect(field).toHaveAccessibleDescription(/En az 12 karakter/);
  });

  it("refuses a short or username password client-side, linked by aria-describedby", async () => {
    view();
    const field = screen.getByLabelText("Yeni parola");
    fireEvent.change(field, { target: { value: "kisa" } });
    await act(async () => fireEvent.submit(screen.getByTestId("set-password-form")));
    expect(field).toHaveAttribute("aria-invalid", "true");
    expect(field).toHaveAccessibleDescription(/Parola en az 12 karakter olmalı/);
    expect(passwordProblem("my-ayse.yilmaz-pass", 12, "ayse.yilmaz")).toBe("username");
    expect(passwordProblem("parola123456", 12, null)).toBe("blocklist");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("an expired link shows the expired copy", async () => {
    fetchMock.mockResolvedValueOnce(resp(400, { detail: { code: "invalid_code" } }));
    view();
    fireEvent.change(screen.getByLabelText("Yeni parola"), { target: { value: "uzun bir cümle parola" } });
    await act(async () => fireEvent.submit(screen.getByTestId("set-password-form")));
    expect(await screen.findByTestId("set-password-expired")).toHaveTextContent("süresi dolmuş ya da daha önce kullanılmış");
  });

  it("success signs in; with the policy requiring 2FA it lands on the enrolment notice", async () => {
    fetchMock.mockResolvedValueOnce(resp(200, { status: "setup", setup_methods: ["totp"], ok: true }));
    view();
    fireEvent.change(screen.getByLabelText("Yeni parola"), { target: { value: "uzun bir cümle parola" } });
    await act(async () => fireEvent.submit(screen.getByTestId("set-password-form")));
    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/login/setup-2fa"));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/mfa/reset-confirm");
  });
});
