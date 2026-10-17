"use client";
/**
 * Sidebar-footer pill "Başlarken 2 / 5" with a bar and "Sıradaki: …" (spec §4.3). A button (`aria-expanded`,
 * `aria-controls`) that opens a 420 px popover panel. In the 72 px icon rail it is a round progress button.
 * Hidden when the list is hidden, switched off, or empty. Not a floating launcher (Liquid Glass G1).
 */
import { ListChecks } from "lucide-react";
import { useId } from "react";
import { BareButton } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useI18n } from "@/lib/i18n/provider";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";
import { itemKey } from "../content";
import { useWelcomeStore } from "../welcome-store";
import { ChecklistPanel, useChecklistModel } from "./checklist-list";

export function ChecklistPill({ collapsed }: { collapsed?: boolean }) {
  const { t } = useI18n();
  const hydrated = useHydrated();
  const model = useChecklistModel();
  const open = useWelcomeStore((s) => s.checklistOpen);
  const setOpen = useWelcomeStore((s) => s.setChecklistOpen);
  const panelId = useId();
  if (!hydrated || !model || model.hidden) return null;
  const label = t("welcome.check.pillLabel", { done: model.done, total: model.total });
  const ratio = model.total ? model.done / model.total : 0;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <BareButton
            aria-label={label}
            aria-expanded={open}
            aria-controls={open ? panelId : undefined}
            data-testid="checklist-pill"
            className={cn(
              "w-full rounded-xl bg-fill-3 text-left outline-hidden hover:bg-fill-2 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)",
              collapsed ? "flex size-11 items-center justify-center p-0" : "flex flex-col gap-1.5 px-3 py-2.5",
            )}
          >
            {collapsed ? (
              <span aria-hidden className="relative flex size-8 items-center justify-center rounded-full" style={{ background: `conic-gradient(var(--tint) ${ratio * 360}deg, var(--fill-1) 0)` }}>
                <span className="flex size-6 items-center justify-center rounded-full bg-(--mat-chrome-solid)">
                  <ListChecks className="size-3.5 text-label-1" />
                </span>
              </span>
            ) : (
              <>
                <span aria-hidden className="flex items-center justify-between gap-2 type-footnote font-semibold text-label-1">
                  <span>{t("welcome.check.title")}</span>
                  <span className="tabular-nums">
                    {model.done} / {model.total}
                  </span>
                </span>
                <span aria-hidden className="h-1 w-full overflow-hidden rounded-full bg-fill-1">
                  <span className="block h-full w-full origin-left rounded-full bg-tint transition-transform duration-(--dur-slow) motion-reduce:transition-none" style={{ transform: `scaleX(${ratio})` }} />
                </span>
                {model.next ? (
                  <span aria-hidden className="block truncate type-caption text-label-3">
                    {t("welcome.check.next", { item: t(itemKey(model.next.key, "title")) })}
                  </span>
                ) : null}
              </>
            )}
          </BareButton>
        }
      />
      <PopoverContent id={panelId} side={collapsed ? "right" : "top"} align="start" className="w-[420px] max-w-[calc(100vw-1rem)] p-4">
        <ChecklistPanel model={model} onNavigate={() => setOpen(false)} />
      </PopoverContent>
    </Popover>
  );
}
