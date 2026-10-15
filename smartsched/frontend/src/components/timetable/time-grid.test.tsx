import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { assignment, fixtureIndex } from "@/test/fixtures/calendar-index";
import { I18nProvider } from "@/lib/i18n/provider";
import { buildModel, eventsOf } from "./model/index-model";
import { TimeGrid, type GridColumn } from "./time-grid";

const model = buildModel(fixtureIndex([assignment({ id: 9, label: "MAT 101 §2", day: 1, sp: 7, ep: 9, rooms: [3] })]));
const columns: GridColumn[] = model.rooms.map((r) => ({ key: `r${r.id}`, room: r.id, day: 1, label: r.name, ariaLabel: r.name }));
const colIndex = new Map(columns.map((c, i) => [c.room, i]));

function renderGrid() {
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
