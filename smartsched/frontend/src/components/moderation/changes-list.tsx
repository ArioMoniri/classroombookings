"use client";
/**
 * "Yayından beri değişenler" (moderation spec §5.1, P19-M-07): the edits since the published run was activated
 * that change the next solve, from the server (`GET /terms/{id}/changes-since-publish`), newest first. The
 * same list in every browser and for every coordinator; its `changed_request_ids` seed the re-solve. Opened
 * from the console header (a popover, a bottom sheet on phones) and shown in the recreate sheet.
 */
import { CircleDashed } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Skeleton } from "@/components/ui/skeleton";
import { useChanges, type Change } from "@/lib/api/moderation";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { springs, useReduce } from "@/lib/motion";
import { changeLevel, changeSummary } from "./moderation-model";
import { ResponsiveDialog } from "./responsive-dialog";
import { usePhone } from "./use-media";

function when(iso: string | null, lang: "tr" | "en"): string {
  return iso ? new Date(iso).toLocaleString(lang === "tr" ? "tr-TR" : "en-GB", { dateStyle: "short", timeStyle: "short" }) : "";
}

export function ChangeLine({ c }: { c: Change }) {
  const { t, locale, n } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const s = changeSummary(c);
  const level = changeLevel(c);
  const what =
    c.kind === "priority"
      ? t("moderation.changes.priority", { level: t(`moderation.changes.level.${level ?? "request"}`), tier: s.cleared ? t("moderation.changes.cleared") : t(`moderation.tier.${s.tier ?? "normal"}`) })
      : t(`moderation.changes.kind.${c.kind}` as MessageKey);
  return (
    <li className="flex flex-col border-b border-hairline py-1.5 last:border-b-0" data-testid="change-row" data-kind={c.kind}>
      <span className="type-footnote">
        <span className="font-semibold">{s.subjects || t("moderation.changes.noClass")}</span>
        {s.more ? <span className="text-label-2"> {t("moderation.changes.more", { n: n(s.more) })}</span> : null}
        {": "}
        {what}
      </span>
      <span className="type-caption text-label-3">{[c.actor, when(c.ts, lang), c.reason ? `“${c.reason}”` : null].filter(Boolean).join(" · ")}</span>
    </li>
  );
}

export function ChangesList({ termId, max }: { termId: number; max?: number }) {
  const { t } = useI18n();
  const q = useChanges(termId);
  if (q.isLoading) return <Skeleton className="h-12 w-full" />;
  if (q.isError) return <p role="alert" className="type-footnote text-label-2">{t("moderation.loadError")}</p>;
  const items = q.data?.items ?? [];
  if (!items.length) return <p className="type-footnote text-label-2" data-testid="changes-none">{t("moderation.staged.none")}</p>;
  return (
    <ul className="flex max-h-72 flex-col overflow-auto" data-testid="changes-list">
      {(max ? items.slice(0, max) : items).map((c) => <ChangeLine key={c.audit_id} c={c} />)}
    </ul>
  );
}

/** the console's "N değişiklik yayında değil" link */
export function ChangesLink({ termId, canEdit }: { termId: number; canEdit: boolean }) {
  const { t, n } = useI18n();
  const reduce = useReduce();
  const phone = usePhone();
  const q = useChanges(termId);
  const [open, setOpen] = useState(false);
  const count = q.data?.total ?? 0;
  const label = (
    // the bump follows the count (motion.md §3.9 staged-count-bump), never on first paint
    <motion.span key={count} className="tabular-nums" initial={reduce || !q.data ? false : { scale: 1.08 }} animate={{ scale: 1 }} transition={springs.bouncySubtle}>
      {q.data ? t("moderation.staged.link", { count }) : t("busy.loading")}
    </motion.span>
  );
  const body = (
    <>
      {q.data?.since ? <p className="type-caption text-label-3">{t("moderation.changes.since", { id: q.data.published_run_id ?? "—" })}</p> : null}
      <ChangesList termId={termId} />
      {count ? <p className="type-caption text-label-2">{t("moderation.changes.requests", { n: n(q.data?.changed_request_ids.length ?? 0) })}</p> : null}
      {!canEdit ? <p className="type-caption text-label-3">{t("moderation.publishNeedsEdit")}</p> : null}
    </>
  );
  if (phone) {
    return (
      <>
        <Button variant="ghost" onClick={() => setOpen(true)} data-testid="staged-link"><CircleDashed aria-hidden />{label}</Button>
        <ResponsiveDialog open={open} onOpenChange={setOpen} title={t("moderation.staged.title")} footer={<Button variant="ghost" onClick={() => setOpen(false)}>{t("common.close")}</Button>} testId="changes-sheet">
          {body}
        </ResponsiveDialog>
      </>
    );
  }
  return (
    <Popover>
      <PopoverTrigger render={<Button variant="ghost" size="sm" data-testid="staged-link" />}>
        <CircleDashed aria-hidden />
        {label}
      </PopoverTrigger>
      <PopoverContent className="flex w-96 flex-col gap-2" align="start" data-testid="changes-popover">
        <p className="type-headline">{t("moderation.staged.title")}</p>
        {body}
      </PopoverContent>
    </Popover>
  );
}
