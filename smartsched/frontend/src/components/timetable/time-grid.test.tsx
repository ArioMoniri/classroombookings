import { fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { assignment, fixtureIndex } from "@/test/fixtures/calendar-index";
import { I18nProvider } from "@/lib/i18n/provider";
import { buildModel, eventsOf } from "./model/index-model";
import { TimeGrid, type GridColumn } from "./time-grid";

const model = buildModel(fixtureIndex([assignment({ id: 9, label: "MAT 101 §2", day: 1, sp: 7, ep: 9, rooms: [3] })]));
const columns: GridColumn[] = model.rooms.map((r) => ({ key: `r${r.id}`, room: r.id, day: 1, label: r.name, ariaLabel: r.name }));
const colIndex = new Map(columns.map((c, i) => [c.room, i]));

function renderGrid({ readOnly = false }: { readOnly?: boolean } = {}) {
  const props = { onOpen: vi.fn(), onCreate: vi.fn(), onSelect: vi.fn(), onMove: vi.fn(), onAnnounce: vi.fn() };
  render(
    <I18nProvider initialLocale="en">
      <TimeGrid
        model={model}
        mask={model.allMask}
        columns={columns}
        colW={160}
        rowH={32}
        events={eventsOf(model, 1, 1)}
        colOf={(e) => colIndex.get(e.room) ?? -1}
        blocks={[]}
        blockCol={() => -1}
        bookings={[]}
        bookingCol={() => -1}
        selection={new Set()}
        onSelectMany={vi.fn()}
        onResize={vi.fn()}
        gridLabel="Monday"
        headerH={40}
        line2={() => ""}
        ariaFor={(e) => e.a.label}
        readOnly={readOnly}
        {...props}
      />
    </I18nProvider>,
  );
  return props;
}

describe("TimeGrid keyboard (admin persona M-16)", () => {
  it("Enter on a focused class chip opens the inspector for that class, never quick-create", () => {
    const p = renderGrid();
    const chip = screen.getByRole("button", { name: "MAT 101 §2" });
    chip.focus();
    fireEvent.keyDown(chip, { key: "Enter" });
    expect(p.onCreate).not.toHaveBeenCalled();
    expect(p.onOpen).toHaveBeenCalledWith(expect.objectContaining({ a: expect.objectContaining({ id: 9 }) }));
  });

  it("Space on a focused chip picks that class up for a keyboard move", () => {
    const p = renderGrid();
    const chip = screen.getByRole("button", { name: "MAT 101 §2" });
    chip.focus();
    fireEvent.keyDown(chip, { key: " " });
    expect(p.onAnnounce).toHaveBeenCalledWith(expect.stringContaining("MAT 101 §2"));
  });
});

// owner report 2026-11-02 ("Çizelge'de rezerve edemiyorum; + çalışmıyor"): a free cell shows a "+" on hover, but a
// plain click on it only cleared the selection; quick-create opened after a drag across slots alone
describe("TimeGrid: a click on a free slot's + opens quick-create", () => {
  beforeAll(() => {
    // jsdom has no pointer capture
    Element.prototype.setPointerCapture ??= () => {};
    Element.prototype.releasePointerCapture ??= () => {};
  });
  // jsdom lays nothing out: the scroller's box is at 0,0, so content x = clientX − 56 (gutter), y = clientY − 40 (header)
  const at = (col: number, period: number) => ({ clientX: 56 + col * 160 + 20, clientY: 40 + (period - 1) * 32 + 8 });
  const click = (col: number, period: number, extra: Record<string, unknown> = {}) => {
    const grid = screen.getByTestId("time-grid");
    fireEvent.pointerDown(grid, { button: 0, pointerId: 1, ...at(col, period), ...extra });
    fireEvent.pointerUp(grid, { button: 0, pointerId: 1, ...at(col, period), ...extra });
  };
  const free = (col: number, period: number) => document.querySelector(`[data-testid="grid-drop-cell"][data-room-id="${columns[col].room}"][data-period="${period}"]`)?.getAttribute("data-free");

  it("opens quick-create for that room and period", () => {
    const p = renderGrid();
    expect(free(0, 2)).toBe("true");
    click(0, 2);
    expect(p.onCreate).toHaveBeenCalledTimes(1);
    expect(p.onCreate).toHaveBeenCalledWith(expect.objectContaining({ column: expect.objectContaining({ room: columns[0].room, day: 1 }), sp: 2, ep: 2, via: "click" }));
  });

  it("a busy slot only clears the selection", () => {
    const p = renderGrid();
    const col = colIndex.get(3)!; // MAT 101 §2 sits in room 3, P7–P9
    expect(free(col, 8)).toBeNull();
    click(col, 8);
    expect(p.onCreate).not.toHaveBeenCalled();
    expect(p.onSelect).toHaveBeenCalledWith(null, "replace");
  });

  it("a click on the sticky header after scrolling down never creates", () => {
    const p = renderGrid();
    const grid = screen.getByTestId("time-grid");
    grid.scrollTop = 200; // the header stays at the top while the rows scroll under it
    fireEvent.pointerDown(grid, { button: 0, pointerId: 1, clientX: 56 + 20, clientY: 20 });
    fireEvent.pointerUp(grid, { button: 0, pointerId: 1, clientX: 56 + 20, clientY: 20 });
    expect(p.onCreate).not.toHaveBeenCalled();
  });

  it("read-only users never create", () => {
    const ro = renderGrid({ readOnly: true });
    click(0, 2);
    expect(ro.onCreate).not.toHaveBeenCalled();
  });

  it("⌘- and Shift-clicks keep their selection gestures (no quick-create)", () => {
    const p = renderGrid();
    click(0, 2, { metaKey: true });
    click(0, 3, { shiftKey: true });
    expect(p.onCreate).not.toHaveBeenCalled();
  });

  it("the free cell's + is a visible glyph, not label-4 text", () => {
    renderGrid();
    const cell = document.querySelector('[data-testid="grid-drop-cell"][data-free="true"]');
    const plus = cell?.querySelector('[data-slot="free-plus"]');
    expect(plus).not.toBeNull();
    expect(plus?.className).toContain("text-tint-text");
    expect(plus?.querySelector("svg")).not.toBeNull();
  });
});
