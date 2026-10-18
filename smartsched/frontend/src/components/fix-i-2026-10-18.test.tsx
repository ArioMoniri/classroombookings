/** FIX-I (round-4 e2e triage, 2026-10-18): small reflow fixes found by Mobile B 6 (root 32 px at 390, E2EB-F02). */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import { VerdictTag } from "./compare/compare-view";

describe("E2EB-F02 /runs/compare at 200 % text: the unbreakable verdict word wraps inside its cell", () => {
  it("the 'karşılaştırılamaz' label may break anywhere and the tag never grows past its cell", () => {
    render(
      <I18nProvider initialLocale="tr">
        <VerdictTag v="incomparable" delta={null} locale="tr" />
      </I18nProvider>,
    );
    const label = screen.getByText("karşılaştırılamaz");
    expect(label.className).toContain("[overflow-wrap:anywhere]");
    expect(label.parentElement!.className).toContain("max-w-full");
  });
});
