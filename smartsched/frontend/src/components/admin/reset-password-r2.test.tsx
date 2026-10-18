// Flow-loop round 2, lane A (T-R2-06, R2-A-06 / R2-S-12 / R2-M-22): the reset page has its own password hint (no LDAP
// sentence), the requested text names the 24 hours, and a wrong or short code reads the coded Turkish refusal.
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams("token=12"), useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }) }));

import { ResetPassword } from "./reset-password";
import { I18nProvider } from "@/lib/i18n/provider";
import { translate } from "@/lib/i18n";

describe("T-R2-06: reset page copy", () => {
  it("the new-password hint is the reset page's own: no LDAP / directory sentence", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">
          <ResetPassword />
        </I18nProvider>
      </QueryClientProvider>,
    );
    // AUX12-F07 (fix-h-2026-10-18): the code field, then SetPasswordForm: one password field with show/hide and the
    // backend's 12-character minimum (the old "En az 8 karakter." contradicted PASSWORD_MIN = 12)
    const form = screen.getByTestId("set-password-form");
    const card = form.parentElement!;
    expect(card.textContent).not.toMatch(/LDAP|Dizin/);
    expect(screen.getByLabelText("Tek kullanımlık kod")).toHaveValue("12");
    expect(form.textContent).toContain(translate("tr", "auth.setPassword.hint", { n: 12 }));
    expect(form.textContent).not.toContain("En az 8 karakter.");
    expect(form.querySelectorAll('input[type="password"]')).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Parolayı göster" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Parolayı tekrarlayın")).toBeNull();
  });
  it("the 'Oturum açmaya dön' link is a 44 px tall target on touch (MOBILE M-02 sweep of the lane's routes)", () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <I18nProvider initialLocale="tr">
          <ResetPassword />
        </I18nProvider>
      </QueryClientProvider>,
    );
    // ?token=12 opens the confirm form: back to the request form, which carries the link
    fireEvent.click(screen.getByRole("button", { name: "Kod istiyorum" }));
    expect(screen.getByRole("link", { name: "Oturum açmaya dön" })).toHaveClass("inline-flex", "items-center", "pointer-coarse:min-h-11");
    // AUX12-F07: the request field says what SSO users do instead (auth.md §4.4)
    expect(screen.getByText(translate("tr", "auth.setPassword.ssoLine"))).toBeInTheDocument();
  });
  it("the requested text names the 24 hours in both languages", () => {
    expect(translate("tr", "crbs.reset.requested")).toContain("24 saat");
    expect(translate("en", "crbs.reset.requested")).toContain("24 hours");
    expect(translate("tr", "crbs.reset.requested")).not.toContain("bir süre sonra");
  });
});
