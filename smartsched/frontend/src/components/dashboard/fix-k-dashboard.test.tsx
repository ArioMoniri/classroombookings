// E2EB-F08 (FIX-K): with no schedule yet, "Çizelge oluştur" is a button-sized link, 44 px tall on touch.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { HeroStatus } from "./dashboard-view";

describe("dashboard hero without a plan", () => {
  it("offers 'Çizelge oluştur' as a button-sized link with a 44 px touch height", () => {
    render(
      <I18nProvider initialLocale="tr">
        <HeroStatus plan={undefined} />
      </I18nProvider>,
    );
    const link = screen.getByTestId("dashboard-make-plan");
    expect(link).toHaveAttribute("href", "/generate");
    expect(link.className).toContain("pointer-coarse:min-h-11");
    expect(link.className).toContain("h-(--control-h-md)");
  });
});
