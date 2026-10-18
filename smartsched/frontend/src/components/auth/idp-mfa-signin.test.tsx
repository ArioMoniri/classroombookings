// AU-16 (AU-B API.md §12): /login shows the Turkish `idp_mfa_required` refusal; the exchange's one-time
// `idp_mfa_missing` becomes a lasting warning toast with the server's sentence.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { translate } from "@/lib/i18n";
import { errorBody } from "./sign-in-page";
import { normalizeSsoError } from "./signin-model";
import { SignInShell } from "./signin-shell";
import { SsoExchange } from "./sso-exchange";

const nav = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }));
const toasts = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav, useSearchParams: () => new URLSearchParams("ticket=abcdefghijklmnopqrstuvwxyz") }));
vi.mock("@/lib/api/crbs", () => ({ useAppVersion: () => ({ data: "1.4.0" }), crbs: { org: { i18n: () => Promise.reject(new Error("x")) } } }));
vi.mock("@/components/bookings/use-booking-format", () => ({ applySessionLanguage: vi.fn() }));
vi.mock("sonner", () => ({ toast: toasts }));

const res = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
beforeEach(() => {
  Object.values(nav).forEach((f) => f.mockReset());
  Object.values(toasts).forEach((f) => f.mockReset());
});
afterEach(() => vi.unstubAllGlobals());

describe("idp_mfa_required on /login", () => {
  it("is a known code with its own Turkish sentence (not the generic 'failed')", () => {
    expect(normalizeSsoError("idp_mfa_required")).toBe("idp_mfa_required");
    const t = (k: Parameters<typeof translate>[1], v?: Record<string, string | number>) => translate("tr", k, v);
    const body = errorBody("idp_mfa_required", t as never, { org: null, ref: null, invited: null, signedIn: null });
    expect(body.title).toBe("İki aşamalı doğrulama gerekiyor.");
    expect(body.text).toMatch(/^Kurumunuz bu rol için iki aşamalı doğrulama istiyor\. Kimlik sağlayıcınızda çok adımlı doğrulamayı açıp/);
  });
});

describe("idp_mfa_missing after the exchange", () => {
  it("shows the server's Turkish sentence once as a warning, then goes on", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => res(200, { user: { id: 3, full_name: "Ayşe Yılmaz", permissions: ["planning.view"] }, next: "/my-bookings", idp_mfa_missing: true, idp_mfa_message_tr: "Kimlik sağlayıcınızda çok adımlı doğrulamayı açın.", idp_mfa_message_en: "Turn on MFA." })),
    );
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">
          <SsoExchange logoUrl={null} kvkkUrl={null} />
        </I18nProvider>
      </QueryClientProvider>,
    );
    await waitFor(() => expect(nav.replace).toHaveBeenCalledWith("/my-bookings"));
    expect(toasts.warning).toHaveBeenCalledTimes(1);
    expect(toasts.warning).toHaveBeenCalledWith("Kimlik sağlayıcınız çok adımlı doğrulama bildirmedi.", expect.objectContaining({ description: "Kimlik sağlayıcınızda çok adımlı doğrulamayı açın.", id: "idp-mfa-missing" }));
  });
});

describe("sign-in sheet side padding (mobile A: landscape safe areas)", () => {
  it("every side padding is max(padding, safe-area inset), so the insets win in landscape", () => {
    const { getByTestId } = render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">
          <SignInShell logoUrl={null} kvkkUrl={null} testId="shell">
            <h1 id="signin-title">x</h1>
          </SignInShell>
        </I18nProvider>
      </QueryClientProvider>,
    );
    const cls = getByTestId("signin-sheet").className;
    for (const bp of ["max-[599px]:", "min-[600px]:", "lg:"]) {
      expect(cls).toContain(`${bp}pl-[max(`);
      expect(cls).toContain(`${bp}pr-[max(`);
    }
    expect(cls).not.toMatch(/(^|\s)(min-\[600px\]:|lg:|max-\[599px\]:)px-/);
    expect(cls.match(/env\(safe-area-inset-(left|right)\)/g)).toHaveLength(6);
  });
});
