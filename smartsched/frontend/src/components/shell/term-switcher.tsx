"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Check, ChevronsUpDown } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useTerms } from "@/lib/api/hooks";
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
export function useActiveTerm() {
  const terms = useTerms();
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

export function TermSwitcher({ collapsed }: { collapsed: boolean }) {
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
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <button
            type="button"
            aria-label={`${t("nav.term")}: ${term?.name ?? "…"}. ${t("nav.switchTerm")}`}
            data-testid="term-switcher"
            className={cn(
              "flex w-full items-center gap-2 rounded-xl bg-fill-3 px-2.5 py-1.5 text-left outline-none shadow-[inset_0_0_0_1px_var(--hairline)] transition-colors duration-(--dur-fast) hover:bg-fill-2 focus-visible:outline-2 focus-visible:outline-(--focus)",
              collapsed && "justify-center px-0",
            )}
          >
            {collapsed ? (
              <span className="type-caption text-label-1">{term?.code.split("-")[1]?.slice(0, 2) ?? "—"}</span>
            ) : (
              <>
                <span className="min-w-0 flex-1">
                  <span className="type-headline block truncate text-label-1">{term?.name ?? "…"}</span>
                  <span className="type-footnote block truncate text-label-3">{term ? kindLabel(term.kind) : " "}</span>
                </span>
                <ChevronsUpDown className="size-3.5 shrink-0 text-label-3" aria-hidden />
              </>
            )}
          </button>
        }
      />
      <PopoverContent align="start" side={collapsed ? "right" : "bottom"} className="w-72 p-1.5">
        <p className="px-2.5 pt-1 pb-1.5 text-[11px] font-semibold text-label-3">{t("nav.switchTerm")}</p>
        {years.map((year) => (
          <div key={year} role="group" aria-label={year} className="pb-1">
            <p className="px-2.5 pt-1 text-[11px] font-semibold text-label-3">{year}</p>
            <ul>
              {terms
                .filter((x) => x.start_date.startsWith(year))
                .map((x) => (
                  <li key={x.id}>
                    <button
                      type="button"
                      aria-current={x.id === term?.id ? "true" : undefined}
                      className="flex w-full items-center gap-2 rounded-[10px] px-2.5 py-1.5 text-left outline-none hover:bg-fill-2 focus-visible:bg-fill-2"
                      onClick={() => choose(x)}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block text-[13px] font-medium text-label-1">{x.name}</span>
                        <span className="block text-[12px] text-label-3">
                          {kindLabel(x.kind)} · {formatDate(x.start_date, locale)} · {t("glass.term.weeks", { n: x.week_count })}
                        </span>
                      </span>
                      {x.id === term?.id ? <Check className="size-4 text-tint-text" aria-hidden /> : <span className="size-4" />}
                    </button>
                  </li>
                ))}
            </ul>
          </div>
        ))}
      </PopoverContent>
    </Popover>
  );
}
