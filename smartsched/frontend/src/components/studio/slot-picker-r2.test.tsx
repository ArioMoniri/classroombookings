/**
 * Round-2 lane E, T-R2-30 (R2-M-12): the pin template marks a room the class does not fit ('· sığmaz (100 > 30)'),
 * the course picker shows each meeting's day and time, and a 'Sığmaz' room in the move dialog is a hard issue (the
 * plain 'Taşı' is disabled, the force panel explains).
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "@/lib/i18n/provider";
import type { ClassRow } from "@/lib/api/studio-schemas";
import type { Room } from "@/lib/api/schemas";
import { capacityIssue } from "@/components/timetable/move-dialog";
import { SlotEditor, fitMark } from "./slot-picker";
import { StudioDataContext, fallbackSentence } from "./studio-data";

const room = (id: number, code: string, capacity: number): Room => ({ id, building_id: 1, building_code: "B", code, display_name: code, floor: 1, capacity, exam_capacity: capacity, tags: [], is_bookable: true });
const cls = (id: number, code: string, enrolment: number, day: number, time: string): ClassRow =>
  ({ id, kind: "COURSE", course_code: code, course_name: code, section_label: "1", program_name: "Hemşirelik", class_years: [], days: [day], day, start_period: 1, end_period: 2, time_label: time, weeks: [], enrolment, needs_room: true, is_evening: false, flexible_day: false, requested_room_ids: [], requested_room_codes: [] }) as unknown as ClassRow;

function wrap(ui: React.ReactNode, classes: ClassRow[]) {
  return render(
    <I18nProvider initialLocale="tr">
      <StudioDataContext.Provider value={{ rooms: [room(1, "B 201", 30), room(2, "C 403", 120)], classes, termWeeks: [], sentence: fallbackSentence, advanced: false }}>{ui}</StudioDataContext.Provider>
    </I18nProvider>,
  );
}

describe("T-R2-30: capacity in the pin template and the move dialog", () => {
  it("fitMark names the shortfall", () => {
    expect(fitMark(100, 30, "tr")).toBe("sığmaz (100 > 30)");
    expect(fitMark(100, 120, "tr")).toBeNull();
    expect(fitMark(null, 30, "tr")).toBeNull();
    expect(fitMark(100, 30, "en")).toBe("too small (100 > 30)");
  });

  it("the rooms field marks the rooms the chosen classes do not fit", () => {
    const classes = [cls(521, "ING 302", 100, 1, "Pzt 08:30–10:20"), cls(264, "ING 302", 100, 3, "Çar 13:30–15:20")];
    wrap(<SlotEditor field={{ name: "rooms", type: "rooms", param: "room_ids", required: true }} value={[1]} onChange={() => undefined} context={{ classIds: [521] }} />, classes);
    const small = screen.getByTestId("room-option-1");
    expect(small).toHaveTextContent("sığmaz (100 > 30)");
    expect(small).toHaveAttribute("data-fits", "0");
    expect(screen.getByTestId("room-option-2")).not.toHaveTextContent("sığmaz");
  });

  it("the course picker shows day and time, so two meetings of one course are told apart", () => {
    const classes = [cls(521, "ING 302", 100, 1, "Pzt 08:30–10:20"), cls(264, "ING 302", 100, 3, "Çar 13:30–15:20")];
    wrap(<SlotEditor field={{ name: "course", type: "courses", param: "event_ids", required: true }} value={[]} onChange={() => undefined} />, classes);
    expect(screen.getByTestId("course-option-521")).toHaveTextContent("Pzt 08:30–10:20");
    expect(screen.getByTestId("course-option-264")).toHaveTextContent("Çar 13:30–15:20");
  });

  it("a too-small target room is a hard issue of the move", () => {
    const issue = capacityIssue(100, { room_id: 1, code: "B 201", building: "B", capacity: 30, tags: [], status: "too_small" }, false);
    expect(issue?.code).toBe("capacity");
    expect(issue?.text.tr).toBe("100 öğrenci 30 kişilik B 201'e sığmaz");
    expect(capacityIssue(100, { room_id: 2, code: "C 403", building: "C", capacity: 120, tags: [], status: "free" }, false)).toBeNull();
    expect(capacityIssue(100, undefined, false)).toBeNull();
  });
});
