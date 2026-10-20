"use client";

import { useQueryClient } from "@tanstack/react-query";
import { CalendarRange, Check, ChevronsUpDown } from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useTerms } from "@/lib/api/hooks";
import { usePermissions } from "@/lib/api/shell-extra";
import type { Term } from "@/lib/api/schemas";
import { useI18n } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/time";
import { useHydrated } from "@/lib/use-hydrated";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";
import { currentTermByDate, useRememberedTermId } from "./workspace";

/**
 * The term every page works on: the one picked in this session, else the one this user last used
 * (workspace memory), else the **current term by date** (not the last imported, usability M1).
 */
export function useActiveTerm(opts: { enabled?: boolean } = {}) {
  const terms = useTerms({ enabled: opts.enabled });
  const termId = useUiStore((s) => s.termId);
  const [remembered] = useRememberedTermId();
  const list = terms.data ?? [];
  const active = list.find((t) => t.id === termId) ?? list.find((t) => t.id === remembered) ?? currentTermByDate(list) ?? list.find((t) => t.is_active) ?? list[0];
  return { term: active, terms: list, isLoading: terms.isLoading };
}

/** Planner words for term kinds (no raw "REGULAR" / "FINAL" enum in the UI, usability m1). */
export function useTermKindLabel() {
  const { t } = useI18n();
  return (kind: Term["kind"]) => t(`glass.term.kind.${kind}`);
}

/** Terms are planning data (GET /terms needs planning.view): people without it get no switcher (and no 403). */
export function TermSwitcher({ collapsed }: { collapsed: boolean }) {
  const { can } = usePermissions();
  // never on the server or the first client render: /auth/me can arrive while the sidebar's Suspense boundary
  // hydrates, and a button the server did not render is React error #418 (/classes, /timetable)
  const hydrated = useHydrated();
  if (!hydrated || !can("planning.view")) return null;
  return <TermSwitcherInner collapsed={collapsed} />;
}

function TermSwitcherInner({ collapsed }: { collapsed: boolean }) {
  const { t, locale } = useI18n();
  const hydrated = useHydrated();
  const active = useActiveTerm();
  const term = hydrated ? active.term : undefined;
  const terms = active.terms;
  const setTermId = useUiStore((s) => s.setTermId);
  const [, remember] = useRememberedTermId();
  const kindLabel = useTermKindLabel();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const years = [...new Set(terms.map((x) => x.start_date.slice(0, 4)))].sort().reverse();
  const choose = (x: Term) => {
    setTermId(x.id);
    remember(x.id);
    void qc.invalidateQueries({ predicate: (q) => q.queryKey.includes("term") });
    setOpen(false);
    toast(t("nav.switched", { term: x.name }));
  };
  const trigger = (
    <Button
      variant="ghost"
      aria-label={`${t("nav.term")}: ${term?.name ?? "…"}. ${t("nav.switchTerm")}`}
      data-testid="term-switcher"
      className={cn(
        "h-auto w-full justify-start gap-2 rounded-xl bg-fill-3 px-2.5 py-1.5 text-left font-normal whitespace-normal edge-hairline hover:bg-fill-2 active:not-aria-[haspopup]:scale-100",
        // the rail: a 40 px calendar button; the term's full name is its tooltip (a two-letter "GU" said nothing)
        collapsed && "mx-auto size-10 justify-center px-0 py-0 [&_svg]:size-4",
      )}
    >
      {collapsed ? (
        <CalendarRange aria-hidden className="text-label-1" />
      ) : (
        <>
          <span className="min-w-0 flex-1">
            <span className="type-headline block truncate text-label-1">{term?.name ?? "…"}</span>
            <span className="type-footnote block truncate text-label-3">{term ? kindLabel(term.kind) : " "}</span>
          </span>
          <ChevronsUpDown className="size-3.5 shrink-0 text-label-3" aria-hidden />
        </>
      )}
    </Button>
  );
  return (
    <Popover open={open} onOpenChange={setOpen}>
      {collapsed ? (
        <Tooltip>
          <PopoverTrigger render={<TooltipTrigger render={trigger} />} />
          <TooltipContent side="right">
            {term ? `${term.name} · ${kindLabel(term.kind)}` : t("nav.term")}
          </TooltipContent>
        </Tooltip>
      ) : (
        <PopoverTrigger render={trigger} />
      )}
      <PopoverContent align="start" side={collapsed ? "right" : "bottom"} className="w-72 p-1.5">
        <p className="px-2.5 pt-1 pb-1.5 type-caption font-semibold text-label-3">{t("nav.switchTerm")}</p>
        {years.map((year) => (
          <div key={year} role="group" aria-label={year} className="pb-1">
            <p className="px-2.5 pt-1 type-caption font-semibold text-label-3">{year}</p>
            <ul>
              {terms
                .filter((x) => x.start_date.startsWith(year))
                .map((x) => (
                  <li key={x.id}>
                    <Button
                      variant="ghost"
                      aria-current={x.id === term?.id ? "true" : undefined}
                      className="h-auto w-full justify-start gap-2 rounded-lg px-2.5 py-1.5 text-left font-normal whitespace-normal focus-visible:-outline-offset-2"
                      onClick={() => choose(x)}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block type-callout font-medium text-label-1">{x.name}</span>
                        <span className="block type-footnote text-label-3">
                          {kindLabel(x.kind)} · {formatDate(x.start_date, locale)} · {t("glass.term.weeks", { n: x.week_count })}
                        </span>
                      </span>
                      {x.id === term?.id ? <Check className="size-4 text-tint-text" aria-hidden /> : <span className="size-4" />}
                    </Button>
                  </li>
                ))}
            </ul>
          </div>
        ))}
      </PopoverContent>
    </Popover>
  );
}
