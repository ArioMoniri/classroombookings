"use client";

import { Check, ChevronsUpDown } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useTerms } from "@/lib/api/hooks";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { useUiStore } from "@/stores/ui";
import { useHydrated } from "@/lib/use-hydrated";

export function useActiveTerm() {
  const terms = useTerms();
  const termId = useUiStore((s) => s.termId);
  const active = terms.data?.find((t) => t.id === termId) ?? terms.data?.find((t) => t.is_active) ?? terms.data?.[0];
  return { term: active, terms: terms.data ?? [], isLoading: terms.isLoading };
}

export function TermSwitcher({ collapsed }: { collapsed: boolean }) {
  const { t } = useI18n();
  const hydrated = useHydrated();
  const active = useActiveTerm();
  const term = hydrated ? active.term : undefined;
  const terms = active.terms;
  const setTermId = useUiStore((s) => s.setTermId);
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const years = [...new Set(terms.map((x) => x.start_date.slice(0, 4)))].sort();
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`${t("nav.term")}: ${term?.name ?? "…"}. ${t("nav.switchTerm")}`}
        data-testid="term-switcher"
        className={cn("flex w-full items-center gap-2 rounded-md border bg-background px-2 py-1.5 text-left text-sm hover:bg-accent", collapsed && "justify-center px-0")}
      >
        {collapsed ? (
          <span className="font-mono text-xs font-semibold">{term?.code.split("-")[1]?.slice(0, 2) ?? "—"}</span>
        ) : (
          <>
            <span className="flex-1 truncate font-medium">{term?.name ?? "…"}</span>
            {term ? <Badge variant="secondary" className="text-[10px]">{term.kind}</Badge> : null}
            <ChevronsUpDown className="size-3.5 text-muted-foreground" aria-hidden />
          </>
        )}
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{t("nav.switchTerm")}</DialogTitle>
            <DialogDescription className="sr-only">{t("nav.term")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            {years.map((year) => (
              <div key={year}>
                <p className="mb-1 text-[11px] font-medium uppercase text-muted-foreground">{year}</p>
                <ul className="space-y-0.5">
                  {terms
                    .filter((x) => x.start_date.startsWith(year))
                    .map((x) => (
                      <li key={x.id}>
                        <button
                          type="button"
                          className={cn("flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent", x.id === term?.id && "bg-accent")}
                          onClick={() => {
                            setTermId(x.id);
                            void qc.invalidateQueries({ predicate: (q) => q.queryKey.includes("term") });
                            setOpen(false);
                            toast(t("nav.switched", { term: x.name }));
                          }}
                        >
                          <span className="flex-1">{x.name}</span>
                          <Badge variant="outline" className="text-[10px]">{x.kind}</Badge>
                          {x.id === term?.id ? <Check className="size-4 text-primary" aria-hidden /> : <span className="size-4" />}
                        </button>
                      </li>
                    ))}
                </ul>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
