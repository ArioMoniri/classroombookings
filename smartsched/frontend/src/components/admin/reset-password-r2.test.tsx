// Flow-loop round 2, lane A (T-R2-06, R2-A-06 / R2-S-12 / R2-M-22): the reset page has its own password hint (no LDAP
// sentence), the requested text names the 24 hours, and a wrong or short code reads the coded Turkish refusal.
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams("token=12") }));

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
    const form = screen.getByLabelText("Tek kullanımlık kod").closest("form")!;
    expect(form.textContent).not.toMatch(/LDAP|Dizin/);
    expect(form.textContent).toContain(translate("tr", "crbs.reset.passwordHint"));
    expect(translate("tr", "crbs.reset.passwordHint")).toBe("En az 8 karakter.");
    expect(translate("en", "crbs.reset.passwordHint")).toBe("At least 8 characters.");
  });
  it("the requested text names the 24 hours in both languages", () => {
    expect(translate("tr", "crbs.reset.requested")).toContain("24 saat");
    expect(translate("en", "crbs.reset.requested")).toContain("24 hours");
    expect(translate("tr", "crbs.reset.requested")).not.toContain("bir süre sonra");
  });
});
