// Dense grids on phones (2026-10-16): below 640 px the /rooms/[id] week grid is a day view, the /admin/sessions
// calendar taps with 44 px cells and paint modes, the dashboard heatmap is a ranked BarList per day, and the
// /admin/roles booking matrix is two groups of 44 px labelled rows. jsdom has no layout, so these assert the DOM,
// the interaction and the class contract (min-h-11 = 44 px); the 390 px touch probe measures the boxes.
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/lib/i18n/provider";
import type { DashboardSummary } from "@/lib/api/schemas";

const media = vi.hoisted(() => ({ phone: true }));
vi.mock("@/components/bookings/use-is-phone", () => ({ useIsPhone: () => media.phone, useIsCompact: () => media.phone }));

const painter = vi.hoisted(() => ({
  dates: {
    term_id: 7,
    start: "2026-02-16",
    end: "2026-02-28",
    dates: Array.from({ length: 13 }, (_, i) => ({ date: `2026-02-${String(16 + i).padStart(2, "0")}`, timetable_week_id: null, term_week: i < 7 ? 1 : 2, holiday: null })),
  },
}));
vi.mock("@/lib/api/crbs", () => ({
  crbs: { bookingAdmin: {} },
  crbsError: (e: unknown) => e,
  useCrbsMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useSessionDates: () => ({ data: painter.dates, isLoading: false }),
  useTimetableWeeks: () => ({ data: [{ id: 1, name: "A", bgcol: "#2563eb", fgcol: "#ffffff" }] }),
  useOrgI18n: () => ({ data: undefined }),
  useBookingContext: () => ({ data: undefined }),
  useSchedules: () => ({ data: [] }),
  useTermSchedules: () => ({ data: [] }),
  useSessions: () => ({ data: [] }),
}));

import { RoomClassesList, RoomDayView, initialDay } from "@/components/rooms/room-day-view";
import type { RoomCell } from "@/components/rooms/room-occupancy";
import { DatePainter } from "@/components/admin/sessions-admin";
import { PermissionMatrix } from "@/components/admin/roles-admin";
import { UtilisationHeatmap, rankRows } from "@/components/dashboard/utilisation-heatmap";
import { BarList } from "@/components/ui/bar-list";
import { SegmentedControl } from "@/components/ui/segmented-control";

const wrap = (ui: ReactNode, locale: "tr" | "en" = "tr") => render(<I18nProvider initialLocale={locale}>{ui}</I18nProvider>);

beforeEach(() => {
  media.phone = true;
});

/** Monday: a class P1–P2, a block P5; the rest free. Other days free. */
function weekGrid(): RoomCell[][] {
  const free = (): RoomCell[] => Array.from({ length: 18 }, () => ({ kind: "free" }) as RoomCell);
  const mon = free();
  const cls: RoomCell = { kind: "class", label: "HEM 101", aid: 9, fac: 2, conflict: false, sp: 1, ep: 2 };
  mon[0] = cls;
  mon[1] = cls;
  mon[4] = { kind: "block", label: "Bakım", sp: 5, ep: 5 };
  return [mon, free(), free(), free(), free(), free(), free()];
}

