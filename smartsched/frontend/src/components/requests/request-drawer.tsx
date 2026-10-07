"use client";

import { Lock, Unlock } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { NativeSelect } from "@/components/common/native-select";
import { StatusBadge } from "@/components/common/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useRooms, useUpdateExam, useUpdateMeeting } from "@/lib/api/hooks";
import type { ExamRequest, MeetingRequest, RoomTag } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { PERIODS, dayName } from "@/lib/time";
import { SeverityIcon } from "@/components/import/parse-warnings-table";
import { STATUS_KIND } from "./requests-view";

const TAGS: RoomTag[] = ["TIP", "PC", "LAB", "AMPHI"];

export function RequestDrawer({ meeting, exam, onClose }: { meeting: MeetingRequest | null; exam: ExamRequest | null; onClose: () => void }) {
  const { t, locale } = useI18n();
  const open = meeting !== null || exam !== null;
  const update = useUpdateMeeting();
  const updateExam = useUpdateExam();
  const rooms = useRooms();
  const [form, setForm] = useState<Partial<MeetingRequest>>({});
  useEffect(() => {
    if (meeting) setForm({ day: meeting.day, start_period: meeting.start_period, end_period: meeting.end_period, enrolment: meeting.enrolment, requested_room_ids: meeting.requested_room_ids, requested_building: meeting.requested_building, requested_tags: meeting.requested_tags, requested_capacity: meeting.requested_capacity, flexible_day: meeting.flexible_day, status: meeting.status, notes: meeting.notes });
  }, [meeting]);

  const save = async () => {
    if (!meeting) return;
    await update.mutateAsync({ id: meeting.id, body: { ...form, status: form.status === "NEEDS_REVIEW" ? "PARSED" : form.status } });
    toast.success(t("requests.saved"));
    onClose();
  };
  const toggleLock = async () => {
    if (meeting) {
      await update.mutateAsync({ id: meeting.id, body: { status: meeting.status === "LOCKED" ? "PARSED" : "LOCKED" } });
    } else if (exam) {
      await updateExam.mutateAsync({ id: exam.id, body: { status: exam.status === "LOCKED" ? "PARSED" : "LOCKED" } });
    }
    toast.success(t("requests.saved"));
  };
  const item = meeting ?? exam;
  const warnings = item?.parse_warnings ?? [];
  const preferred = new Set(form.requested_room_ids ?? []);

  return (
    <Sheet open={open} onOpenChange={(o) => { if (!o) onClose(); }}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-[440px]" data-testid="request-drawer">
        {item ? (
          <>
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2"><span className="font-mono">{item.course_code}</span> <StatusBadge kind={STATUS_KIND[item.status]} label={t(`requests.status.${item.status}`)} /></SheetTitle>
              <SheetDescription>{item.course_name} · {item.program_name}</SheetDescription>
            </SheetHeader>
            <div className="space-y-4 px-4">
              <Button variant="outline" size="sm" onClick={() => void toggleLock()} data-testid="toggle-lock">
                {item.status === "LOCKED" ? <><Unlock /> {t("requests.unlockRow")}</> : <><Lock /> {t("requests.lockRow")}</>}
              </Button>
              {warnings.length > 0 ? (
                <div className="rounded-md border border-status-warning-border bg-status-warning/40 p-2 text-xs">
                  <p className="mb-1 font-medium">{t("requests.parseWarnings")}</p>
                  <ul className="space-y-1">{warnings.map((w, i) => <li key={i} className="flex gap-1.5"><SeverityIcon severity={w.severity} className="mt-0.5 shrink-0" /><span><span className="font-medium">{w.field}:</span> {w.message}</span></li>)}</ul>
                </div>
              ) : null}
              {meeting ? (
                <form className="grid gap-3" onSubmit={(e) => { e.preventDefault(); void save(); }}>
                  <div className="grid grid-cols-3 gap-2">
                    <div className="grid gap-1"><Label htmlFor="rq-day">{t("common.day")}</Label>
                      <NativeSelect id="rq-day" value={form.day ?? ""} onChange={(e) => setForm({ ...form, day: e.target.value ? Number(e.target.value) : null })}>
                        <option value="">—</option>{[1, 2, 3, 4, 5, 6, 7].map((d) => <option key={d} value={d}>{dayName(d, locale, "short")}</option>)}
                      </NativeSelect></div>
                    <div className="grid gap-1"><Label htmlFor="rq-start">P{t("common.period").slice(0, 0)}start</Label>
                      <NativeSelect id="rq-start" value={form.start_period ?? ""} onChange={(e) => setForm({ ...form, start_period: e.target.value ? Number(e.target.value) : null })}>
                        <option value="">—</option>{PERIODS.map((p) => <option key={p.index} value={p.index}>P{p.index} {p.start}</option>)}
                      </NativeSelect></div>
                    <div className="grid gap-1"><Label htmlFor="rq-end">end</Label>
                      <NativeSelect id="rq-end" value={form.end_period ?? ""} onChange={(e) => setForm({ ...form, end_period: e.target.value ? Number(e.target.value) : null })}>
                        <option value="">—</option>{PERIODS.map((p) => <option key={p.index} value={p.index}>P{p.index} {p.end}</option>)}
                      </NativeSelect></div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div className="grid gap-1"><Label htmlFor="rq-enrol">{t("requests.enrolment")}</Label><Input id="rq-enrol" type="number" value={form.enrolment ?? ""} onChange={(e) => setForm({ ...form, enrolment: e.target.value ? Number(e.target.value) : null })} /></div>
                    <div className="grid gap-1"><Label htmlFor="rq-cap">{t("requests.capacity")}</Label><Input id="rq-cap" type="number" value={form.requested_capacity ?? ""} onChange={(e) => setForm({ ...form, requested_capacity: e.target.value ? Number(e.target.value) : null })} /></div>
                  </div>
                  <div className="grid gap-1">
                    <Label>{t("requests.tags")}</Label>
                    <div className="flex gap-1">{TAGS.map((tg) => { const on = form.requested_tags?.includes(tg); return <button key={tg} type="button" aria-pressed={on} onClick={() => setForm({ ...form, requested_tags: on ? (form.requested_tags ?? []).filter((x) => x !== tg) : [...(form.requested_tags ?? []), tg] })} className={`rounded-full border px-2.5 py-1 text-xs ${on ? "bg-primary text-primary-foreground" : "hover:bg-accent"}`}>{tg}</button>; })}</div>
                  </div>
                  <div className="grid gap-1">
                    <Label htmlFor="rq-building">{t("common.building")}</Label>
                    <NativeSelect id="rq-building" value={form.requested_building ?? ""} onChange={(e) => setForm({ ...form, requested_building: e.target.value || null })}>
                      <option value="">—</option>{["A", "B", "C", "D"].map((b) => <option key={b} value={b}>{b}</option>)}
                    </NativeSelect>
                  </div>
                  <div className="grid gap-1">
                    <Label>{t("requests.preferredRooms")}</Label>
                    <div className="flex max-h-28 flex-wrap gap-1 overflow-y-auto rounded-md border p-2">
                      {(rooms.data ?? []).filter((r) => r.is_bookable).map((r) => (
                        <button key={r.id} type="button" aria-pressed={preferred.has(r.id)} onClick={() => { const next = new Set(preferred); if (next.has(r.id)) next.delete(r.id); else next.add(r.id); setForm({ ...form, requested_room_ids: [...next] }); }} className={`rounded border px-1.5 py-0.5 font-mono text-[11px] ${preferred.has(r.id) ? "bg-primary text-primary-foreground" : "hover:bg-accent"}`}>{r.display_name}</button>
                      ))}
                    </div>
                  </div>
                  <label className="flex items-center justify-between gap-2 text-sm"><span>{t("requests.flexibleDay")}</span><Switch checked={form.flexible_day ?? false} onCheckedChange={(v) => setForm({ ...form, flexible_day: v })} /></label>
                  <div className="grid gap-1"><Label htmlFor="rq-notes">{t("requests.notes")}</Label><Textarea id="rq-notes" rows={2} value={form.notes ?? ""} onChange={(e) => setForm({ ...form, notes: e.target.value || null })} /></div>
                  {meeting.requested_room_text ? <p className="text-xs text-muted-foreground">{t("requests.sourceRow")}: “{meeting.requested_room_text}” · {meeting.start_time ?? ""}–{meeting.end_time ?? ""} · {meeting.instructor}</p> : null}
                  <SheetFooter className="px-0">
                    <Button type="submit" disabled={update.isPending} data-testid="request-save">{t("common.save")}</Button>
                    <Button type="button" variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
                  </SheetFooter>
                </form>
              ) : exam ? (
                <dl className="grid grid-cols-2 gap-x-3 gap-y-2 text-sm">
                  <dt className="text-muted-foreground">{t("requests.date")}</dt><dd>{exam.date ?? "—"}</dd>
                  <dt className="text-muted-foreground">{t("requests.time")}</dt><dd>{exam.start_time ?? "—"}–{exam.end_time ?? ""}</dd>
                  <dt className="text-muted-foreground">{t("requests.enrolment")}</dt><dd>{exam.enrolment ?? "—"}</dd>
                  <dt className="text-muted-foreground">{t("requests.instructor")}</dt><dd>{exam.instructor_text ?? "—"}</dd>
                  <dt className="text-muted-foreground">{t("requests.venue")}</dt><dd>{exam.requested_venue_text ?? "—"}</dd>
                  <dt className="text-muted-foreground">{t("requests.tags")}</dt><dd className="flex gap-1">{exam.requested_tags.map((tg) => <Badge key={tg} variant="outline">{tg}</Badge>)}</dd>
                </dl>
              ) : null}
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
