/**
 * FIX-D / HB18-F02 (security, docs/testing/round4/2026-10-18-hb18.md): a sign-in form with no `method` submits as
 * GET when it is sent before React hydrates, which put `?username=…&password=…` in the address, the history and every
 * proxy log. Every form that holds a credential is `method="post"` with an action that never reads the body
 * (`/api/auth/no-script`), and its submit is disabled in the server HTML (so neither the button nor Enter can submit
 * natively) until the page has hydrated.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ResetPassword } from "@/components/admin/reset-password";
import { I18nProvider } from "@/lib/i18n/provider";
import { ChangePasswordForm } from "./change-password-form";
import { CREDENTIAL_FORM } from "./credential-form";
import { LocalSignInForm } from "./local-sign-in";
import { MfaStep } from "./mfa-step";
import { SetPasswordForm } from "./set-password-form";

const params = vi.hoisted(() => ({ q: new URLSearchParams() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => params.q, usePathname: () => "/login" }));

const wrap = (node: ReactNode) => (
  <QueryClientProvider client={new QueryClient()}>
    <I18nProvider initialLocale="tr">{node}</I18nProvider>
  </QueryClientProvider>
);

/** The server HTML parsed into a detached document (what the browser has before hydration). */
function ssr(node: ReactNode): Document {
  return new DOMParser().parseFromString(renderToString(wrap(node)), "text/html");
}

function expectSafe(doc: Document, label: string) {
  const forms = Array.from(doc.querySelectorAll("form"));
  expect(forms.length, label).toBeGreaterThan(0);
  for (const f of forms) {
    expect(f.getAttribute("method"), label).toBe("post");
    expect(f.getAttribute("action"), label).toBe(CREDENTIAL_FORM.action);
    for (const b of Array.from(f.querySelectorAll('button[type="submit"]'))) expect(b.hasAttribute("disabled"), `${label}: submit enabled before hydration`).toBe(true);
  }
}

describe("credential forms never submit natively as GET (HB18-F02)", () => {
  it("the action is a same-origin endpoint that never reads the body", () => {
    expect(CREDENTIAL_FORM).toEqual({ method: "post", action: "/api/auth/no-script" });
  });

  it("local sign-in: POST, and 'Giriş yap' disabled in the server HTML", () => {
    expectSafe(ssr(<LocalSignInForm next={null} primary resetLink lastMethodLocal={false} />), "login");
  });

  it("local sign-in: 'Giriş yap' is enabled once hydrated", () => {
    render(wrap(<LocalSignInForm next={null} primary resetLink lastMethodLocal={false} />));
    expect(screen.getByTestId("login-form")).toHaveAttribute("method", "post");
    expect(screen.getByTestId("login-submit")).not.toBeDisabled();
  });

  it("second step (MFA): POST, submit disabled before hydration", () => {
    expectSafe(ssr(<MfaStep methods={["totp"]} masked={null} next={null} rememberDays={30} />), "mfa");
  });

  it("set password (reset link / invite): POST, submit disabled before hydration", () => {
    expectSafe(ssr(<SetPasswordForm mode="invite" token="t" username="ayse" />), "set-password");
  });

  it("forced change password: POST, submit disabled before hydration", () => {
    expectSafe(ssr(<ChangePasswordForm />), "change-password");
  });

  it("reset password (request and confirm): POST, submit disabled before hydration", () => {
    params.q = new URLSearchParams();
    expectSafe(ssr(<ResetPassword />), "reset-request");
    params.q = new URLSearchParams("token=abc");
    expectSafe(ssr(<ResetPassword />), "reset-confirm");
    params.q = new URLSearchParams();
  });
});
