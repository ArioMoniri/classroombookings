"use client";
/**
 * Duties by date and room: one date at a time (previous / next, or every date), grouped by session time; each post
 * shows the room (link to its page), the exams, the seated students, required vs assigned and who is on duty. A
 * planner can lock a duty (a re-run keeps it) or reassign it to a free candidate (people who cannot take it are
 * listed with the reason). A post a diagnosis points to opens on its date and is highlighted.
 */
import { ChevronLeft, ChevronRight, Lock, LockOpen, UserRoundCog } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { toast } from "sonner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button, IconButton } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { errorText } from "@/lib/api/analytics";
import { useLockDuty, type Duty, type PlanDetail, type Post } from "@/lib/api/invigilation";
import { useI18n } from "@/lib/i18n/provider";
import { formatDate } from "@/lib/time";
import { cn } from "@/lib/utils";
import { bySession, filterPosts, postDates } from "./invigilation-model";
import { ReassignDialog } from "./reassign-dialog";

const PAGE = 60;

export function PostsView({ plan, canEdit, person, focusPost }: { plan: PlanDetail; canEdit: boolean; person: string | null; focusPost: string | null }) {
  const { t, n, locale } = useI18n();
  const dates = useMemo(() => postDates(plan.posts), [plan.posts]);
  const focus = focusPost ? plan.posts.find((p) => p.key === focusPost) : undefined;
  const firstMissing = plan.posts.find((p) => p.missing > 0)?.date;
  const [date, setDate] = useState<string | "all">(() => focus?.date ?? (person ? "all" : (firstMissing ?? dates[0] ?? "all")));
  const [query, setQuery] = useState("");
  const [onlyMissing, setOnlyMissing] = useState(false);
  const [limit, setLimit] = useState(PAGE);
  const [editing, setEditing] = useState<{ post: Post; duty: Duty } | null>(null);
  // a diagnosis link or a person filter re-targets the date (state adjusted during render, no effect)
  const [seen, setSeen] = useState(`${focusPost}|${person}`);
  if (seen !== `${focusPost}|${person}`) {
    setSeen(`${focusPost}|${person}`);
    if (focus) setDate(focus.date);
    else if (person) setDate("all");
    setLimit(PAGE);
  }
  const shown = useMemo(() => {
    const base = person ? plan.posts.filter((p) => p.assigned.some((d) => d.person_key === person)) : plan.posts;
    return filterPosts(base, { date, query, onlyMissing });
  }, [plan.posts, person, date, query, onlyMissing]);
  const sessions = useMemo(() => bySession(shown.slice(0, limit)), [shown, limit]);
  const focusRef = useRef<HTMLLIElement | null>(null);
  useEffect(() => {
    focusRef.current?.scrollIntoView({ block: "center" });
    focusRef.current?.focus({ preventScroll: true });
  }, [focusPost]);
  const idx = date === "all" ? -1 : dates.indexOf(date);
  const dayFmt = (d: string) => formatDate(d, locale, { weekday: "short", day: "2-digit", month: "2-digit", year: "numeric" });

  return (
    <section className="flex flex-col gap-3" aria-label={t("invigilation.view.posts")} data-testid="invig-posts">
      <div className="flex flex-wrap items-end gap-2">
        <div className="flex items-end gap-1">
          <IconButton label={t("invigilation.posts.prevDate")} variant="outline" size="sm" disabled={idx <= 0} onClick={() => setDate(dates[idx - 1]!)}>
            <ChevronLeft aria-hidden />
          </IconButton>
          <label className="flex flex-col gap-1">
            <span className="type-footnote font-medium text-label-2">{t("invigilation.posts.date")}</span>
            <NativeSelect size="sm" className="w-48" value={date} onChange={(e) => (setDate(e.target.value), setLimit(PAGE))} data-testid="invig-date">
              <option value="all">{t("invigilation.posts.allDates", { n: n(dates.length) })}</option>
              {dates.map((d) => (
                <option key={d} value={d}>{dayFmt(d)}</option>
              ))}
            </NativeSelect>
          </label>
          <IconButton label={t("invigilation.posts.nextDate")} variant="outline" size="sm" disabled={idx < 0 || idx >= dates.length - 1} onClick={() => setDate(dates[idx + 1]!)}>
            <ChevronRight aria-hidden />
          </IconButton>
        </div>
        <Input fieldSize="sm" type="search" className="w-56" placeholder={t("invigilation.posts.search")} aria-label={t("invigilation.posts.search")} value={query} onChange={(e) => (setQuery(e.target.value), setLimit(PAGE))} data-testid="invig-post-search" />
        <label className="flex h-(--control-h-sm) items-center gap-2 type-callout">
          <Checkbox checked={onlyMissing} onCheckedChange={(v) => (setOnlyMissing(Boolean(v)), setLimit(PAGE))} data-testid="invig-only-missing" />
          {t("invigilation.posts.onlyMissing")}
        </label>
        <span className="ml-auto type-footnote text-label-2 tnum" aria-live="polite">{t("invigilation.posts.count", { n: n(shown.length) })}</span>
      </div>
      {shown.length === 0 ? (
        <p className="rounded-xl bg-fill-3 px-3 py-4 type-callout text-label-2">{t("invigilation.posts.none")}</p>
      ) : (
        <div className="flex flex-col gap-4">
          {sessions.map((s) => (
            <section key={s.key} aria-label={`${dayFmt(s.date)} ${s.time}`} className="flex flex-col gap-2">
              <h4 className="sticky top-0 z-[1] -mx-1 bg-background px-1 py-1 type-headline">
                <time dateTime={s.date}>{dayFmt(s.date)}</time> · <span className="tnum">{s.time}</span>
                <span className="ml-2 type-footnote font-normal text-label-2">{t("invigilation.posts.rooms", { n: n(s.posts.length) })}</span>
              </h4>
              <ul className="grid gap-2 md:grid-cols-2 2xl:grid-cols-3">
                {s.posts.map((p) => (
                  <PostCard key={p.key} p={p} canEdit={canEdit} planId={plan.id} focused={p.key === focusPost} refCb={p.key === focusPost ? focusRef : undefined} onReassign={(duty) => setEditing({ post: p, duty })} />
                ))}
              </ul>
            </section>
          ))}
          {shown.length > limit ? (
            <Button variant="outline" className="self-center" onClick={() => setLimit((l) => l + PAGE * 2)} data-testid="invig-posts-more">
              {t("invigilation.posts.more", { n: n(shown.length - limit) })}
            </Button>
          ) : null}
        </div>
      )}
      <ReassignDialog planId={plan.id} target={editing} onClose={() => setEditing(null)} />
    </section>
  );
}

