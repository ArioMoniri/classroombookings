"use client";
/**
 * Ayarlar › Öğrenme belleği (phase19-suggestions.md §6): what the system learned (terms and observation counts,
 * open / accepted / dismissed suggestions of the working term), resets per person / per term / everything (a
 * reason always, the typed word SIFIRLA for "Tümü"), "Son sıfırlamalar" with Geri al while the 30-day window
 * lasts, and the KVKK erasure of one person (immediate, no undo). planning.admin only; everyone else sees the
 * standard no-access note. A standalone component: mounted at /moderation/learning and in Settings.
 */
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { catalogApi, type Instructor } from "@/lib/api/catalog-admin";
import { HttpError } from "@/lib/api/client";
import { useTerms } from "@/lib/api/hooks";
import { useMemoryActions, useMemorySummary, useResets, type ResetRow, type ResetScope } from "@/lib/api/learning";
import { useI18n } from "@/lib/i18n/provider";
import { tween, useReduce } from "@/lib/motion";
import { usePermissions } from "@/lib/permissions";
import { useTermContext } from "@/components/timetable/use-calendar-data";
import { resetStatus } from "./learning-model";
import { ResetDialog } from "./reset-dialog";

function PersonPicker({ value, onChange, id }: { value: Instructor | null; onChange: (i: Instructor | null) => void; id: string }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const found = useQuery({ queryKey: ["learning", "instructor-search", q], queryFn: () => catalogApi.instructors(q), enabled: q.trim().length >= 2, staleTime: 30_000 });
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-1">
      <label className="relative block">
        <span className="sr-only">{t("learning.memory.personSearch")}</span>
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-label-3" aria-hidden />
        <Input id={id} value={value ? value.full_name : q} onChange={(e) => { onChange(null); setQ(e.target.value); }} placeholder={t("learning.memory.personPh")} className="pl-8" data-testid="memory-person" />
      </label>
      {!value && q.trim().length >= 2 ? (
        <ul role="listbox" aria-label={t("learning.memory.personSearch")} className="flex max-h-48 flex-col overflow-auto rounded-lg border border-hairline">
          {found.isLoading ? <li className="px-2 py-1 type-footnote text-label-2">{t("busy.searching")}</li> : null}
          {(found.data?.items ?? []).map((i) => (
            <li key={i.id} role="option" aria-selected={false}>
              <Button variant="ghost" size="sm" className="w-full justify-start rounded-none" onClick={() => onChange(i)}>
                {[i.title, i.full_name].filter(Boolean).join(" ")}
              </Button>
            </li>
          ))}
          {found.data && found.data.items.length === 0 ? <li className="px-2 py-1 type-footnote text-label-2">{t("learning.memory.noPerson")}</li> : null}
        </ul>
      ) : null}
    </div>
  );
}

function ResetRowView({ r, terms }: { r: ResetRow; terms: Map<number, string> }) {
  const { t, locale } = useI18n();
  const { undo } = useMemoryActions();
  const status = resetStatus(r);
  const subject = r.scope === "all" ? t("learning.scope.all") : r.scope === "term" ? (terms.get(Number(r.value)) ?? `#${r.value}`) : `#${r.value}`;
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-hairline py-2 type-footnote" data-testid="reset-row" data-status={status}>
      <span className="tabular-nums text-label-2">{new Date(r.created_at).toLocaleString(locale === "tr" ? "tr-TR" : "en-GB", { dateStyle: "medium", timeStyle: "short" })}</span>
      <span className="font-semibold">{r.kind === "ERASURE" ? t("learning.memory.erasure") : t(`learning.scope.${r.scope}`)}</span>
      <span>{subject}</span>
      {r.reason ? <span className="text-label-2">“{r.reason}”</span> : null}
      <span className="ml-auto text-label-2">{t(`learning.memory.status.${status}`, { n: r.days_left })}</span>
      {status === "undoable" ? (
        <Button
          size="xs"
          variant="outline"
          disabled={undo.isPending}
          data-testid="reset-undo"
          onClick={() =>
            void undo
              .mutateAsync(r.id)
              .then(() => toast.success(t("learning.reset.undone")))
              .catch((e: unknown) => toast.error(e instanceof HttpError ? e.message : String(e)))
          }
        >
          {t("common.undo")}
        </Button>
      ) : null}
    </li>
  );
}