describe("/rooms/[id] day view (phones)", () => {
  it("opens on today when shown, else the first day", () => {
    expect(initialDay([1, 2, 3, 4, 5, 6], 3)).toBe(3);
    expect(initialDay([1, 2, 3, 4, 5, 6], 7)).toBe(1);
    expect(initialDay([1, 2, 3, 4, 5, 6, 7], 7)).toBe(7);
    expect(initialDay([1, 2, 3, 4, 5, 6], null)).toBe(1);
  });

  it("shows one day: a SegmentedControl Pzt…Cmt, held spans as one row, free periods as 44 px rows that pick a slot", async () => {
    const onPick = vi.fn();
    const onDay = vi.fn();
    wrap(<RoomDayView grid={weekGrid()} days={[1, 2, 3, 4, 5, 6]} day={1} onDay={onDay} picked={null} onPick={onPick} now={null} />);
    const tabs = within(screen.getByTestId("room-day-picker")).getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt"]);
    expect(tabs[0]).toHaveAttribute("aria-selected", "true");
    const panel = screen.getByRole("tabpanel");
    expect(tabs[0]).toHaveAttribute("aria-controls", panel.id);
    const rows = within(panel).getAllByRole("listitem");
    // P1–P2 class + P3, P4 free + P5 block + P6…P18 free = 1 + 2 + 1 + 13
    expect(rows).toHaveLength(17);
    expect(rows[0]).toHaveAccessibleName("Pazartesi P1–2: HEM 101");
    expect(rows[0]).toHaveClass("min-h-11", "cal-chip");
    expect(rows[3]).toHaveClass("cal-block");
    const free = within(panel).getByRole("button", { name: "Pazartesi P3: boş" });
    expect(free).toHaveClass("min-h-11", "w-full");
    await userEvent.click(free);
    // two periods from P3 (P4 is free)
    expect(onPick).toHaveBeenCalledWith({ day: 1, sp: 3, ep: 4, length: 2 });
    await userEvent.click(within(panel).getByRole("button", { name: "Pazartesi P4: boş" }));
    // one period when the next is taken
    expect(onPick).toHaveBeenLastCalledWith({ day: 1, sp: 4, ep: 4, length: 1 });
    await userEvent.click(tabs[2]);
    expect(onDay).toHaveBeenCalledWith(3);
  });

  it("marks the picked slot and has no buttons when booking is off", () => {
    const { rerender } = wrap(<RoomDayView grid={weekGrid()} days={[1, 2, 3, 4, 5, 6]} day={1} onDay={() => {}} picked={{ day: 1, sp: 3, ep: 4, length: 2 }} onPick={() => {}} now={null} />);
    expect(screen.getByRole("button", { name: "Pazartesi P3: boş" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Pazartesi P6: boş" })).toHaveAttribute("aria-pressed", "false");
    rerender(
      <I18nProvider initialLocale="tr">
        <RoomDayView grid={weekGrid()} days={[1, 2, 3, 4, 5, 6]} day={1} onDay={() => {}} picked={null} now={null} />
      </I18nProvider>,
    );
    expect(within(screen.getByRole("tabpanel")).queryAllByRole("button")).toHaveLength(0);
  });

  it("lists the week's classes as 44 px links instead of a 560 px table", () => {
    const e = { key: "k1", day: 2, sp: 3, ep: 4, a: { id: 41, label: "HEM 101", slot: 2, prog: "Hemşirelik", size: 40 } };
    wrap(<RoomClassesList classes={[e] as never} capacity={30} hrefOf={(x) => `/timetable?sel=${x.a.id}`} />);
    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/timetable?sel=41");
    expect(link).toHaveClass("min-h-11");
    expect(link).toHaveTextContent("HEM 101");
    expect(link).toHaveTextContent(/Sal 10:10–\d\d:\d\d/);
  });
});

describe("/admin/sessions calendar (phones)", () => {
  const session = { term_id: 7, code: "2026-BAHAR", name: "Bahar", kind: "TERM", is_current: true, is_selectable: true, mapped_dates: 0, holidays: 0 };

  it("drops the week-number column, taps instead of pointer strokes and lets the page scroll", () => {
    wrap(<DatePainter session={session} />);
    expect(screen.queryByRole("button", { name: /haftasını boya/ })).toBeNull();
    const cell = screen.getByRole("button", { name: /^2026-02-16/ });
    expect(cell).not.toHaveClass("touch-none");
    expect(cell.closest("[role=row]")).toHaveClass("grid-cols-7");
    expect(screen.getByTestId("painter-howto")).toHaveTextContent("dokunun");
  });

  it("Gün paints one date, Hafta the whole week, Aralık the dates between two taps", async () => {
    wrap(<DatePainter session={session} />);
    const save = screen.getByTestId("painter-save");
    expect(save).toBeDisabled();
    const modes = within(screen.getByTestId("painter-mode")).getAllByRole("radio");
    expect(modes.map((m) => m.textContent)).toEqual(["Gün", "Hafta", "Aralık"]);
    // brush A, day mode
    await userEvent.click(screen.getByRole("radio", { name: "A" }));
    await userEvent.click(screen.getByRole("button", { name: /^2026-02-17/ }));
    expect(screen.getByRole("button", { name: /^2026-02-17/ })).toHaveAccessibleName(/A, değişti/);
    expect(save).toHaveTextContent("1");
    // week mode: Monday 23 – Saturday 28 (the term ends on the 28th)
    await userEvent.click(modes[1]);
    await userEvent.click(screen.getByRole("button", { name: /^2026-02-25/ }));
    expect(save).toHaveTextContent("7");
    // range mode: 18 → 20 paints 18, 19, 20
    await userEvent.click(modes[2]);
    await userEvent.click(screen.getByRole("button", { name: /^2026-02-18/ }));
    expect(screen.getByTestId("painter-howto")).toHaveTextContent("son tarihe dokunun");
    expect(screen.getByRole("button", { name: /^2026-02-18/ })).toHaveAttribute("data-anchor", "true");
    await userEvent.click(screen.getByRole("button", { name: /^2026-02-20/ }));
    expect(screen.getByRole("button", { name: /^2026-02-19/ })).toHaveAccessibleName(/A, değişti/);
    expect(save).toHaveTextContent("10");
    expect(screen.getByTestId("painter-howto")).not.toHaveTextContent("son tarihe");
  });

  it("keeps the desktop calendar (week numbers, pointer strokes) from 640 px", () => {
    media.phone = false;
    wrap(<DatePainter session={session} />);
    expect(screen.queryByTestId("painter-mode")).toBeNull();
    expect(screen.getAllByRole("button", { name: /haftasını boya/ }).length).toBeGreaterThan(0);
    const cell = screen.getByRole("button", { name: /^2026-02-16, / });
    expect(cell).toHaveClass("touch-none");
    fireEvent.click(screen.getByRole("radio", { name: "A" }));
    fireEvent.pointerDown(cell);
    fireEvent.pointerUp(window);
    expect(screen.getByTestId("painter-save")).toHaveTextContent("1");
  });
});

function summary(): DashboardSummary {
  const day = (building: string, v: number[]) => v.map((utilisation, i) => ({ building, day: i + 1, utilisation }));
  return {
    utilisation: 0.4,
    rooms_bookable: 30,
    utilisation_by_building: [
      { building: "A", utilisation: 0.3, rooms: 10 },
      { building: "B", utilisation: 0.5, rooms: 10 },
      { building: "C", utilisation: 0.2, rooms: 10 },
    ],
    utilisation_building_day: [...day("A", [0.3, 0.4, 0.1, 0, 0, 0, 0]), ...day("B", [0.6, 0.2, 0.5, 0, 0, 0, 0]), ...day("C", [0.1, 0.9, 0.2, 0, 0, 0, 0])],
    utilisation_building_period: [],
    peak_hours: [],
  } as unknown as DashboardSummary;
}

describe("dashboard heat cells (phones)", () => {
  it("ranks rows by value, ties by name", () => {
    expect(rankRows([{ building: "B" }, { building: "A" }, { building: "C" }], (r) => (r.building === "C" ? 0.9 : 0.5)).map((x) => x.row.building)).toEqual(["C", "A", "B"]);
  });

  it("shows one day as a ranked BarList of 44 px links (Sunday hidden without data), heatmap cells gone", async () => {
    wrap(<UtilisationHeatmap data={summary()} week={3} />);
    expect(screen.queryByRole("table")).toBeNull();
    const days = within(screen.getByTestId("heat-phone-col")).getAllByRole("tab");
    expect(days.map((d) => d.textContent)).toEqual(["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt"]);
    await userEvent.click(days[1]);
    const links = within(screen.getByRole("list")).getAllByRole("link");
    expect(links.map((l) => l.getAttribute("aria-label"))).toEqual(["C · Salı · 90%", "A · Salı · 40%", "B · Salı · 20%"]);
    expect(links[0]).toHaveAttribute("href", "/timetable?day=2&building=C");
    expect(links[0]).toHaveClass("pointer-coarse:min-h-11");
    expect(links[0]).toHaveTextContent("90%");
  });

  it("keeps the heatmap from 640 px", () => {
    media.phone = false;
    wrap(<UtilisationHeatmap data={summary()} week={3} />);
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.queryByTestId("heat-phone")).toBeNull();
  });
});

describe("BarList rows as links", () => {
  it("renders a row with href as one link spanning label, bar and value; others stay plain", () => {
    wrap(<BarList items={[{ key: "a", label: "A", value: 3, href: "/x", linkLabel: "A · 3" }, { key: "b", label: "B", value: 1 }]} />);
    const link = screen.getByRole("link", { name: "A · 3" });
    expect(link).toHaveAttribute("href", "/x");
    expect(link).toHaveClass("col-span-3", "grid-cols-subgrid");
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });
});

describe("/admin/roles booking permissions (phones)", () => {
  const catalogue = {
    system: { setup: [{ id: 1, name: "setup.roles", description: "Roles" }] },
    bookings: {
      room: [{ id: 2, name: "room.view", description: "View" }],
      book_single: [{ id: 3, name: "book_single.create", description: "Create" }],
      book_recur: [{ id: 4, name: "book_recur.create", description: "Create" }],
    },
  };

  it("groups single and recurring as 44 px labelled checkbox rows instead of the table", async () => {
    const onToggle = vi.fn();
    wrap(<PermissionMatrix catalogue={catalogue} value={new Set(["book_single.create"])} onToggle={onToggle} />, "en");
    expect(screen.queryByRole("table")).toBeNull();
    const groups = within(screen.getByTestId("perm-book-groups")).getAllByRole("group");
    expect(groups).toHaveLength(2);
    for (const g of groups) {
      const boxes = within(g).getAllByRole("checkbox");
      expect(boxes).toHaveLength(7);
      for (const b of boxes) expect(b.closest("label")).toHaveClass("min-h-11");
    }
    const single = within(groups[0]).getAllByRole("checkbox")[0];
    expect(single).toHaveAttribute("aria-checked", "true");
    expect(single.closest("label")).toHaveAttribute("data-permission", "book_single.create");
    await userEvent.click(within(groups[1]).getAllByRole("checkbox")[0]);
    expect(onToggle).toHaveBeenCalledWith("book_recur.create", true);
  });

  it("keeps the single / recurring table from 640 px", () => {
    media.phone = false;
    wrap(<PermissionMatrix catalogue={catalogue} value={new Set()} onToggle={() => {}} />, "en");
    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.queryByTestId("perm-book-groups")).toBeNull();
  });
});

describe("SegmentedControl measures even when the first-paint estimate folded it", () => {
  it("shows the track for the measurement, so seven short day names come back from the select fallback", () => {
    // jsdom has no layout: the measured track is 270 px, rendered (offsetParent set)
    const rect = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      return { width: this.dataset.part === "track" && this.style.display === "inline-grid" ? 270 : 0, height: 0, x: 0, y: 0, top: 0, left: 0, right: 0, bottom: 0, toJSON: () => ({}) } as DOMRect;
    });
    const parent = vi.spyOn(HTMLElement.prototype, "offsetParent", "get").mockReturnValue(document.body);
    const days = ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"];
    const { container } = render(<SegmentedControl fill aria-label="Gün" options={days.map((d) => ({ value: d, label: d }))} />);
    const wrapper = container.querySelector<HTMLElement>("[data-slot=segmented-control]")!;
    // the estimate (6 + 7 × (24 + 3 × 7.6) = 334 px) would have folded it on a 326 px card
    expect(wrapper.style.getPropertyValue("--seg-w")).toBe("270px");
    // the inline display used for the measurement is gone again (the container query decides)
    expect(container.querySelector<HTMLElement>("[data-part=track]")!.style.display).toBe("");
    rect.mockRestore();
    parent.mockRestore();
  });
});
