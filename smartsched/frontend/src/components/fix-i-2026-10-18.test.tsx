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

describe("e2e fixtures on a recording stack (FIX-J KVKK upload guard)", async () => {
  const { resolveFixturesDir } = await import("../../e2e/fixtures-dir");
  const raw = "/repo/smartsched/backend/tests/fixtures";
  const none = () => false;
  it("pod CI / a plain local run: the raw fixtures (the guard is off there)", () => {
    expect(resolveFixturesDir({}, raw, none)).toBe(raw);
  });
  it("E2E_FIXTURES_DIR always wins", () => {
    expect(resolveFixturesDir({ E2E_FIXTURES_DIR: "/w/fixtures", REC_WORKDIR: "/w" }, raw, none)).toBe("/w/fixtures");
  });
  it("a recording stack (REC_WORKDIR) uses its masked copies when `stack.sh fixtures` made them", () => {
    expect(resolveFixturesDir({ REC_WORKDIR: "/w" }, raw, (p) => p === "/w/fixtures")).toBe("/w/fixtures");
  });
  it("a recording stack without masked copies fails with a clear message instead of using the raw workbooks", () => {
    expect(() => resolveFixturesDir({ REC_WORKDIR: "/w" }, raw, none)).toThrow(/E2E_FIXTURES_DIR.*stack\.sh fixtures/s);
    expect(() => resolveFixturesDir({ KVKK_UPLOAD_GUARD: "1" }, raw, none)).toThrow(/KVKK/);
    expect(() => resolveFixturesDir({ E2E_RECORDING_STACK: "1" }, raw, none)).toThrow(/E2E_FIXTURES_DIR/);
  });
});
