"use client";
/**
 * Profil › Takvim (CAL-08): the "Takvimime ekle" button, the sheet and the manage list. Also resumes a push approval
 * after the provider's OAuth round trip: the sheet stored the scope in sessionStorage before leaving; back on
 * /profile?calendar=connected the scope is applied (PUT /calendar/connectors/{p}/scopes, idempotent) and the sheet
 * reopens on its progress state. `?calendar=error` drops the stored scope.
 */
import { CalendarPlus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { SectionTitle } from "@/components/admin/kit";
import { calendarExportApi, useExportOptions, useRefreshCalendar } from "@/lib/api/calendar-export";
import { useI18n } from "@/lib/i18n/provider";
import { CalendarExportSheet } from "./export-sheet";
import { CalendarExportManage } from "./manage-list";
import { PENDING_KEY, pushScope, readPending, type PendingPush } from "./model";

/** Reads (and clears) the pending push after the OAuth round trip; null when there is none or it failed. */
function takePending(): { pending: PendingPush | null; failed: boolean } {
  if (typeof window === "undefined") return { pending: null, failed: false };
  let raw: string | null = null;
  try {
    raw = window.sessionStorage.getItem(PENDING_KEY);
  } catch {
    return { pending: null, failed: false };
  }
  const pending = readPending(raw);
  const result = new URLSearchParams(window.location.search).get("calendar");
  if (!pending || (result !== "connected" && result !== "error")) return { pending: null, failed: false };
  try {
    window.sessionStorage.removeItem(PENDING_KEY);
  } catch {
    /* ignore */
  }
  return result === "connected" ? { pending, failed: false } : { pending: null, failed: true };
}

export function CalendarExportSection() {
  const { t } = useI18n();
  const options = useExportOptions();
  const refresh = useRefreshCalendar();
  const [open, setOpen] = useState(false);
  const [resume, setResume] = useState<PendingPush | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const took = useRef(false);

  useEffect(() => {
    if (took.current) return;
    took.current = true;
    const { pending } = takePending();
    if (!pending) return;
    const scope = pushScope(pending.kind, pending.departmentId);
    void calendarExportApi
      .pushScopes(pending.provider, [scope])
      .catch(() => undefined)
      .finally(() => {
        void refresh();
        setResume(pending);
        setOpen(true);
      });
  }, [refresh]);

  const enabled = options.data?.enabled !== false;
  return (
    <section aria-labelledby="pf-calendar-export" id="calendar" className="scroll-mt-20" data-testid="cal-section">
      <SectionTitle id="pf-calendar-export">{t("calendarExport.section")}</SectionTitle>
      <Card variant="glass" className="gap-3 px-4">
        <p className="type-callout text-label-2">{enabled ? t("calendarExport.lead") : t("calendarExport.off")}</p>
        {enabled ? (
          <div>
            <Button ref={buttonRef} onClick={() => setOpen(true)} className="pointer-coarse:min-h-11" data-testid="cal-open">
              <CalendarPlus aria-hidden />
              {t("calendarExport.open")}
            </Button>
          </div>
        ) : null}
        {enabled ? <CalendarExportManage fallbackFocus={buttonRef} /> : null}
      </Card>
      <CalendarExportSheet
        open={open}
        resume={resume}
        onOpenChange={(o) => {
          setOpen(o);
          if (!o) setResume(null);
        }}
      />
    </section>
  );
}

/**
 * A "Takvime ekle" button that opens the same sheet, for the academician's own classes / requests view
 * (`/moderation` "me" view, P19-T1) and other entry points: one import and one line.
 */
export function CalendarExportButton({ variant = "outline", className }: { variant?: "outline" | "secondary" | "default"; className?: string }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant={variant} size="sm" className={className ?? "pointer-coarse:min-h-11"} onClick={() => setOpen(true)} data-testid="cal-open-button">
        <CalendarPlus aria-hidden />
        {t("calendarExport.openShort")}
      </Button>
      <CalendarExportSheet open={open} onOpenChange={setOpen} />
    </>
  );
}
