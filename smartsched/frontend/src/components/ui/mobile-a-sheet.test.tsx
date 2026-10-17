// Mobile audit A (2026-10-17), fixes 5, 8, 9, 10 on the bottom sheet and the phone dialog:
//  5  a phone bottom sheet is opaque (no backdrop blur repainting the page under a 270 ms slide);
//  8  iOS resizes only the visual viewport for the keyboard, so the popup is lifted by --kb-inset;
//  9  the grabber is a real drag handle: a drag down past 30 % of the height (or a flick) closes the sheet;
// 10  the bottom inset uses the Chrome 135+ edge-to-edge pattern (max inset, pulled down by the live inset).
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { keyboardInset } from "@/components/ui/keyboard-clearance";
import { Sheet, SheetContent, SheetTitle, shouldDismissSheet } from "@/components/ui/sheet";
import { I18nProvider } from "@/lib/i18n/provider";

const tr = (ui: React.ReactNode) => render(<I18nProvider initialLocale="tr">{ui}</I18nProvider>);
afterEach(() => vi.restoreAllMocks());

describe("keyboardInset: how much of the layout viewport the on-screen keyboard covers", () => {
  it("is the part of the window under the visual viewport (iOS: only the visual viewport shrinks)", () => {
    expect(keyboardInset(844, 508, 0)).toBe(336);
  });
  it("is 0 when the layout viewport resized with it (Android, interactive-widget=resizes-content)", () => {
    expect(keyboardInset(508, 508, 0)).toBe(0);
  });
  it("ignores small differences (toolbars collapsing, pinch zoom offsets)", () => {
    expect(keyboardInset(844, 790, 0)).toBe(0);
    expect(keyboardInset(844, 600, 300)).toBe(0);
  });
});

describe("shouldDismissSheet", () => {
  it("closes past 30 % of the height or on a downward flick, not on a nudge", () => {
    expect(shouldDismissSheet(250, 796, 0.1)).toBe(true);
    expect(shouldDismissSheet(60, 796, 0.9)).toBe(true);
    expect(shouldDismissSheet(60, 796, 0.2)).toBe(false);
    expect(shouldDismissSheet(10, 796, 2)).toBe(false);
  });
});

describe("bottom sheet on phones", () => {
  it("is opaque below 640 px and uses the max-inset safe-area pattern, lifted by --kb-inset", () => {
    tr(
      <Sheet open>
        <SheetContent side="bottom">
          <SheetTitle>Filtreler</SheetTitle>
        </SheetContent>
      </Sheet>,
    );
    const sheet = screen.getByRole("dialog");
    expect(sheet).toHaveClass(
      "max-sm:data-[side=bottom]:[--mat-chrome:var(--mat-thick-solid)]",
      "max-sm:data-[side=bottom]:[--mat-chrome-filter:none]",
      "max-sm:data-[side=bottom]:border-b-[length:env(safe-area-max-inset-bottom,env(safe-area-inset-bottom,0px))]",
      "max-sm:data-[side=bottom]:bottom-[calc(var(--kb-inset,0px)+env(safe-area-inset-bottom,0px)-env(safe-area-max-inset-bottom,env(safe-area-inset-bottom,0px)))]",
      "data-[side=bottom]:max-h-[calc(100dvh-3rem-var(--kb-inset,0px))]",
    );
    expect(sheet.className).not.toContain("border-b-[length:env(safe-area-inset-bottom)]");
  });

  it("has a real grabber, and a drag down past 30 % closes it", () => {
    const onOpenChange = vi.fn();
    tr(
      <Sheet open onOpenChange={onOpenChange}>
        <SheetContent side="bottom">
          <SheetTitle>Rezerve et</SheetTitle>
        </SheetContent>
      </Sheet>,
    );
    const sheet = screen.getByRole("dialog");
    vi.spyOn(sheet, "getBoundingClientRect").mockReturnValue({ top: 48, bottom: 844, height: 796, left: 0, right: 390, width: 390, x: 0, y: 48, toJSON: () => ({}) });
    const grabber = sheet.querySelector("[data-slot=sheet-grabber]")!;
    expect(grabber).not.toBeNull();
    fireEvent.pointerDown(grabber, { pointerId: 1, clientY: 60 });
    fireEvent.pointerMove(grabber, { pointerId: 1, clientY: 200 });
    expect(sheet.style.translate).toBe("0 140px");
    fireEvent.pointerMove(grabber, { pointerId: 1, clientY: 400 });
    fireEvent.pointerUp(grabber, { pointerId: 1, clientY: 400 });
    expect(onOpenChange).toHaveBeenCalledWith(false, expect.anything());
  });

  it("snaps back after a short drag", () => {
    const onOpenChange = vi.fn();
    tr(
      <Sheet open onOpenChange={onOpenChange}>
        <SheetContent side="bottom">
          <SheetTitle>Rezerve et</SheetTitle>
        </SheetContent>
      </Sheet>,
    );
    const sheet = screen.getByRole("dialog");
    vi.spyOn(sheet, "getBoundingClientRect").mockReturnValue({ top: 48, bottom: 844, height: 796, left: 0, right: 390, width: 390, x: 0, y: 48, toJSON: () => ({}) });
    const grabber = sheet.querySelector("[data-slot=sheet-grabber]")!;
    vi.spyOn(performance, "now").mockReturnValueOnce(0).mockReturnValue(1000); // slow: no flick
    fireEvent.pointerDown(grabber, { pointerId: 1, clientY: 60 });
    fireEvent.pointerMove(grabber, { pointerId: 1, clientY: 100 });
    fireEvent.pointerUp(grabber, { pointerId: 1, clientY: 100 });
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(sheet.style.translate).toBe("");
  });

  it("side sheets have no grabber", () => {
    tr(
      <Sheet open>
        <SheetContent side="right">
          <SheetTitle>Ayrıntı</SheetTitle>
        </SheetContent>
      </Sheet>,
    );
    expect(screen.getByRole("dialog").querySelector("[data-slot=sheet-grabber]")).toBeNull();
  });
});

describe("--kb-inset on the open popup", () => {
  it("is set from the visual viewport when the keyboard opens, and cleared when it closes", () => {
    const vv = Object.assign(new EventTarget(), { height: 844, offsetTop: 0, width: 390 });
    Object.defineProperty(window, "visualViewport", { configurable: true, value: vv });
    vi.spyOn(window, "innerHeight", "get").mockReturnValue(844);
    tr(
      <Dialog open>
        <DialogContent>
          <DialogTitle>Gerekçe</DialogTitle>
        </DialogContent>
      </Dialog>,
    );
    const popup = screen.getByRole("dialog");
    act(() => {
      vv.height = 508;
      vv.dispatchEvent(new Event("resize"));
    });
    expect(popup.style.getPropertyValue("--kb-inset")).toBe("336px");
    act(() => {
      vv.height = 844;
      vv.dispatchEvent(new Event("resize"));
    });
    expect(popup.style.getPropertyValue("--kb-inset")).toBe("0px");
    Reflect.deleteProperty(window, "visualViewport");
  });
});
