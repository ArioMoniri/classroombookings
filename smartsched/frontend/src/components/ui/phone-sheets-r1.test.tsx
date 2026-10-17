// Flow-loop round 1, lane A (T-R1-02 / T-R1-03 / T-R1-07): phone sheets and dialogs. jsdom has no layout, so these
// pin the class contract and the DOM semantics; e2e/loop-r1-laneA.spec.ts measures the boxes on a stack.sh build.
import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { KbdHint, modKeyLabel } from "@/components/ui/kbd-hint";
import { KeyboardClearance, overlapWith } from "@/components/ui/keyboard-clearance";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { TOASTER_MOBILE_OFFSET } from "@/components/ui/sonner";
import { I18nProvider } from "@/lib/i18n/provider";

afterEach(() => vi.restoreAllMocks());

const tr = (ui: React.ReactNode) => render(<I18nProvider initialLocale="tr">{ui}</I18nProvider>);

describe("Dialog on phones is a column: sticky header and footer, a scrolling body, an opaque surface (T-R1-03)", () => {
  it("puts the children in a scrolling body with the keyboard scroll padding and keeps the popup from scrolling", () => {
    tr(
      <Dialog open>
        <DialogContent data-testid="dlg">
          <DialogHeader>
            <DialogTitle>Yerel hesap oluştur</DialogTitle>
            <DialogDescription>Açıklama</DialogDescription>
          </DialogHeader>
          <form>
            <input aria-label="Ad" />
            <DialogFooter>
              <button type="submit">Oluştur</button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>,
    );
    const popup = screen.getByTestId("dlg");
    expect(popup).toHaveClass("flex", "flex-col", "max-sm:overflow-hidden", "max-sm:max-h-[calc(100dvh-3rem-var(--kb-inset,0px))]", "max-sm:bg-(--mat-thick-solid)");
    expect(popup).not.toHaveClass("max-sm:overflow-y-auto");
    const body = popup.querySelector("[data-slot=dialog-body]")!;
    expect(body).toHaveClass("overflow-y-auto", "min-h-0", "flex-1", "scroll-pb-24", "[&>*]:scroll-pb-24");
    expect(body.contains(screen.getByRole("button", { name: "Oluştur" }))).toBe(true);
    // the keyboard-clearance element rides inside the body, after the children
    expect(body.querySelector("[data-slot=keyboard-clearance]")).not.toBeNull();
  });

  it("the header sticks to the top and the footer to the bottom of the body on phones, both on the solid material", () => {
    tr(
      <Dialog open>
        <DialogContent>
          <DialogHeader data-testid="hdr">
            <DialogTitle>Başlık</DialogTitle>
          </DialogHeader>
          <DialogFooter data-testid="ftr">
            <button type="button">Kaydet</button>
          </DialogFooter>
        </DialogContent>
      </Dialog>,
    );
    expect(screen.getByTestId("hdr")).toHaveClass("max-sm:sticky", "max-sm:top-0", "max-sm:z-10", "max-sm:bg-(--mat-thick-solid)");
    expect(screen.getByTestId("ftr")).toHaveClass("max-sm:sticky", "max-sm:bottom-0", "max-sm:z-10", "max-sm:bg-(--mat-thick-solid)", "-mx-5", "-mb-5");
  });

  it("the close buttons are named in the user's language (T-R1-07: 'Close' leaked into the Turkish UI)", () => {
    tr(
      <Dialog open>
        <DialogContent>
          <DialogTitle>Başlık</DialogTitle>
          <DialogFooter showCloseButton />
        </DialogContent>
      </Dialog>,
    );
    const names = screen.getAllByRole("button").map((b) => b.textContent?.trim());
    expect(names).toEqual(["Kapat", "Kapat"]);
    // the icon close button sits on the popup (not in the scroller), above the sticky header
    const icon = document.querySelector("[data-slot=dialog-close]")!;
    expect(icon.closest("[data-slot=dialog-body]")).toBeNull();
    expect(icon).toHaveClass("absolute", "z-20");
  });
});

