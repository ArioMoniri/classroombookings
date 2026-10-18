"use client";
/**
 * AS-17 exam hold mode `slots` (`PUT /booking-policies/exam-period {buffer_periods, slots_effect}`): only the exam
 * timetable's slots (± a buffer) are held in the exam rooms; the rest of the exam weeks stays bookable. The freed
 * room-periods come from `GET /analytics/forecast/exams` → `holds` of the newest exam term.
 */
import { useId } from "react";
import { toast } from "sonner";
import { SelectField } from "@/components/admin/kit";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { useExamForecast } from "@/lib/api/adaptive";
import { useSaveExamPeriod, type ExamPeriod } from "@/lib/api/booking-policies";
import { apiText } from "@/lib/api/seasons";
import { useI18n } from "@/lib/i18n/provider";

export function ExamSlotsOptions({ exam, termId }: { exam: ExamPeriod; termId: number | null }) {
  const { t, locale, n } = useI18n();
  const id = useId();
  const save = useSaveExamPeriod();
  const forecast = useExamForecast(termId);
  const holds = forecast.data?.holds;
  const ok = () => toast.success(t("policies.exam.saved"));
  const fail = (e: unknown) => toast.error(apiText(e, locale));
  return (
    <div className="flex flex-col gap-3 rounded-lg bg-fill-3 p-3" data-testid="exam-slots">
      <label className="flex flex-col gap-1.5 sm:flex-row sm:items-center sm:justify-between">
        <span className="min-w-0">
          <span className="block type-callout font-medium text-label-1">{t("adaptive.hold.buffer")}</span>
          <span className="block type-footnote text-label-2">{t("adaptive.hold.bufferHint")}</span>
        </span>
        <SelectField id={`${id}-buffer`} value={String(exam.buffer_periods)} onChange={(e) => save.mutate({ buffer_periods: Number(e.target.value) }, { onSuccess: ok, onError: fail })} className="sm:w-40" data-testid="exam-buffer">
          {[0, 1, 2, 3, 4].map((b) => (
            <option key={b} value={b}>{b === 0 ? t("adaptive.hold.bufferNone") : t("adaptive.hold.bufferN", { n: b })}</option>
          ))}
        </SelectField>
      </label>
      <div className="flex flex-col gap-1.5">
        <span id={`${id}-effect`} className="type-callout font-medium text-label-1">{t("adaptive.hold.effect")}</span>
        <SegmentedControl<"request" | "refuse">
          semantics="radiogroup"
          aria-labelledby={`${id}-effect`}
          value={exam.slots_effect}
          onValueChange={(v) => save.mutate({ slots_effect: v }, { onSuccess: ok, onError: fail })}
          options={[
            { value: "request", label: t("adaptive.hold.effectRequest"), testId: "exam-effect-request" },
            { value: "refuse", label: t("adaptive.hold.effectRefuse"), testId: "exam-effect-refuse" },
          ]}
        />
      </div>
      <p className="type-footnote text-label-2" data-testid="exam-freed">
        {holds && (holds.held_room_periods ?? 0) + (holds.freed_room_periods ?? 0) > 0
          ? t("adaptive.hold.freed", { freed: n(holds.freed_room_periods ?? 0), held: n(holds.held_room_periods ?? 0) })
          : t("adaptive.hold.noTimetable")}
      </p>
    </div>
  );
}
