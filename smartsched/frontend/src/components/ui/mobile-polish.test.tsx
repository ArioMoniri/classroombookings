// Mobile polish (2026-10-16): Dialog as a phone bottom sheet, the full-height command sheet, Tabs hit areas and the
// /classes filter menu as a sheet on touch. jsdom has no layout or media queries, so these assert the class
// contract (Tailwind variants) and the DOM semantics; e2e/visual-quality.spec.ts and the 390 px probe measure boxes.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FilterMenu } from "@/components/classes/filter-bar";
import { EMPTY as EMPTY_FILTERS } from "@/components/classes/classes-model";
import { Checkbox } from "@/components/ui/checkbox";
import { Command, CommandDialog, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { coarseHitArea } from "@/components/ui/hit-area";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { I18nProvider } from "@/lib/i18n/provider";

function mockPointer(coarse: boolean) {
  const real = window.matchMedia;
  vi.spyOn(window, "matchMedia").mockImplementation((q: string) => ({ ...real(q), matches: q === "(pointer: coarse)" ? coarse : false, media: q }));
}

afterEach(() => vi.restoreAllMocks());

describe("Dialog on phones (MOBILE.md M-04)", () => {
  it("is a full-width bottom sheet below 640 px and stays centred from 640 px", () => {
    render(
      <Dialog open>
        <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-lg" data-testid="dlg">
          <DialogTitle>Yeni bölüm</DialogTitle>
        </DialogContent>
      </Dialog>,
    );
    const popup = screen.getByTestId("dlg");
    // desktop: centred, unchanged
    expect(popup).toHaveClass("top-1/2", "left-1/2", "-translate-x-1/2", "-translate-y-1/2", "rounded-3xl", "sm:max-w-lg");
    // phone: flush with the bottom edge, full width, top corners only, safe-area border; the popup is a column
    // whose body scrolls (T-R1-03), on the solid material
    expect(popup).toHaveClass(
      "max-sm:top-auto",
      "max-sm:bottom-[calc(var(--kb-inset,0px)+env(safe-area-inset-bottom,0px)-env(safe-area-max-inset-bottom,env(safe-area-inset-bottom,0px)))]",
      "max-sm:left-0",
      "max-sm:w-full",
      "max-sm:max-w-none",
      "max-sm:translate-x-0",
      "max-sm:translate-y-0",
      "max-sm:max-h-[calc(100dvh-3rem-var(--kb-inset,0px))]",
      "max-sm:overflow-hidden",
      "max-sm:rounded-b-none",
      "max-sm:border-b-[length:env(safe-area-max-inset-bottom,env(safe-area-inset-bottom,0px))]",
      "max-sm:border-b-transparent",
      "max-sm:bg-(--mat-thick-solid)",
    );
    expect(popup.querySelector("[data-slot=dialog-body]")).toHaveClass("overflow-y-auto", "min-h-0", "flex-1");
    // the caller's own height cap stays for tablets and desktops
    expect(popup).toHaveClass("max-h-[92dvh]");
  });

  it("CommandDialog takes the full sheet height on phones and keeps its own scroller", () => {
    render(
      <CommandDialog open title="Komut paleti" description="Ara">
        <Command>
          <CommandInput placeholder="Ara" />
          <CommandList />
        </Command>
      </CommandDialog>,
    );
    const popup = document.querySelector("[data-slot=dialog-content]")!;
    expect(popup).toHaveClass("max-sm:h-[calc(100dvh-3rem)]", "max-sm:overflow-hidden", "max-sm:**:data-[slot=command-list]:flex-1");
    expect(popup).not.toHaveClass("max-sm:overflow-y-auto");
  });
});

describe("Tabs triggers on touch (M-02)", () => {
  it("carry the shared 44 × 44 coarse hit area", () => {
    render(
      <Tabs defaultValue="a">
        <TabsList>
          <TabsTrigger value="a">Rapor</TabsTrigger>
          <TabsTrigger value="b">Izgara</TabsTrigger>
        </TabsList>
      </Tabs>,
    );
    for (const tab of screen.getAllByRole("tab")) {
      expect(coarseHitArea.split(" ").every((c) => tab.classList.contains(c))).toBe(true);
      expect(tab).toHaveClass("relative");
    }
  });
});

describe("Checkbox and command rows on touch (M-02)", () => {
  it("Checkbox is a 44 × 44 box on coarse pointers (16 → 44, T-R2-05) and keeps the desktop ::after extension", () => {
    render(<Checkbox aria-label="Türkçe" />);
    const box = screen.getByRole("checkbox", { name: "Türkçe" });
    expect(box).toHaveClass("relative", "after:-inset-x-3", "after:-inset-y-2", "pointer-coarse:size-11", "pointer-coarse:after:inset-0"); // T-R2-05: a real 44 px box on touch
  });

  it("command items are at least 44 px tall and the input fills its 44 px row on touch", () => {
    Element.prototype.scrollIntoView ??= () => undefined; // cmdk scrolls the selected item; jsdom has no layout
    render(
      <Command>
        <CommandInput placeholder="Ara" />
        <CommandList>
          <CommandItem>Derslikler</CommandItem>
        </CommandList>
      </Command>,
    );
    expect(document.querySelector("[data-slot=command-item]")).toHaveClass("h-9", "pointer-coarse:min-h-11");
    expect(screen.getByPlaceholderText("Ara")).toHaveClass("pointer-coarse:h-11");
  });
});

describe("/classes filter menu (M-02 / M-04)", () => {
  const menu = () => (
    <I18nProvider initialLocale="en">
      <FilterMenu rows={[]} filters={EMPTY_FILTERS} onChange={vi.fn()} shownCount={0} />
    </I18nProvider>
  );

  it("touch: opens a titled bottom sheet whose rows are 44 px", async () => {
    mockPointer(true);
    render(menu());
    await userEvent.click(screen.getByTestId("filter-menu"));
    const sheet = await screen.findByRole("dialog");
    expect(sheet).toHaveAttribute("data-side", "bottom");
    expect(sheet).toHaveClass("[&_button]:min-h-11");
    expect(screen.getAllByRole("menuitem").length).toBeGreaterThan(3);
  });

  it("fine pointer: stays a popover", async () => {
    mockPointer(false);
    render(menu());
    await userEvent.click(screen.getByTestId("filter-menu"));
    expect(await screen.findAllByRole("menuitem")).not.toHaveLength(0);
    expect(document.querySelector("[data-slot=sheet-content]")).toBeNull();
  });
});