function PostCard({ p, canEdit, planId, focused, refCb, onReassign }: { p: Post; canEdit: boolean; planId: number; focused: boolean; refCb?: RefObject<HTMLLIElement | null>; onReassign: (d: Duty) => void }) {
  const { t, n, locale } = useI18n();
  const lang = locale === "tr" ? "tr" : "en";
  const lock = useLockDuty();
  const first = p.exams[0];
  const toggle = async (d: Duty) => {
    try {
      await lock.mutateAsync({ id: planId, dutyId: d.id, locked: !d.is_locked });
      toast.success(t(d.is_locked ? "invigilation.posts.unlocked" : "invigilation.posts.lockedToast", { name: d.person_name }));
    } catch (e) {
      toast.error(errorText(e, lang));
    }
  };
  return (
    <li
      ref={refCb}
      tabIndex={focused ? -1 : undefined}
      className={cn("flex min-w-0 flex-col gap-2 rounded-xl bg-card p-3 edge-hairline outline-hidden", focused && "ring-2 ring-(--focus)", p.missing > 0 && "bg-status-warning")}
      data-testid="invig-post"
      data-post={p.key}
      data-missing={p.missing}
    >
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
        <Link href={`/rooms/${p.room_id}`} className="type-headline hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-(--focus)">{p.room}</Link>
        {p.building ? <span className="type-footnote text-label-2">{t("invigilation.posts.building", { b: p.building })}</span> : null}
        <span className="ml-auto type-footnote text-label-2 tnum">{t("invigilation.posts.seated", { n: n(p.seated) })}</span>
      </div>
      {first ? (
        <p className="type-footnote text-label-2" title={p.exams.map((e) => e.label).join("\n")}>
          <span className="line-clamp-2">{first.label}{p.exams.length > 1 ? ` ${t("invigilation.posts.moreExams", { n: n(p.exams.length - 1) })}` : ""}</span>
          {first.instructor_text ? <span className="block truncate text-label-3">{first.instructor_text}</span> : null}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2 type-footnote">
        <span className="tnum">{t("invigilation.posts.staffed", { assigned: n(p.assigned.length), required: n(p.required) })}</span>
        {p.missing > 0 ? <Badge tone="warning" data-testid="invig-post-missing">{t("invigilation.posts.missing", { n: n(p.missing) })}</Badge> : null}
      </div>
      {p.assigned.length ? (
        <ul className="flex flex-col gap-1" aria-label={t("invigilation.posts.onDuty")}>
          {p.assigned.map((d) => (
            <li key={d.id} className="flex min-w-0 items-center gap-1.5 rounded-md bg-fill-3 py-0.5 pr-0.5 pl-2" data-testid="invig-duty" data-duty={d.id} data-locked={d.is_locked ? "true" : "false"}>
              {d.is_locked ? <Lock aria-label={t("invigilation.posts.isLocked")} className="size-3.5 shrink-0 text-status-locked-fg" /> : null}
              <span className="min-w-0 flex-1 truncate type-callout">{d.person_name}</span>
              {d.origin === "MANUAL" ? <Badge tone="locked">{t("invigilation.posts.manual")}</Badge> : null}
              {canEdit ? (
                <>
                  <IconButton size="xs" label={t(d.is_locked ? "invigilation.posts.unlock" : "invigilation.posts.lock", { name: d.person_name })} aria-pressed={d.is_locked} disabled={lock.isPending} onClick={() => void toggle(d)} data-testid="invig-lock">
                    {d.is_locked ? <LockOpen aria-hidden /> : <Lock aria-hidden />}
                  </IconButton>
                  <IconButton size="xs" label={t("invigilation.posts.reassign", { name: d.person_name })} onClick={() => onReassign(d)} data-testid="invig-reassign">
                    <UserRoundCog aria-hidden />
                  </IconButton>
                </>
              ) : null}
            </li>
          ))}
        </ul>
      ) : (
        <Alert tone="warning" className="py-1.5">{t("invigilation.posts.nobody")}</Alert>
      )}
    </li>
  );
}
