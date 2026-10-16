"use client";
/**
 * Reassign one duty: the post's candidates (`GET …/candidates?post_key=`): the free people as a radio list (search
 * by name), and everyone who cannot take it with the backend's reason (teaching, unavailable, own exam, on another
 * duty or at a limit). The swap is checked against every hard rule; a 409 shows the problems verbatim. The new duty
 * is MANUAL and locked, so a re-run keeps it.
 */
import { useId, useMemo, useState } from "react";
import { toast } from "sonner";
import { ResponsiveDialog } from "@/components/moderation/responsive-dialog";
import { Alert } from "@/components/ui/alert";
import { BusyButton } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { errorProblems, errorText, pairOf } from "@/lib/api/analytics";
import { useCandidates, useReassignDuty, type Duty, type Post } from "@/lib/api/invigilation";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/time";

const fold = (s: string) => s.toLocaleLowerCase("tr").normalize("NFD").replace(/\p{M}/gu, "").replace(/ı/g, "i");
const KINDS = new Set(["instructor", "staff", "assistant", "other"]);

export function ReassignDialog({ planId, target, onClose }: { planId: number; target: { post: Post; duty: Duty } | null; onClose: () => void }) {
  const { t, n, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const id = useId();
  const cand = useCandidates(target ? planId : null, target?.post.key ?? null);
  const reassign = useReassignDuty();
  const [pick, setPick] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [query, setQuery] = useState("");
  const [err, setErr] = useState<{ text: string; problems: string[] } | null>(null);
  const [seen, setSeen] = useState<number | null>(null);
  if ((target?.duty.id ?? null) !== seen) {
    setSeen(target?.duty.id ?? null);
    setPick(null);
    setReason("");
    setQuery("");
    setErr(null);
  }
  const q = fold(query.trim());
  const free = useMemo(() => (cand.data?.free ?? []).filter((p) => !q || fold(p.name).includes(q)), [cand.data, q]);
  const busy = useMemo(() => (cand.data?.unavailable ?? []).filter((p) => !q || fold(p.name).includes(q)), [cand.data, q]);
  const kind = (k: string) => (KINDS.has(k.toLowerCase()) ? t(`invigilation.kindLower.${k.toLowerCase()}` as MessageKey) : k);

  const submit = async () => {
    if (!target || !pick) return;
    setErr(null);
    try {
      await reassign.mutateAsync({ id: planId, dutyId: target.duty.id, personKey: pick, reason: reason.trim() || undefined });
      toast.success(t("invigilation.reassign.done", { name: cand.data?.free.find((p) => p.person_key === pick)?.name ?? pick }));
      onClose();
    } catch (e) {
      setErr({ text: errorText(e, lang), problems: errorProblems(e) });
    }
  };

  const post = target?.post;
  return (
    <ResponsiveDialog
      open={target !== null}
      onOpenChange={(o) => !o && onClose()}
      title={target ? t("invigilation.reassign.title", { name: target.duty.person_name }) : ""}
      description={post ? t("invigilation.reassign.body", { room: post.room, date: formatDate(post.date, locale, { weekday: "short", day: "2-digit", month: "2-digit" }), time: post.time }) : undefined}
      className="sm:max-w-xl"
      testId="invig-reassign-dialog"
      footer={
        <>
          <Button variant="ghost" className="max-md:h-11" onClick={onClose}>{t("common.cancel")}</Button>
          <BusyButton busy={reassign.isPending} busyLabel={t("busy.working")} disabled={!pick} className="max-md:h-11" onClick={() => void submit()} data-testid="invig-reassign-ok">
            {t("invigilation.reassign.confirm")}
          </BusyButton>
        </>
      }
    >
      <div className="flex min-w-0 flex-col gap-3">
        <Input type="search" placeholder={t("invigilation.reassign.search")} aria-label={t("invigilation.reassign.search")} value={query} onChange={(e) => setQuery(e.target.value)} data-testid="invig-cand-search" />
        {cand.isError ? (
          <Alert tone="error">{errorText(cand.error, lang)}</Alert>
        ) : !cand.data ? (
          <Skeleton className="h-40 w-full" />
        ) : (
          <>
            <fieldset className="flex min-w-0 flex-col gap-1">
              <legend className="mb-1 type-footnote font-medium text-label-1">{t("invigilation.reassign.free", { n: n(cand.data.free.length) })}</legend>
              {free.length === 0 ? (
                <p className="type-callout text-label-2">{t("invigilation.reassign.noFree")}</p>
              ) : (
                <ul className="flex max-h-60 flex-col overflow-auto rounded-lg edge-hairline" data-testid="invig-cand-free">
                  {free.slice(0, 200).map((p) => (
                    <li key={p.person_key} className="edge-hairline-b last:shadow-none">
                      <label className="flex min-h-10 cursor-pointer items-center gap-2 px-3 py-1.5 type-callout hover:bg-fill-2 has-checked:bg-tint-soft" htmlFor={`${id}-${p.person_key}`}>
                        <input id={`${id}-${p.person_key}`} type="radio" name={`${id}-pick`} value={p.person_key} checked={pick === p.person_key} onChange={() => setPick(p.person_key)} className="size-4 accent-(--accent) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus)" data-testid="invig-cand" />
                        <span className="min-w-0 flex-1 truncate">{p.name}</span>
                        <span className="type-caption text-label-2">{kind(p.kind)}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}
              {free.length > 200 ? <p className="type-footnote text-label-2">{t("invigilation.reassign.narrow", { n: n(free.length - 200) })}</p> : null}
            </fieldset>
            {busy.length ? (
              <details className="rounded-lg bg-fill-3 px-3 py-2">
                <summary className="cursor-pointer type-footnote font-medium focus-visible:outline-2 focus-visible:outline-(--focus)" data-testid="invig-cand-busy">{t("invigilation.reassign.unavailable", { n: n(cand.data.unavailable.length) })}</summary>
                <ul className="mt-2 flex max-h-48 flex-col gap-1 overflow-auto">
                  {busy.slice(0, 200).map((p) => (
                    <li key={p.person_key} className="flex flex-wrap items-baseline gap-x-2 type-callout">
                      <span className="min-w-0 truncate">{p.name}</span>
                      <span className="type-footnote text-label-2">{pairOf(p.reason_text, lang) || p.reason}</span>
                    </li>
                  ))}
                </ul>
              </details>
            ) : null}
          </>
        )}
        <label className="flex flex-col gap-1" htmlFor={`${id}-reason`}>
          <span className="type-footnote font-medium text-label-1">{t("invigilation.reassign.reason")}</span>
          <Textarea id={`${id}-reason`} maxLength={500} rows={2} value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t("invigilation.reassign.reasonHint")} data-testid="invig-reassign-reason" />
        </label>
        {err ? (
          <Alert tone="error" data-testid="invig-reassign-error">
            {err.text}
            {err.problems.length ? (
              <ul className="mt-1 list-disc pl-5">
                {err.problems.map((p) => <li key={p}>{p}</li>)}
              </ul>
            ) : null}
          </Alert>
        ) : null}
      </div>
    </ResponsiveDialog>
  );
}
