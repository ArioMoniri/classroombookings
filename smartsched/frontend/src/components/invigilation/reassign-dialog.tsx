"use client";
/**
 * Pick an invigilator for a post: either reassign one duty or, on a post with `missing > 0`, add one more
 * ("Gözetmen ekle", `POST …/duties`). The post's candidates (`GET …/candidates?post_key=`, about 0.3 s on the real
 * Final): the free people as a radio list (search by name), and everyone who cannot take it as disabled rows with
 * the backend's reason (teaching, unavailable, own exam, on another duty, rest, a daily or total cap). The choice
 * is checked against every hard rule; a 409 shows the server's sentence, its reason and the problems verbatim.
 * The new duty is MANUAL and locked, so a re-run keeps it.
 */
import { useId, useMemo, useState } from "react";
import { toast } from "sonner";
import { ResponsiveDialog } from "@/components/moderation/responsive-dialog";
import { Alert } from "@/components/ui/alert";
import { BusyButton, BusyGlyph } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { pairOf } from "@/lib/api/analytics";
import { dutyRefusal, useAddDuty, useCandidates, useReassignDuty, type Duty, type Post } from "@/lib/api/invigilation";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/time";

const fold = (s: string) => s.toLocaleLowerCase("tr").normalize("NFD").replace(/\p{M}/gu, "").replace(/ı/g, "i");
const KINDS = new Set(["instructor", "staff", "assistant", "other"]);
const SHOW = 200;

/** `duty: null` adds an invigilator to the post; a duty reassigns it */
export type PickTarget = { post: Post; duty: Duty | null };

