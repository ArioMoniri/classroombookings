// ui primitives touch (2026-10-16): coarse-pointer hit areas, 16 px phone text, the phone bottom sheet, Button
// variant="bare" and the DataTable card target. jsdom has no layout or media queries, so these assert the class
// contract (Tailwind variants) and the DOM semantics; e2e/visual-quality.spec.ts measures the real boxes.
import { act, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BareButton as ShellBareButton } from "@/components/shell/bare-button";
import { BareButton, Button, IconButton } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { DataTable, type DataColumn } from "@/components/ui/data-table";
import { DateField } from "@/components/ui/date-field";
import { coarseHitArea, coarsePhoneText } from "@/components/ui/hit-area";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";

const HIT = coarseHitArea.split(" ");
const hasHitArea = (el: Element) => HIT.every((c) => el.classList.contains(c));

describe("coarse hit areas", () => {
  it("every Button size carries the 44 × 44 ::after, including the icon-sm the Sheet close uses", () => {
    render(
      <>
        <Button size="icon-sm" aria-label="Kapat" />
        <Button size="xs">Ekle</Button>
        <IconButton label="Önceki" size="xs" />
      </>,
    );
    for (const name of ["Kapat", "Ekle", "Önceki"]) {
      const b = screen.getByRole("button", { name });
      expect(hasHitArea(b)).toBe(true);
      expect(b).toHaveClass("relative");
    }
  });

  it("Switch grows to at least 44 px tall on touch and keeps the 8 px desktop extension", () => {
    render(<Switch aria-label="Bildirimler" />);
    const sw = screen.getByRole("switch", { name: "Bildirimler" });
    expect(sw).toHaveClass("after:-inset-y-2", "after:-inset-x-3", "pointer-coarse:min-h-11", "pointer-coarse:min-w-11", "pointer-coarse:after:inset-0"); // T-R2-05: a real 44 px box on touch
  });

  it("Chip and its remove button both get the hit area", () => {
    render(
      <Chip selected={false} onSelectedChange={() => undefined} onRemove={() => undefined} removeLabel="Kaldır">
        Bina A
      </Chip>,
    );
    const chip = screen.getByRole("button", { name: "Bina A" });
    const remove = screen.getByRole("button", { name: "Kaldır" });
    expect(hasHitArea(chip) && chip.classList.contains("relative")).toBe(true);
    expect(hasHitArea(remove) && remove.classList.contains("relative")).toBe(true);
    // wider on touch so its hit area stays inside the chip's own end padding
    expect(remove).toHaveClass("pointer-coarse:pl-2", "pointer-coarse:pr-2.5");
  });

  it("SegmentedControl segments get the hit area; the select fallback has 16 px phone text", () => {
    render(
      <SegmentedControl
        aria-label="Görünüm"
        options={[
          { value: "w", label: "Hafta" },
          { value: "d", label: "Gün" },
        ]}
      />,
    );
    for (const tab of screen.getAllByRole("tab")) expect(hasHitArea(tab)).toBe(true);
    expect(screen.getByRole("combobox", { name: "Görünüm" })).toHaveClass(coarsePhoneText);
  });
});

describe("16 px text on phones", () => {
  it("NativeSelect builds it in and still merges the caller's select classes", () => {
    render(
      <NativeSelect aria-label="Bina" selectClassName="w-40">
        <option>A</option>
      </NativeSelect>,
    );
    const select = screen.getByRole("combobox", { name: "Bina" });
    expect(select).toHaveClass("max-md:pointer-coarse:text-base", "w-40");
  });

  it("DateField: the input has it, the calendar trigger has the hit area, Today / Clear are ui Buttons", async () => {
    function Harness() {
      const [v, setV] = useState("2026-10-15");
      return <DateField aria-label="Tarih" value={v} onChange={setV} locale="tr-TR" />;
    }
    render(<Harness />);
    expect(screen.getByRole("textbox", { name: "Tarih" })).toHaveClass(coarsePhoneText);
    const trigger = screen.getByRole("button", { name: "Takvimi aç" });
    expect(hasHitArea(trigger)).toBe(true);
    await userEvent.click(trigger);
    const today = await screen.findByRole("button", { name: "Bugün" });
    const clear = screen.getByRole("button", { name: "Temizle" });
    for (const b of [today, clear]) {
      expect(b).toHaveAttribute("data-slot", "button");
      expect(b).toHaveAttribute("type", "button");
      expect(hasHitArea(b)).toBe(true);
    }
    expect(screen.getByRole("button", { name: "Önceki ay" })).toHaveAttribute("data-slot", "icon-button");
    expect(screen.getByRole("button", { name: "Sonraki ay" })).toHaveAttribute("data-slot", "icon-button");
    await userEvent.click(clear);
    expect(screen.getByRole("textbox", { name: "Tarih" })).toHaveValue("");
  });
});