describe("Sheet keyboard clearance (T-R1-02)", () => {
  it("the popup and its direct children carry scroll-padding-bottom for the sticky footer, and the clearance element", () => {
    tr(
      <Sheet open>
        <SheetContent side="bottom" data-testid="sheet">
          <SheetHeader>
            <SheetTitle>Talep</SheetTitle>
            <SheetDescription>Açıklama</SheetDescription>
          </SheetHeader>
          <div className="flex-1 overflow-y-auto">
            <textarea aria-label="Not" />
          </div>
          <SheetFooter>
            <button type="button">Talep et</button>
          </SheetFooter>
        </SheetContent>
      </Sheet>,
    );
    const popup = screen.getByTestId("sheet");
    expect(popup).toHaveClass("scroll-pb-24", "[&>*]:scroll-pb-24");
    expect(popup.querySelector("[data-slot=keyboard-clearance]")).not.toBeNull();
  });

  it("scrolls a focused field into its nearest scroller after the focus and again when the viewport resizes (the keyboard)", () => {
    vi.useFakeTimers();
    const scrolled: string[] = [];
    render(
      <div data-testid="popup">
        <input aria-label="Not" onFocus={() => undefined} />
        <input type="checkbox" aria-label="Onay" />
        <KeyboardClearance />
      </div>,
    );
    const note = screen.getByRole("textbox", { name: "Not" });
    const box = screen.getByRole("checkbox", { name: "Onay" });
    for (const el of [note, box]) (el as HTMLElement).scrollIntoView = vi.fn((o: unknown) => scrolled.push(`${el.getAttribute("aria-label")}:${JSON.stringify(o)}`));
    act(() => note.focus());
    act(() => void vi.advanceTimersByTime(100));
    expect(scrolled).toEqual(['Not:{"block":"nearest","inline":"nearest"}']);
    act(() => void window.dispatchEvent(new Event("resize")));
    act(() => void vi.advanceTimersByTime(100));
    expect(scrolled).toHaveLength(2);
    // a checkbox is not typed into: no keyboard, no scroll
    act(() => box.focus());
    act(() => void vi.advanceTimersByTime(100));
    expect(scrolled).toHaveLength(2);
    vi.useRealTimers();
  });
});

describe("KeyboardClearance under jsdom (lane F2's ask: no uncaught TypeError when scrollIntoView is missing)", () => {
  it("focusing a field whose element has no scrollIntoView is a no-op", () => {
    vi.useFakeTimers();
    render(
      <div>
        <input aria-label="Ad" />
        <KeyboardClearance />
      </div>,
    );
    const field = screen.getByRole("textbox", { name: "Ad" });
    Object.defineProperty(field, "scrollIntoView", { value: undefined, configurable: true });
    expect(typeof (field as { scrollIntoView?: unknown }).scrollIntoView).toBe("undefined");
    act(() => field.focus());
    expect(() => act(() => void vi.advanceTimersByTime(200))).not.toThrow();
    vi.useRealTimers();
  });
});

describe("overlapWith: the scroll that clears a sticky footer or header (the wish sheet's two-button footer is 164 px)", () => {
  const box = (top: number, bottom: number) => ({ top, bottom });
  it("a field under the footer scrolls down by the overlap plus the gap; under the header, up; clear, not at all", () => {
    // measured on the lane stack at 390 × 508: search 368–412, sticky footer from 344
    expect(overlapWith(box(368, 412), null, box(344, 508))).toBe(412 + 8 - 344);
    expect(overlapWith(box(40, 84), box(0, 60), null)).toBe(40 - 8 - 60);
    expect(overlapWith(box(200, 244), box(0, 60), box(344, 508))).toBe(0);
    // a footer that is not sticky lies below the scroller: nothing to do (the book sheet)
    expect(overlapWith(box(286, 350), box(60, 133), box(388, 508))).toBe(0);
  });
});

describe("KbdHint names (T-R1-07)", () => {
  it("the modifier reads as a key word, never 'Command or Control' (the EN_WORDS scan)", () => {
    render(<KbdHint keys={["mod", "K"]} data-testid="kbd" />);
    const kbd = screen.getByTestId("kbd");
    expect(kbd.getAttribute("aria-label")).toBe("Ctrl + K");
    expect(kbd.getAttribute("aria-label")).not.toMatch(/Command or Control/);
    expect(modKeyLabel(false)).toBe("Ctrl");
    expect(modKeyLabel(true)).toBe("Cmd");
  });
  it("a sequence uses the localised 'then' word", () => {
    render(<KbdHint keys={["G", "T"]} sequence thenLabel="sonra" data-testid="kbd" />);
    expect(screen.getByTestId("kbd").getAttribute("aria-label")).toBe("G sonra T");
  });
});

describe("Toaster (T-R1-06 / T-R1-07)", () => {
  it("stacks above the tab bar on phones", () => {
    expect(TOASTER_MOBILE_OFFSET.bottom).toContain("var(--shell-bottom-h");
  });
});
