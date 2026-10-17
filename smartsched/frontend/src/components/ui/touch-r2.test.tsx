// Flow-loop round 2, lane A (T-R2-05, R2-A-13 / R2-S-03 / R2-S-08 / R2-M-13 / R2-M-23 / R2-S-19): on coarse pointers the
// small primitives get a REAL 44 px box instead of relying on the ::after hit area alone, which any overflow:auto /
// overflow:hidden ancestor (card lists, the recurring date table, the sonner toast) clips. jsdom has no layout or media
// queries, so these pin the class contract; e2e/loop-r2-laneA.spec.ts measures the boxes on a stack.sh build.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { Checkbox } from "@/components/ui/checkbox";
import { Chip } from "@/components/ui/chip";
import { SegmentedControl, segmentedTrack } from "@/components/ui/segmented-control";
import { TOAST_CLASSNAMES } from "@/components/ui/sonner";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { LocaleToggle } from "@/components/shell/locale-toggle";
import { I18nProvider } from "@/lib/i18n/provider";

const css = readFileSync(join(process.cwd(), "src/app/globals.css"), "utf8");

describe("T-R2-05: real 44 px boxes on coarse pointers", () => {
  it("Switch is 44 px tall on touch, the capsule is drawn by ::before, the hit area no longer leaks past the box", () => {
    render(<Switch aria-label="Bildirimler" />);
    const sw = screen.getByRole("switch", { name: "Bildirimler" });
    expect(sw).toHaveClass("isolate", "pointer-coarse:min-h-11", "pointer-coarse:after:inset-y-0", "before:absolute", "before:rounded-full", "before:-z-10", "data-checked:before:bg-tint", "data-unchecked:before:bg-fill-1");
    expect(sw.className).not.toMatch(/(^|\s)data-checked:bg-tint(\s|$)/);
  });

  it("Checkbox is a 44 × 44 box on touch with the 16 px well drawn by ::before", () => {
    render(<Checkbox aria-label="Türkçe" />);
    const box = screen.getByRole("checkbox", { name: "Türkçe" });
    expect(box).toHaveClass("isolate", "pointer-coarse:size-11", "pointer-coarse:after:inset-0", "pointer-coarse:before:inset-[14px]", "before:bg-(--mat-thick)", "data-checked:before:bg-tint");
  });

  it("SegmentedControl track is at least 44 px tall on touch with no vertical padding, so every segment is 44 px (38 → 44)", () => {
    expect(segmentedTrack).toContain("pointer-coarse:min-h-11");
    expect(segmentedTrack).toContain("pointer-coarse:py-0");
    render(<SegmentedControl aria-label="Görünüm" options={[{ value: "w", label: "Hafta" }, { value: "d", label: "Gün" }]} />);
    expect(screen.getByRole("tablist", { name: "Görünüm" })).toHaveClass("pointer-coarse:min-h-11", "pointer-coarse:py-0");
  });

  it("Tabs triggers are at least 44 px tall on touch", () => {
    render(
      <Tabs defaultValue="a">
        <TabsList>
          <TabsTrigger value="a">Yaklaşan</TabsTrigger>
          <TabsTrigger value="b">Geçmiş</TabsTrigger>
        </TabsList>
      </Tabs>,
    );
    for (const tab of screen.getAllByRole("tab")) expect(tab).toHaveClass("pointer-coarse:min-h-11");
  });

  it("Chip sm takes the md height on touch and the chip wrapper pads to 44 px so a scrolling row never clips the hit area", () => {
    render(
      <Chip size="sm" selected={false} onSelectedChange={() => undefined} onRemove={() => undefined} removeLabel="Kaldır">
        Bina A
      </Chip>,
    );
    const chip = screen.getByRole("button", { name: "Bina A" });
    expect(chip).toHaveClass("h-6", "pointer-coarse:h-7");
    expect(screen.getByRole("button", { name: "Kaldır" })).toHaveClass("h-6", "pointer-coarse:h-7");
    expect(chip.closest("[data-slot=chip]")).toHaveClass("pointer-coarse:py-2");
  });

  it("the toast close button is a 44 × 44 box inside the toast's end padding on touch", () => {
    expect(TOAST_CLASSNAMES.closeButton).toMatch(/pointer-coarse:!size-11/);
    expect(TOAST_CLASSNAMES.closeButton).toMatch(/pointer-coarse:!transform-none/);
    expect(TOAST_CLASSNAMES.toast).toMatch(/pointer-coarse:!pr-12/);
  });

  it("native checkboxes and radios outside a label row grow their row by the 44 px hit area (base layer, coarse)", () => {
    expect(css).toContain('input:is([type="checkbox"], [type="radio"]):not(label *) { margin-block: 14px; }');
  });

  it("the locale toggle buttons carry the language name as their accessible name, not only a title (M-11)", () => {
    render(
      <I18nProvider initialLocale="tr">
        <LocaleToggle />
      </I18nProvider>,
    );
    expect(screen.getByRole("button", { name: "Türkçe" })).toHaveAttribute("aria-label", "Türkçe");
    expect(screen.getByRole("button", { name: "English" })).toHaveAttribute("aria-label", "English");
  });
});
