/**
 * Flow-loop round 1, lane A, T-R1-09 (R1-A-27, R1-M-28, R1-A-28, R1-A-29, R1-M-21): the login form's field
 * messages, focus after a refusal, inputmode, the per-identifier lock, the SSO-off notice and the landing page.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { OrgPublicAuth } from "@/lib/api/identity";
import { I18nProvider } from "@/lib/i18n/provider";
import { SignInPage } from "./sign-in-page";
import { homeFor, normalizeSsoError, readSignInParams } from "./signin-model";

const nav = vi.hoisted(() => ({ replace: vi.fn(), refresh: vi.fn(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => nav, useSearchParams: () => new URLSearchParams() }));
vi.mock("@/lib/api/crbs", () => ({ useAppVersion: () => ({ data: "1.4.0" }), crbs: { org: { i18n: () => Promise.reject(new Error("x")) } } }));
vi.mock("@/components/bookings/use-booking-format", () => ({ applySessionLanguage: vi.fn() }));

function org(ms = false): OrgPublicAuth {
  return {
    name: "Örnek Üniversitesi",
    logo_url: null,
    login_message: null,
    maintenance_mode: false,
    maintenance_message: null,
    ldap_enabled: false,
    setup_required: false,
    default_language: "tr",
    languages: ["tr", "en"],
    auth: { microsoft: { enabled: ms, label: "Microsoft", start_url: "/api/v1/auth/sso/entra/start", domain_hint: null, self_signup: false }, local_enabled: true, ldap_enabled: false, self_signup_role_name: null },
  };
}

function view(query = "", o = org()) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale="tr">
        <SignInPage org={o} params={readSignInParams(new URLSearchParams(query))} invite={null} lastMethodLocal={false} />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

const submit = () => act(async () => void fireEvent.submit(screen.getByTestId("login-form")));
const type = (id: string, value: string) => fireEvent.change(screen.getByTestId(id), { target: { value } });

describe("local sign-in form (T-R1-09)", () => {
  beforeEach(() => nav.replace.mockReset());
  afterEach(() => vi.restoreAllMocks());

  it("an empty submit writes a message under each field, linked by aria-describedby, marks both invalid and shows no alert", async () => {
    view();
    await submit();
    const id = screen.getByTestId("login-identifier");
    const pw = screen.getByTestId("login-password");
    const idMsg = screen.getByTestId("login-identifier-required");
    const pwMsg = screen.getByTestId("login-password-required");
    expect(idMsg).toHaveTextContent("Kullanıcı adı veya e-posta gerekli");
    expect(pwMsg).toHaveTextContent("Parola gerekli");
    expect(id).toHaveAttribute("aria-invalid", "true");
    expect(pw).toHaveAttribute("aria-invalid", "true");
    expect(id.getAttribute("aria-describedby")).toBe(idMsg.id);
    expect(pw.getAttribute("aria-describedby")).toBe(pwMsg.id);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(document.activeElement).toBe(id);
    // the identifier takes the e-mail keyboard on phones
    expect(id).toHaveAttribute("inputmode", "email");
    // typing clears the field's own message
    type("login-identifier", "ayilmaz");
    expect(screen.queryByTestId("login-identifier-required")).toBeNull();
    expect(screen.getByTestId("login-password-required")).toBeInTheDocument();
    await submit();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(document.activeElement).toBe(pw);
  });

  it("a refused login moves focus to the alert, not back to 'Giriş yap'", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("{}", { status: 401, headers: { "content-type": "application/json" } }));
    view();
    type("login-identifier", "ayilmaz");
    type("login-password", "wrong");
    screen.getByTestId("login-submit").focus();
    await submit();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Kullanıcı adı, e-posta veya parola yanlış."));
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId("login-error")));
  });

  it("the 429 lock belongs to the identifier: another account's 'Giriş yap' stays enabled", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(new Response("{}", { status: 429, headers: { "retry-after": "180" } }));
    view();
    type("login-identifier", "ds.test");
    type("login-password", "x");
    await submit();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("3 dakika sonra"));
    expect(screen.getByTestId("login-submit")).toBeDisabled();
    type("login-identifier", "personel.test");
    expect(screen.getByTestId("login-submit")).toBeEnabled();
    expect(screen.queryByRole("alert")).toBeNull();
    // back to the locked identifier (case and spaces do not matter): locked again, with the countdown
    type("login-identifier", " DS.TEST ");
    expect(screen.getByTestId("login-submit")).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("3 dakika sonra");
  });

  it("lands on the first page the permissions allow", () => {
    expect(homeFor(["planning.view", "book_single.create"])).toBe("/dashboard");
    expect(homeFor(["book_single.create", "room.view"])).toBe("/bookings");
    expect(homeFor(["approvals.decide", "room.view"])).toBe("/approvals");
    // F-11 S04: a user administrator without planning or booking rights
    expect(homeFor(["setup.users", "setup.roles", "room.view"])).toBe("/admin/users");
    expect(homeFor(["setup.roles"])).toBe("/admin/roles");
    expect(homeFor(["setup.settings"])).toBe("/admin/settings");
    expect(homeFor(["room.view"])).toBe("/bookings");
    expect(homeFor([])).toBe("/profile");
    expect(homeFor(undefined)).toBe("/dashboard");
  });
});

describe("Microsoft sign-in switched off (T-R1-35 → T-R1-09)", () => {
  it("not_enabled is a code of its own and reads as a state without a support code", () => {
    expect(normalizeSsoError("not_enabled")).toBe("not_enabled");
    view("error=not_enabled&ref=S-1");
    const notice = screen.getByTestId("signin-notice-not_enabled");
    expect(notice).toHaveTextContent("Microsoft ile giriş bu kurumda henüz açık değil.");
    expect(notice.textContent).not.toMatch(/S-1|kod/);
    expect(screen.queryByTestId("signin-error-not_enabled")).toBeNull();
    expect(screen.queryByTestId("signin-error-failed")).toBeNull();
    // the password form is open (Microsoft is off)
    expect(screen.getByTestId("login-identifier")).toBeInTheDocument();
  });
});
