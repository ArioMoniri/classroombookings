import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { assignment, fixtureIndex } from "@/test/fixtures/calendar-index";
import { I18nProvider } from "@/lib/i18n/provider";
import { dayStartMin, periodStartMin } from "./model/geometry";
import { buildModel, eventsOf } from "./model/index-model";
import { DayTimeline } from "./day-timeline";

// owner report 2026-11-02: in Gün (day timeline) too, a click on a free slot opens quick-create (before: drag only)
const model = buildModel(fixtureIndex([assignment({ id: 9, label: "MAT 101 §2", day: 1, sp: 7, ep: 9, rooms: [3] })]));
const PX = 2;
const LABEL_W = 104;
const ROW_H = 40;
const HEAD_H = 32;

function renderTimeline(readOnly = false) {
  const props = { onOpen: vi.fn(), onCreate: vi.fn(), onSelect: vi.fn(), onMove: vi.fn(), onAnnounce: vi.fn() };
  render(
    <I18nProvider initialLocale="en">
      <DayTimeline model={model} rooms={model.rooms} day={1} mask={model.allMask} pxPerMin={PX} events={eventsOf(model, 1, 1)} blocks={[]} bookings={[]} nowMin={null} isToday={false} selection={new Set()} readOnly={readOnly} ariaFor={(e) => e.a.label} label="Monday" {...props} />
    </I18nProvider>,
  );
  return props;
}

// jsdom lays nothing out: the scroller is at 0,0
const at = (row: number, period: number) => ({ clientX: LABEL_W + (periodStartMin(period) - dayStartMin()) * PX + 4, clientY: HEAD_H + row * ROW_H + 10 });
const click = (pos: { clientX: number; clientY: number }, extra: Record<string, unknown> = {}) => {
  const tl = screen.getByTestId("day-timeline");
  fireEvent.pointerDown(tl, { button: 0, pointerId: 1, ...pos, ...extra });
  fireEvent.pointerUp(tl, { button: 0, pointerId: 1, ...pos, ...extra });
};

describe("DayTimeline: a click on a free slot opens quick-create", () => {
  beforeAll(() => {
    Element.prototype.setPointerCapture ??= () => {};
    Element.prototype.releasePointerCapture ??= () => {};
  });

  it("opens it for that room and period", () => {
    const p = renderTimeline();
    click(at(0, 2));
    expect(p.onCreate).toHaveBeenCalledWith(expect.objectContaining({ column: expect.objectContaining({ room: model.rooms[0]!.id, day: 1 }), sp: 2, ep: 2, via: "click" }));
  });

  it("a busy slot, the room labels, read-only and ⌘-click never create", () => {
    const p = renderTimeline();
    const busyRow = model.rooms.findIndex((r) => r.id === 3);
    click(at(busyRow, 8));
    click({ clientX: 20, clientY: HEAD_H + 10 }); // the sticky room label
    click(at(0, 2), { metaKey: true });
    expect(p.onCreate).not.toHaveBeenCalled();
    cleanup();
    const ro = renderTimeline(true);
    click(at(0, 2));
    expect(ro.onCreate).not.toHaveBeenCalled();
  });
});
