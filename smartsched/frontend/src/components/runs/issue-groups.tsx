"use client";

import { ChevronRight, Download } from "lucide-react";
import { useId, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { dataIssuesXlsxUrl, type DataIssueGroup, type DataIssueItem } from "@/lib/api/shell-extra";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import type { CollapsedDiagnosis } from "./diagnosis-format";
import { plannerText } from "./diagnosis-format";

/** Rule clashes come before data problems; the unplaced group is rendered as fix cards above. */
const RULE_GROUPS = ["locked_room_overlap", "locked_room_blocked", "shared_room_overflow"];
/** Shown above as cards with fixes (from run.diagnosis): unplaced classes and locked overlaps. */
export const UNPLACED_GROUPS = new Set(["no_free_room", "locked_room_overlap"]);

export function orderGroups(groups: DataIssueGroup[]): DataIssueGroup[] {
  return groups
    .filter((g) => g.count > 0 && !UNPLACED_GROUPS.has(g.code))
    .sort((a, b) => {
      const ra = RULE_GROUPS.includes(a.code) ? 0 : 1;
      const rb = RULE_GROUPS.includes(b.code) ? 0 : 1;
      return ra - rb || b.count - a.count;
    });
}

function Disclosure({ title, count, hint, children, defaultOpen = false, testId }: { title: string; count: number; hint?: string; children: ReactNode; defaultOpen?: boolean; testId?: string }) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  const { n } = useI18n();
  return (
    <section className="[&:not(:last-child)]:hairline-b" data-testid={testId}>
      <button type="button" aria-expanded={open} aria-controls={`${id}-body`} onClick={() => setOpen((v) => !v)} className="flex w-full items-start gap-2 py-3 text-left outline-none focus-visible:outline-2 focus-visible:outline-(--focus)">
        <ChevronRight className={cn("mt-0.5 size-4 shrink-0 text-label-3 transition-transform duration-(--dur-fast)", open && "rotate-90")} aria-hidden />
        <span className="min-w-0 flex-1">
          <span className="text-[13.5px] font-semibold text-label-1">{title}</span> <span className="text-[13px] text-label-3 tabular-nums">{n(count)}</span>
          {hint ? <span className="mt-0.5 block text-[12.5px] text-label-2">{hint}</span> : null}
        </span>
      </button>
      {open ? (
        <div id={`${id}-body`} className="pb-3 pl-6">
          {children}
        </div>
      ) : null}
    </section>
  );
}

function collapse(items: DataIssueItem[], text: (i: DataIssueItem) => string) {
  const map = new Map<string, { item: DataIssueItem; count: number }>();
  for (const i of items) {
    const key = text(i);
    const row = map.get(key);
    if (row) row.count += 1;
    else map.set(key, { item: i, count: 1 });
  }
  return [...map.values()];
}

/** Server-grouped problems (`GET /runs/{id}/data-issues`): planner titles, hints, Excel rows, download. */
export function IssueGroups({ runId, groups }: { runId: number; groups: DataIssueGroup[] }) {
  const { t, locale } = useI18n();
  const [limit, setLimit] = useState<Record<string, number>>({});
  const text = (i: DataIssueItem) => (locale === "tr" ? i.message_tr || i.message : i.message).replace(/\s*\(#\d+\)/g, "");
  const ordered = orderGroups(groups);
  if (!ordered.length) return null;
  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 pb-1">
        <h3 className="type-headline text-label-1">{t("glass.report.dataTitle")}</h3>
        <Button size="sm" variant="ghost" nativeButton={false} render={<a href={dataIssuesXlsxUrl(runId)} download />}>
          <Download /> {t("glass.report.downloadIssues")}
        </Button>
      </div>
      <p className="text-[12.5px] text-label-2">{t("glass.report.dataHint")}</p>
      <div className="mt-1">
        {ordered.map((g) => {
          const rows = collapse(g.items, text);
          const shown = limit[g.code] ?? 12;
          return (
            <Disclosure key={g.code} title={locale === "tr" ? g.title.tr || g.title.en : g.title.en || g.title.tr} count={g.count} hint={g.hint ? (locale === "tr" ? g.hint.tr : g.hint.en) : undefined} testId={`issue-group-${g.code}`}>
              <ul className="flex flex-col">
                {rows.slice(0, shown).map(({ item, count }, i) => {
                  const rowsOf = item.classes.map((c) => c.source_row).filter((r): r is number => typeof r === "number");
                  return (
                    <li key={i} className="py-1.5 text-[13px] text-label-1 [&:not(:last-child)]:hairline-b">
                      {text(item)}
                      {count > 1 ? <span className="ml-1.5 text-[12px] text-label-3 tabular-nums">{t("glass.report.times", { n: count })}</span> : null}
                      {rowsOf.length ? <span className="mt-0.5 block text-[12px] text-label-3">{t("glass.report.excelRows", { rows: [...new Set(rowsOf)].slice(0, 6).join(", ") })}</span> : null}
                    </li>
                  );
                })}
              </ul>
              {rows.length > shown ? (
                <Button size="xs" variant="secondary" className="mt-2" onClick={() => setLimit((l) => ({ ...l, [g.code]: rows.length }))}>
                  {t("glass.report.showAll", { n: rows.length })}
                </Button>
              ) : null}
            </Disclosure>
          );
        })}
      </div>
    </div>
  );
}

const CODE_TITLES: Record<string, MessageKey> = {
  input_conflict: "glass.report.code.input_conflict",
  trusted_lock_capacity: "glass.report.code.trusted_lock_capacity",
  trusted_lock_tags: "glass.report.code.trusted_lock_tags",
  outside_room_pool: "glass.report.code.outside_room_pool",
  locked_overlap: "glass.report.code.locked_overlap",
};

/** Fallback when the backend has no data-issues route: client groups by code (same order and collapsing). */
export function LocalIssueGroups({ sections }: { sections: { section: string; codes: Map<string, CollapsedDiagnosis[]> }[] }) {
  const { t, locale } = useI18n();
  const blocks = sections.filter((s) => s.section !== "unplaced").flatMap((s) => [...s.codes.entries()]);
  if (!blocks.length) return null;
  return (
    <div>
      <h3 className="type-headline pb-1 text-label-1">{t("glass.report.dataTitle")}</h3>
      {blocks.map(([code, rows]) => (
        <Disclosure key={code} title={t(CODE_TITLES[code] ?? "glass.report.code.other")} count={rows.reduce((s, r) => s + r.count, 0)}>
          <ul>
            {rows.map((r) => (
              <li key={r.d.id} className="py-1.5 text-[13px] text-label-1 [&:not(:last-child)]:hairline-b" data-testid="diagnosis-card" data-code={r.d.code ?? ""}>
                {plannerText(r.d, locale)}
                {r.count > 1 ? <span className="ml-1.5 text-[12px] text-label-3">{t("glass.report.times", { n: r.count })}</span> : null}
              </li>
            ))}
          </ul>
        </Disclosure>
      ))}
    </div>
  );
}
