/** HB-23c: the router's kinds → their Turkish-first labels (helper.file.kinds.*); no raw kind ever reaches the UI. */
import type { MessageKey } from "@/lib/i18n";

export const KIND_KEYS: Readonly<Record<string, MessageKey>> = {
  planning_list: "helper.file.kinds.planning_list",
  exam_list: "helper.file.kinds.exam_list",
  weekly_grid: "helper.file.kinds.weekly_grid",
  room_master: "helper.file.kinds.room_master",
  users_csv: "helper.file.kinds.users_csv",
  crbs_dump: "helper.file.kinds.crbs_dump",
  intake_json: "helper.file.kinds.intake_json",
  calendar_ics: "helper.file.kinds.calendar_ics",
  request_list: "helper.file.kinds.request_list",
  timetable_other: "helper.file.kinds.timetable_other",
  room_list: "helper.file.kinds.room_list",
  holidays: "helper.file.kinds.holidays",
  staff_list: "helper.file.kinds.staff_list",
  rules_doc: "helper.file.kinds.rules_doc",
  scan: "helper.file.kinds.scan",
};

/** kinds the İçe aktar screen reads from an Excel file (its wizard: planning / exam / weekly grid / room master) */
export const IMPORT_SCREEN_KINDS: ReadonlySet<string> = new Set(["planning_list", "exam_list", "weekly_grid", "room_master"]);