describe("Sheet on phones", () => {
  it("the bottom sheet is full width and flush below 640 px, with the safe-area border; the close is a Button", () => {
    render(
      <Sheet open>
        <SheetContent side="bottom" className="p-5">
          <SheetTitle>Filtreler</SheetTitle>
        </SheetContent>
      </Sheet>,
    );
    const sheet = screen.getByRole("dialog");
    expect(sheet).toHaveClass(
      "max-sm:data-[side=bottom]:inset-x-0",
      "max-sm:data-[side=bottom]:bottom-0",
      "max-sm:data-[side=bottom]:rounded-b-none",
      "max-sm:data-[side=bottom]:border-b-[length:env(safe-area-inset-bottom)]",
      "p-5",
    );
    // the floating sheet on larger screens is unchanged except for the safe-area lift
    expect(sheet).toHaveClass("data-[side=bottom]:inset-x-2", "data-[side=bottom]:bottom-[max(0.5rem,env(safe-area-inset-bottom))]");
    const close = within(sheet).getByRole("button", { name: "Kapat" });
    expect(close).toHaveAttribute("data-slot", "sheet-close");
    expect(hasHitArea(close)).toBe(true);
  });
});

describe('Button variant="bare"', () => {
  it("has no control size, fill or pill, inherits the weight, and marks itself bare-button", () => {
    render(
      <>
        <Button variant="bare" className="rounded-md p-2">Hücre</Button>
        <Button variant="bare" className="font-semibold">Kalın</Button>
      </>,
    );
    const bare = screen.getByRole("button", { name: "Hücre" });
    expect(bare).toHaveAttribute("data-slot", "bare-button");
    expect(bare).not.toHaveAttribute("data-size");
    expect(bare.className).not.toMatch(/control-h|rounded-full|bg-tint/);
    expect(bare).toHaveClass("inline-block", "whitespace-normal", "[font-weight:inherit]", "rounded-md", "p-2");
    expect(hasHitArea(bare)).toBe(true);
    const bold = screen.getByRole("button", { name: "Kalın" });
    expect(bold).toHaveClass("font-semibold");
    expect(bold).not.toHaveClass("[font-weight:inherit]");
    expect(bold).not.toHaveClass("font-medium");
  });

  it("shell/bare-button is the same component", () => {
    expect(ShellBareButton).toBe(BareButton);
    render(<ShellBareButton className="flex">Satır</ShellBareButton>);
    const b = screen.getByRole("button", { name: "Satır" });
    expect(b).toHaveAttribute("data-slot", "bare-button");
    expect(b).toHaveClass("flex");
    expect(b).not.toHaveClass("inline-block");
  });
});