export function LearningMemoryPanel() {
  const { t, n } = useI18n();
  const reduce = useReduce();
  const { can, loading } = usePermissions();
  const admin = can("planning.admin");
  const { termId } = useTermContext();
  const terms = useTerms({ enabled: admin });
  const summary = useMemorySummary(termId, admin);
  const resets = useResets(admin);
  const [person, setPerson] = useState<Instructor | null>(null);
  const [erasePerson, setErasePerson] = useState<Instructor | null>(null);
  const [term, setTerm] = useState<string>("");
  const [dialog, setDialog] = useState<{ scope: ResetScope | "erase"; subject?: { id: number; label: string } } | null>(null);
  const termNames = new Map((terms.data ?? []).map((x) => [x.id, x.code]));

  if (loading) return <Skeleton className="h-64 w-full" />;
  if (!admin) return <EmptyState title={t("learning.memory.forbiddenTitle")} description={t("learning.memory.forbidden")} />;

  const s = summary.data;
  const sugg = s?.suggestions ?? {};
  return (
    <div className="flex max-w-3xl flex-col gap-6" data-testid="learning-memory">
      <header className="flex flex-col gap-1">
        <h2 className="type-title-2">{t("learning.memory.title")}</h2>
        <p className="type-callout text-label-2">{t("learning.memory.intro")}</p>
      </header>

      <section aria-labelledby="mem-summary" className="flex flex-col gap-2">
        <h3 id="mem-summary" className="type-headline">{t("learning.memory.summary")}</h3>
        {summary.isError ? (
          <p role="alert" className="type-footnote text-label-2">{t("learning.list.error")}</p>
        ) : !s ? (
          <Skeleton className="h-16 w-full" />
        ) : (
          /* a reset or undo swaps the region with one fade, never per row (motion.md §3.10) */
          <motion.dl key={`${s.observations}-${s.hidden_by_reset}`} initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={reduce ? { duration: 0 } : tween.fadeIn} className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 type-callout" data-testid="memory-summary">
            <dt className="text-label-2">{t("learning.memory.terms")}</dt>
            <dd>{s.terms.length ? s.terms.map((x) => `${x.code ?? "—"} (${n(x.observations)})`).join(" · ") : "—"}</dd>
            <dt className="text-label-2">{t("learning.memory.observations")}</dt>
            <dd className="tabular-nums" data-testid="memory-observations">{n(s.observations)}</dd>
            <dt className="text-label-2">{t("learning.memory.hidden")}</dt>
            <dd className="tabular-nums">{n(s.hidden_by_reset)}</dd>
            <dt className="text-label-2">{t("learning.memory.suggestions")}</dt>
            <dd className="tabular-nums">{t("learning.memory.suggestionCounts", { open: n(sugg.open ?? 0), accepted: n(sugg.accepted ?? 0), dismissed: n(sugg.dismissed ?? 0) })}</dd>
          </motion.dl>
        )}
      </section>

      <section aria-labelledby="mem-reset" className="flex flex-col gap-3">
        <h3 id="mem-reset" className="type-headline">{t("learning.memory.reset")}</h3>
        <div className="flex flex-wrap items-start gap-2">
          <span className="w-44 pt-1.5 type-callout">{t("learning.scope.person")}</span>
          <PersonPicker id="mem-person" value={person} onChange={setPerson} />
          <Button variant="outline" disabled={!person} onClick={() => person && setDialog({ scope: "person", subject: { id: person.id, label: [person.title, person.full_name].filter(Boolean).join(" ") } })} data-testid="reset-person-open">{t("learning.reset.open")}</Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="mem-term" className="w-44 type-callout">{t("learning.scope.term")}</label>
          <NativeSelect id="mem-term" className="max-w-xs flex-1" value={term} onChange={(e) => setTerm(e.target.value)} data-testid="memory-term">
            <option value="">{t("learning.memory.pickTerm")}</option>
            {(terms.data ?? []).map((x) => <option key={x.id} value={x.id}>{x.code}</option>)}
          </NativeSelect>
          <Button variant="outline" disabled={!term} onClick={() => setDialog({ scope: "term", subject: { id: Number(term), label: termNames.get(Number(term)) ?? term } })} data-testid="reset-term-open">{t("learning.reset.open")}</Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="w-44 type-callout">{t("learning.scope.all")}</span>
          <Button variant="outline" onClick={() => setDialog({ scope: "all" })} data-testid="reset-all-open">{t("learning.reset.openAll")}</Button>
        </div>
      </section>

      <section aria-labelledby="mem-resets" className="flex flex-col gap-1">
        <h3 id="mem-resets" className="type-headline">{t("learning.memory.recent")}</h3>
        {resets.isError ? (
          <p role="alert" className="type-footnote text-label-2">{t("learning.list.error")}</p>
        ) : !resets.data ? (
          <Skeleton className="h-12 w-full" />
        ) : resets.data.length === 0 ? (
          <p className="type-footnote text-label-2">{t("learning.memory.noResets")}</p>
        ) : (
          <ul data-testid="reset-list">{resets.data.map((r) => <ResetRowView key={r.id} r={r} terms={termNames} />)}</ul>
        )}
      </section>

      <section aria-labelledby="mem-erase" className="flex flex-col gap-2 border-t border-hairline pt-4">
        <h3 id="mem-erase" className="type-headline">{t("learning.erase.section")}</h3>
        <p className="type-footnote text-label-2">{t("learning.erase.sectionHint")}</p>
        <div className="flex flex-wrap items-start gap-2">
          <PersonPicker id="mem-erase-person" value={erasePerson} onChange={setErasePerson} />
          <Button variant="destructive" disabled={!erasePerson} onClick={() => erasePerson && setDialog({ scope: "erase", subject: { id: erasePerson.id, label: [erasePerson.title, erasePerson.full_name].filter(Boolean).join(" ") } })}>{t("learning.erase.action")}</Button>
        </div>
      </section>

      {dialog ? <ResetDialog open onOpenChange={(o) => !o && setDialog(null)} scope={dialog.scope} subject={dialog.subject} /> : null}
    </div>
  );
}