export function ReassignDialog({ planId, target, onClose }: { planId: number; target: PickTarget | null; onClose: () => void }) {
  const { t, n, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const id = useId();
  const cand = useCandidates(target ? planId : null, target?.post.key ?? null);
  const reassign = useReassignDuty();
  const add = useAddDuty();
  const [pick, setPick] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [query, setQuery] = useState("");
  const [err, setErr] = useState<ReturnType<typeof dutyRefusal> | null>(null);
  const key = target ? `${target.post.key}|${target.duty?.id ?? "add"}` : null;
  const [seen, setSeen] = useState<string | null>(null);
  if (key !== seen) {
    setSeen(key);
    setPick(null);
    setReason("");
    setQuery("");
    setErr(null);
  }
  const q = fold(query.trim());
  const free = useMemo(() => (cand.data?.free ?? []).filter((p) => !q || fold(p.name).includes(q)), [cand.data, q]);
  const busy = useMemo(() => (cand.data?.unavailable ?? []).filter((p) => !q || fold(p.name).includes(q)), [cand.data, q]);
  const kind = (k: string) => (KINDS.has(k.toLowerCase()) ? t(`invigilation.kindLower.${k.toLowerCase()}` as MessageKey) : k);
  const adding = target !== null && target.duty === null;
  const pending = reassign.isPending || add.isPending;

  const submit = async () => {
    if (!target || !pick) return;
    setErr(null);
    const name = cand.data?.free.find((p) => p.person_key === pick)?.name ?? pick;
    const why = reason.trim() || undefined;
    try {
      if (target.duty) {
        await reassign.mutateAsync({ id: planId, dutyId: target.duty.id, personKey: pick, reason: why });
        toast.success(t("invigilation.reassign.done", { name }));
      } else {
        await add.mutateAsync({ id: planId, postKey: target.post.key, personKey: pick, reason: why });
        toast.success(t("invigilation.add.done", { name, room: target.post.room }));
      }
      onClose();
    } catch (e) {
      setErr(dutyRefusal(e, lang));
    }
  };

  const post = target?.post;
  const when = post ? formatDate(post.date, locale, { weekday: "short", day: "2-digit", month: "2-digit" }) : "";
  return (
    <ResponsiveDialog
      open={target !== null}
      onOpenChange={(o) => !o && onClose()}
      title={!target ? "" : target.duty ? t("invigilation.reassign.title", { name: target.duty.person_name }) : t("invigilation.add.title", { room: target.post.room })}
      description={
        !post
          ? undefined
          : adding
            ? t("invigilation.add.body", { date: when, time: post.time, assigned: n(post.assigned.length), required: n(post.required) })
            : t("invigilation.reassign.body", { room: post.room, date: when, time: post.time })
      }
      className="sm:max-w-xl"
      testId="invig-reassign-dialog"
      footer={
        <>
          <Button variant="ghost" className="max-md:h-11" onClick={onClose}>{t("common.cancel")}</Button>
          <BusyButton busy={pending} busyLabel={t("busy.working")} disabled={!pick} className="max-md:h-11" onClick={() => void submit()} data-testid="invig-reassign-ok">
            {adding ? t("invigilation.add.confirm") : t("invigilation.reassign.confirm")}
          </BusyButton>
        </>
      }
    >
      <div className="flex min-w-0 flex-col gap-3" data-mode={adding ? "add" : "reassign"}>
        <Input type="search" placeholder={t("invigilation.reassign.search")} aria-label={t("invigilation.reassign.search")} value={query} onChange={(e) => setQuery(e.target.value)} data-testid="invig-cand-search" />
        {cand.isError ? (
          <Alert tone="error">{dutyRefusal(cand.error, lang).text}</Alert>
        ) : !cand.data ? (
          <div className="flex flex-col gap-2" role="status" aria-live="polite" data-testid="invig-cand-loading">
            <p className="flex items-center gap-2 type-callout text-label-2">
              <BusyGlyph className="size-4" />
              {t("invigilation.reassign.checking")}
            </p>
            <Skeleton className="h-32 w-full" />
          </div>
        ) : (
          <>
            <fieldset className="flex min-w-0 flex-col gap-1">
              <legend className="mb-1 type-footnote font-medium text-label-1">{t("invigilation.reassign.free", { n: n(cand.data.free.length) })}</legend>
              {free.length === 0 ? (
                <p className="type-callout text-label-2" data-testid="invig-cand-none">{t("invigilation.reassign.noFree")}</p>
              ) : (
                <ul className="flex max-h-60 flex-col overflow-auto rounded-lg edge-hairline" data-testid="invig-cand-free">
                  {free.slice(0, SHOW).map((p) => (
                    <li key={p.person_key} className="edge-hairline-b last:shadow-none">
                      <label className="flex min-h-11 cursor-pointer items-center gap-2 px-3 py-1.5 type-callout hover:bg-fill-2 has-checked:bg-tint-soft md:min-h-10" htmlFor={`${id}-${p.person_key}`}>
                        <input id={`${id}-${p.person_key}`} type="radio" name={`${id}-pick`} value={p.person_key} checked={pick === p.person_key} onChange={() => setPick(p.person_key)} className="size-4 accent-(--accent) focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus)" data-testid="invig-cand" />
                        <span className="min-w-0 flex-1 truncate">{p.name}</span>
                        <span className="type-caption text-label-2">{kind(p.kind)}</span>
                      </label>
                    </li>
                  ))}
                </ul>
              )}
              {free.length > SHOW ? <p className="type-footnote text-label-2">{t("invigilation.reassign.narrow", { n: n(free.length - SHOW) })}</p> : null}
            </fieldset>
            {busy.length ? (
              // open by itself when nobody is free: then the reasons are the answer
              <details className="rounded-lg bg-fill-3 px-3 py-2" open={free.length === 0 || undefined}>
                <summary className="cursor-pointer type-footnote font-medium focus-visible:outline-2 focus-visible:outline-(--focus) max-md:py-2" data-testid="invig-cand-busy">{t("invigilation.reassign.unavailable", { n: n(cand.data.unavailable.length) })}</summary>
                <ul className="mt-2 flex max-h-48 flex-col overflow-auto" data-testid="invig-cand-unavailable">
                  {busy.slice(0, SHOW).map((p) => {
                    const why = pairOf(p.reason_text, lang) || p.reason;
                    const rid = `${id}-u-${p.person_key}`;
                    return (
                      <li key={p.person_key} className="flex min-h-10 items-center gap-2 py-1 type-callout text-label-2" data-testid="invig-cand-off" data-reason={p.reason}>
                        <input type="radio" disabled aria-describedby={`${rid}-why`} aria-label={p.name} className="size-4 shrink-0 opacity-50" />
                        {/* the name keeps its width: the reason wraps below it on a phone, beside it when there is room */}
                        <span className="flex min-w-0 flex-1 flex-col sm:flex-row sm:items-baseline sm:gap-2">
                          <span className="min-w-0 truncate">{p.name}</span>
                          <span id={`${rid}-why`} className="type-footnote sm:ml-auto sm:text-right">{why}</span>
                        </span>
                      </li>
                    );
                  })}
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
          <Alert tone="error" live="assertive" data-testid="invig-reassign-error">
            <span className="block" data-testid="invig-refusal" data-reason={err.reason ?? undefined}>{err.text}</span>
            {err.reasonText ? <span className="block type-footnote" data-testid="invig-refusal-reason">{t("invigilation.reassign.why", { reason: err.reasonText })}</span> : null}
            {err.problems.length ? (
              <ul className="mt-1 list-disc pl-5 type-footnote">
                {err.problems.map((p) => <li key={p}>{p}</li>)}
              </ul>
            ) : null}
          </Alert>
        ) : null}
      </div>
    </ResponsiveDialog>
  );
}
