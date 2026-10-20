"use client";
/**
 * Yardım (spec §4.4, wireframe welcome-hints-help.svg C): the user menu group ("Turu yeniden başlat", "Başlarken
 * listesi 2 / 5", "Yenilikler"; the existing "Klavye kısayolları" entry stays where it is), the ⌘K commands, and the
 * phone "Daha" rows (the checklist as the first row, 92 px, then the help rows).
 *
 * `assistant`: a slot at the top of the group for the AI helper's "Yardımcıya sor" row (components/shell/ask-helper.tsx).
 */
import { ListChecks, Megaphone, RotateCcw } from "lucide-react";
import type { ReactNode } from "react";
import { BareButton } from "@/components/ui/button";
import { DropdownMenuGroup, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";
import { useWelcomeRestart } from "@/lib/api/welcome";
import { useI18n } from "@/lib/i18n/provider";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";
import { itemKey } from "./content";
import { buildSteps } from "./model";
import { useChecklistModel, useWelcomeData } from "./checklist/checklist-list";
import { openWhatsNew, useWelcomeStore } from "./welcome-store";

/** Restart (POST /welcome/restart, then the sheet; the tour alone when the sheet is switched off) and open the checklist. */
export function useWelcomeActions() {
  const data = useWelcomeData();
  const restart = useWelcomeRestart();
  const openSheet = useWelcomeStore((s) => s.openSheet);
  const startTour = useWelcomeStore((s) => s.startTour);
  const setChecklistOpen = useWelcomeStore((s) => s.setChecklistOpen);
  const available = !!data && (data.enabled.sheet || data.enabled.tour);
  return {
    available,
    checklistAvailable: !!data?.enabled.checklist && (data.checklist.items.length > 0 || data.audiences.length > 0),
    restart: async () => {
      let state = data;
      try {
        state = await restart.mutateAsync();
      } catch {
        /* the server keeps its state; the sheet still opens from the cached payload */
      }
      if (!state) return;
      if (state.enabled.sheet) openSheet({ mode: "restart", kind: "sheet" });
      else if (state.enabled.tour) startTour({ steps: buildSteps(state) });
    },
    openChecklist: () => setChecklistOpen(true),
  };
}

/** The user menu's Yardım group (Base UI menu: the label sits inside the group). */
/** `whatsNew={false}` where the header already carries the "Yenilikler" button (the account menu): one entry each. */
export function HelpMenuGroup({ assistant, whatsNew = true }: { assistant?: ReactNode; whatsNew?: boolean }) {
  const { t } = useI18n();
  const hydrated = useHydrated();
  const actions = useWelcomeActions();
  const model = useChecklistModel();
  if (!hydrated) return null;
  return (
    <>
      <DropdownMenuSeparator />
      <DropdownMenuGroup>
        <DropdownMenuLabel>{t("welcome.help.group")}</DropdownMenuLabel>
        {assistant}
        {actions.available ? (
          <DropdownMenuItem onClick={() => void actions.restart()} data-testid="help-restart-tour">
            <RotateCcw /> {t("welcome.help.restart")}
          </DropdownMenuItem>
        ) : null}
        {model ? (
          <DropdownMenuItem onClick={actions.openChecklist} data-testid="help-checklist">
            <ListChecks /> {t("welcome.help.checklistCount", { done: model.done, total: model.total })}
          </DropdownMenuItem>
        ) : null}
        {whatsNew ? (
          <DropdownMenuItem onClick={() => window.setTimeout(openWhatsNew, 0)} data-testid="help-whats-new">
            <Megaphone /> {t("welcome.help.whatsNew")}
          </DropdownMenuItem>
        ) : null}
      </DropdownMenuGroup>
    </>
  );
}

/** ⌘K commands, in the palette's `actions` shape. */
export interface WelcomeCommand {
  value: string;
  icon: typeof RotateCcw;
  label: string;
  keys?: string[];
  run: () => void;
  words: string;
  allowed: boolean;
}
export function useWelcomeCommands(): WelcomeCommand[] {
  const { t } = useI18n();
  const actions = useWelcomeActions();
  const model = useChecklistModel();
  const close = () => useUiStore.getState().setPaletteOpen(false);
  return [
    { value: "action-welcome-restart", icon: RotateCcw, label: t("welcome.help.restart"), run: () => { close(); void actions.restart(); }, words: t("welcome.help.restartWords"), allowed: actions.available },
    { value: "action-welcome-checklist", icon: ListChecks, label: t("welcome.help.checklist"), run: () => { close(); actions.openChecklist(); }, words: t("welcome.help.checklistWords"), allowed: !!model },
  ];
}

/** Phone "Daha": the checklist first (92 px), then Yardım (spec §4.3, §9). */
/**
 * `part`: the drawer puts the checklist card first and the Yardım rows after the navigation (login-navbar-2026-10:
 * destinations before help); "all" keeps both together.
 */
export function DrawerWelcomeRows({ onNavigate, assistant, part = "all" }: { onNavigate?: () => void; assistant?: ReactNode; part?: "all" | "checklist" | "help" }) {
  const { t } = useI18n();
  const hydrated = useHydrated();
  const actions = useWelcomeActions();
  const model = useChecklistModel();
  // the helper row (`assistant`) keeps the Yardım group even when the guide is off
  if (!hydrated || (!model && !actions.available && !assistant)) return null;
  const run = (fn: () => void) => () => {
    onNavigate?.();
    // after the drawer's close, so the next sheet is not opened inside a closing one
    window.setTimeout(fn, 180);
  };
  // the same row as the navigation above it (SidebarGlassItem in the drawer): 44 px, px-2.5, gap-2.5, 16 px glyphs
  const row = "flex min-h-11 w-full items-center gap-2.5 rounded-[10px] px-2.5 text-left type-callout font-medium text-label-1 outline-hidden hover:bg-fill-3 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus) [&_svg]:size-4 [&_svg]:shrink-0 [&_svg]:stroke-[1.75] [&_svg]:text-label-2";
  const checklist =
      model && !model.hidden ? (
        <BareButton onClick={run(actions.openChecklist)} className={cn(row, "min-h-[92px] flex-col items-stretch justify-center gap-1.5 rounded-xl bg-fill-3 px-3")} data-testid="drawer-checklist" aria-label={t("welcome.check.pillLabel", { done: model.done, total: model.total })}>
          <span aria-hidden className="flex items-center justify-between type-headline">
            <span>{t("welcome.check.title")}</span>
            <span className="tabular-nums">
              {model.done} / {model.total}
            </span>
          </span>
          <span aria-hidden className="h-1.5 w-full overflow-hidden rounded-full bg-fill-1">
            <span className="block h-full w-full origin-left rounded-full bg-tint" style={{ transform: `scaleX(${model.total ? model.done / model.total : 0})` }} />
          </span>
          {model.next ? (
            <span aria-hidden className="truncate type-footnote text-label-3">
              {t("welcome.check.next", { item: t(itemKey(model.next.key, "title")) })}
            </span>
          ) : null}
        </BareButton>
      ) : null;
  if (part === "checklist") return checklist ? <div className="flex flex-col px-2 pb-2" data-testid="drawer-welcome-checklist">{checklist}</div> : null;
  return (
    <div className="flex flex-col gap-px px-2 pb-2" data-testid="drawer-welcome">
      {part === "all" ? checklist : null}
      <p className="px-2.5 pt-2 pb-1 type-caption font-semibold tracking-[0.02em] text-label-3">{t("welcome.help.group")}</p>
      {assistant}
      {actions.available ? (
        <BareButton onClick={run(() => void actions.restart())} className={row} data-testid="help-restart-tour">
          <RotateCcw aria-hidden /> {t("welcome.help.restart")}
        </BareButton>
      ) : null}
      {model && model.hidden ? (
        <BareButton onClick={run(actions.openChecklist)} className={row} data-testid="help-checklist">
          <ListChecks aria-hidden /> {t("welcome.help.checklistCount", { done: model.done, total: model.total })}
        </BareButton>
      ) : null}
      <BareButton onClick={run(openWhatsNew)} className={row} data-testid="help-whats-new">
        <Megaphone aria-hidden /> {t("welcome.help.whatsNew")}
      </BareButton>
    </div>
  );
}
