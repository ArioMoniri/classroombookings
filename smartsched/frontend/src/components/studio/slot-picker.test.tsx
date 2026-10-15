import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TemplateField } from "@/lib/api/studio-schemas";
import { I18nProvider } from "@/lib/i18n/provider";
import { SlotChip } from "./slot-picker";

const slot = { name: "weight", field: TemplateField.parse({ name: "weight", type: "int", param: "weight", min: 1, max: 10 }), value: 5, display: "5", empty: false, optional: false };

function mockPointer(coarse: boolean) {
  const real = window.matchMedia;
  vi.spyOn(window, "matchMedia").mockImplementation((q: string) => ({ ...real(q), matches: q === "(pointer: coarse)" ? coarse : false, media: q }));
}

afterEach(() => vi.restoreAllMocks());

describe("SlotChip (Studio backlog: slot pickers as bottom sheets on coarse pointers)", () => {
  it("fine pointer: a popover next to the slot", async () => {
    mockPointer(false);
    render(<I18nProvider initialLocale="en"><SlotChip slot={slot} onChange={vi.fn()} /></I18nProvider>);
    await userEvent.click(screen.getByTestId("slot-weight"));
    expect(document.querySelector("[data-slot=sheet-content]")).toBeNull();
  });

  it("coarse pointer: a bottom sheet with a title, so the editor is reachable with a thumb", async () => {
    mockPointer(true);
    render(<I18nProvider initialLocale="en"><SlotChip slot={slot} onChange={vi.fn()} /></I18nProvider>);
    await userEvent.click(screen.getByTestId("slot-weight"));
    const sheet = await screen.findByRole("dialog");
    expect(sheet.closest("[data-slot=sheet-content]") ?? sheet).toHaveAttribute("data-side", "bottom");
  });
});
