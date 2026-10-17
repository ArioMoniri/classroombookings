"use client";
/**
 * The checklist when the sidebar pill is not there: the full-screen list on phones (from the first row of "Daha" or
 * Yardım › Başlarken listesi; sticky header "Başlarken · 2 / 5", 64 px rows) and a side sheet on desktop when the
 * list was hidden ("Gizle" → it returns via Yardım › Başlarken listesi, spec §4.3).
 */
import { useRef } from "react";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useMediaQuery } from "@/components/ui/use-media-query";
import { useI18n } from "@/lib/i18n/provider";
import { useWelcomeStore } from "../welcome-store";
import { ChecklistAllDone, ChecklistProgress, ChecklistRows, useChecklistActions, useChecklistModel } from "./checklist-list";
import { Button } from "@/components/ui/button";

export const DESKTOP = "(min-width: 1024px)";

export function ChecklistSheet() {
  const { t } = useI18n();
  const model = useChecklistModel();
  const open = useWelcomeStore((s) => s.checklistOpen);
  const setOpen = useWelcomeStore((s) => s.setChecklistOpen);
  const desktop = useMediaQuery(DESKTOP);
  const actions = useChecklistActions();
  const heading = useRef<HTMLHeadingElement>(null);
  // desktop with a visible pill: the pill's popover is the panel
  const pillShown = desktop && !!model && !model.hidden;
  if (!model || pillShown) return null;
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side={desktop ? "right" : "bottom"} initialFocus={heading} className="gap-0 p-0 max-sm:data-[side=bottom]:max-h-dvh max-sm:data-[side=bottom]:h-dvh max-sm:data-[side=bottom]:rounded-none" data-testid="checklist-sheet">
        <SheetHeader className="sticky top-0 z-10 gap-2 bg-(--mat-chrome-solid) px-4 pt-3 pb-3 hairline-b">
          <SheetTitle ref={heading} tabIndex={-1} className="type-title-3 text-left outline-hidden">
            {t("welcome.check.title")} · <span className="tabular-nums">{model.done} / {model.total}</span>
          </SheetTitle>
          <SheetDescription className="sr-only">{t("welcome.check.progress", { done: model.done, total: model.total })}</SheetDescription>
          <ChecklistProgress model={model} />
        </SheetHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-2 py-3" data-testid="checklist-panel">
          {model.allDone ? <ChecklistAllDone /> : null}
          <ChecklistRows model={model} phone={!desktop} onNavigate={() => setOpen(false)} />
          {model.hidden ? null : (
            <div className="px-2">
              <Button variant="secondary" className="min-h-11" onClick={actions.hide} data-testid="checklist-hide">
                {t("welcome.check.hide")}
              </Button>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
