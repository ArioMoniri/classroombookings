import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { LoginForm } from "./login-form";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }), useSearchParams: () => new URLSearchParams() }));
const org = vi.hoisted(() => ({ data: undefined as Record<string, unknown> | undefined }));
vi.mock("@/lib/api/crbs", () => ({ useOrgPublic: () => ({ data: org.data }) }));

function renderForm(locale: "tr" | "en" = "en") {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <I18nProvider initialLocale={locale}>
        <LoginForm />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("LoginForm", () => {
  beforeEach(() => {
    org.data = { name: "Acıbadem Üniversitesi", logo_url: "/api/v1/org/logo", login_message: "Use your staff account.", maintenance_mode: true, maintenance_message: "Bookings pause tonight.", setup_required: false };
  });

  it("starts empty: no demo address, no demo hint", () => {
    renderForm();
    expect(screen.getByTestId("login-identifier")).toHaveValue("");
    expect(screen.getByTestId("login-password")).toHaveValue("");
    expect(document.body.textContent).not.toMatch(/demo|admin"|example\.edu/i);
  });

  it("renders the organisation brand, login message, maintenance banner and the forgot-password link", () => {
    renderForm();
    expect(screen.getByTestId("login-brand")).toHaveTextContent("Acıbadem Üniversitesi");
    expect(screen.getByTestId("login-message")).toHaveTextContent("Use your staff account.");
    expect(screen.getByTestId("login-maintenance")).toHaveTextContent("Bookings pause tonight.");
    expect(screen.getByTestId("forgot-password")).toHaveAttribute("href", "/reset-password");
  });

  it("hides the notices the organisation has not set", () => {
    org.data = { name: null, logo_url: null, login_message: null, maintenance_mode: false, setup_required: false };
    renderForm();
    expect(screen.queryByTestId("login-brand")).toBeNull();
    expect(screen.queryByTestId("login-message")).toBeNull();
    expect(screen.queryByTestId("login-maintenance")).toBeNull();
    expect(screen.getByTestId("forgot-password")).toBeInTheDocument();
  });

  it.each(["en", "tr"] as const)("labels exactly one field as the password (%s), the toggle names its action", (locale) => {
    renderForm(locale);
    const label = locale === "en" ? "Password" : "Şifre";
    expect(screen.getByLabelText(label, { exact: true })).toBe(screen.getByTestId("login-password"));
    expect(screen.getByRole("button", { name: locale === "en" ? "Show password" : "Şifreyi göster" })).toHaveAttribute("aria-controls", "password");
  });
});
