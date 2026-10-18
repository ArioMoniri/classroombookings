"use client";
/**
 * /admin/weeks: the timetable-week and term-week editors, for setup.timetable_weeks only. AS20-F09: a planner
 * (planning.edit) also reaches the page, for the season profile drafts below, and sees no week editor.
 */
import { usePermissions } from "@/lib/permissions";
import { TermWeeksEditor } from "./term-weeks-editor";
import { WeeksAdmin } from "./weeks-admin";

export function WeekEditors() {
  const { can } = usePermissions();
  if (!can(["setup.timetable_weeks"])) return null;
  return (
    <>
      <WeeksAdmin />
      {/* RF-09: the term's week calendar (Ders / Sınav / Tatil / Bütünleme per week) */}
      <TermWeeksEditor />
    </>
  );
}