describe("DataTable card mode", () => {
  type Row = { id: number; name: string; seats: number };
  const rows: Row[] = [
    { id: 1, name: "A-101", seats: 40 },
    { id: 2, name: "B-202", seats: 60 },
  ];

  afterEach(() => vi.unstubAllGlobals());

  /** a ResizeObserver that reports a 380 px wide container (card mode is < 600) */
  function narrow() {
    vi.stubGlobal(
      "ResizeObserver",
      class {
        cb: ResizeObserverCallback;
        constructor(cb: ResizeObserverCallback) {
          this.cb = cb;
        }
        observe(el: Element) {
          this.cb([{ contentRect: { width: 380 } } as ResizeObserverEntry], this as unknown as ResizeObserver);
          void el;
        }
        unobserve() {}
        disconnect() {}
      },
    );
  }

  const base = (title: DataColumn<Row>["cell"], extra?: Partial<DataColumn<Row>>): DataColumn<Row>[] => [
    { id: "name", header: "Ad", pin: "left", priority: 1, text: (r) => r.name, sortValue: (r) => r.name, cell: title },
    { id: "seats", header: "Kapasite", priority: 1, align: "end", text: (r) => String(r.seats), sortValue: (r) => r.seats, cell: (r) => String(r.seats), ...extra },
  ];

  it("hidden header has no sort buttons or resize handles; each card is ONE button target named by its title", async () => {
    narrow();
    const onRow = vi.fn();
    render(<DataTable tableId="t1" label="Derslikler" columns={base((r) => <span>{r.name}</span>)} rows={rows} getRowId={(r) => String(r.id)} onRowActivate={onRow} />);
    const table = await screen.findByRole("table", { name: "Derslikler" });
    expect(table).toHaveAttribute("data-mode", "cards");
    const header = within(table).getAllByRole("row")[0];
    expect(within(header).queryAllByRole("button")).toHaveLength(0);
    expect(within(header).queryAllByRole("separator")).toHaveLength(0);
    expect(within(header).getAllByRole("columnheader").map((h) => h.textContent)).toEqual(["Ad", "Kapasite"]);
    const cards = within(table).getAllByRole("row").slice(1);
    expect(cards).toHaveLength(2);
    for (const card of cards) {
      expect(card).not.toHaveAttribute("tabindex");
      expect(card).toHaveAttribute("data-card-target", "button");
      expect(within(card).getAllByRole("button")).toHaveLength(1);
    }
    const target = within(cards[1]).getByRole("button", { name: "B-202" });
    expect(target).toHaveClass("absolute", "inset-0");
    await userEvent.click(target);
    expect(onRow).toHaveBeenCalledWith(rows[1]);
    // keyboard: the target is a real button (Enter / Space), one tab stop per card
    target.focus();
    await userEvent.keyboard("{Enter}");
    expect(onRow).toHaveBeenCalledTimes(2);
  });

  it("a title link becomes the stretched target (no extra button); nested actions are lifted out of the click area", async () => {
    narrow();
    const onRow = vi.fn();
    const onAction = vi.fn();
    const cols = base(
      (r) => <a href={`/rooms/${r.id}`}>{r.name}</a>,
      { cell: (r) => <Button size="xs" onClick={onAction}>{r.seats} kişi</Button> },
    );
    render(<DataTable tableId="t2" label="Derslikler" columns={cols} rows={rows} getRowId={(r) => String(r.id)} onRowActivate={onRow} />);
    const table = await screen.findByRole("table");
    const card = within(table).getAllByRole("row")[1];
    await act(async () => undefined);
    expect(card).toHaveAttribute("data-card-target", "link");
    expect(within(card).getByRole("link", { name: "A-101" })).toHaveAttribute("href", "/rooms/1");
    // only the nested action remains a button; the overlay button is gone
    expect(within(card).getAllByRole("button").map((b) => b.textContent)).toEqual(["40 kişi"]);
    expect(card.className).toMatch(/\[&_\[data-card-title\]_a\[href\]\]:after:inset-0/);
    expect(card.className).toMatch(/\[&_dd_:is\(a\[href\],button/);
    await userEvent.click(within(card).getByRole("button", { name: "40 kişi" }));
    expect(onAction).toHaveBeenCalledTimes(1);
    expect(onRow).not.toHaveBeenCalled();
  });

  it("without onRowActivate a plain-text card has no target at all", async () => {
    narrow();
    render(<DataTable tableId="t3" label="Derslikler" columns={base((r) => r.name)} rows={rows} getRowId={(r) => String(r.id)} />);
    const table = await screen.findByRole("table");
    const card = within(table).getAllByRole("row")[1];
    expect(within(card).queryAllByRole("button")).toHaveLength(0);
    expect(card).not.toHaveAttribute("data-card-target");
  });
});
