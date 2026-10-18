"use client";
/**
 * PER-F09 (fix-h-2026-10-18): "Derslerim", an academician's own classes in one week (read-only), from
 * `GET /me/classes/week` (backend app/api/v1/my_classes.py, the same snapshot the "Derslerim" calendar feed serves).
 * One plain list per day, three quiet week buttons, a sentence when the account is not linked or a class has no room
 * yet (from Taleplerim's own counts, `GET /moderation/me/matchings`). No numbers without words.
 */
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { z } from "zod";
import { PageHeader } from "@/components/common/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { request } from "@/lib/api/client";
import { useMyMatchings } from "@/lib/api/moderation";
import { useI18n } from "@/lib/i18n/provider";

export const MyClassesWeek = z.object({
  week_start: z.string(),
  week_end: z.string(),
  prev: z.string(),
  next: z.string(),
  today: z.string(),
  linked: z.boolean(),
  term_id: z.number().nullable(),
  classes: z.array(
    z.object({
      uid: z.string(),
      date: z.string(),
      start: z.string(),
      end: z.string(),
      codes: z.array(z.string()).default([]),
      section: z.string().nullable().default(null),
      title: z.string().nullable().default(null),
      rooms: z.array(z.string()).default([]),
      week: z.number().nullable().default(null),
    }),
  ),
});
export type MyClassesWeek = z.infer<typeof MyClassesWeek>;

export const myClassesKey = (date: string | null) => ["me", "classes", "week", date ?? "today"] as const;

export function useMyClassesWeek(date: string | null) {
  return useQuery({ queryKey: myClassesKey(date), queryFn: () => request("/me/classes/week", { query: { date: date ?? undefined }, schema: MyClassesWeek, silent: true }), staleTime: 60_000 });
}

/** the week's classes by day, Monday first; days without a class are left out */
export function byDay(classes: MyClassesWeek["classes"]): [string, MyClassesWeek["classes"]][] {
  const out = new Map<string, MyClassesWeek["classes"]>();
  for (const c of classes) out.set(c.date, [...(out.get(c.date) ?? []), c]);
  return [...out.entries()].sort(([a], [b]) => a.localeCompare(b));
}

const asDate = (iso: string) => new Date(`${iso}T12:00:00`);

export function MyClassesView() {
  const { t, locale } = useI18n();
  const params = useSearchParams();
  const router = useRouter();
  const date = params.get("date");
  const q = useMyClassesWeek(date);
  const w = q.data;
  const matchings = useMyMatchings(w?.linked ? w.term_id : null);
  const unplaced = matchings.data?.counts?.unplaced ?? 0;
  const tag = locale === "tr" ? "tr-TR" : "en-GB";
  const dayFmt = new Intl.DateTimeFormat(tag, { weekday: "long", day: "numeric", month: "long" });
  const shortFmt = new Intl.DateTimeFormat(tag, { day: "numeric", month: "long" });
  const go = (d: string | null) => router.replace(d ? `/my-classes?date=${d}` : "/my-classes");
  const isThisWeek = !!w && w.today >= w.week_start && w.today <= w.week_end;

  return (
    <div className="max-w-3xl" data-testid="my-classes">
      <PageHeader
        title={t("myClasses.title")}
        subtitle={w ? t("myClasses.week", { from: shortFmt.format(asDate(w.week_start)), to: shortFmt.format(asDate(w.week_end)) }) : t("myClasses.lead")}
        actions={
          w ? (
            <div className="flex flex-wrap gap-2" role="group" aria-label={t("myClasses.title")}>
              <Button variant="outline" className="pointer-coarse:min-h-11" onClick={() => go(w.prev)} data-testid="my-classes-prev">{t("myClasses.prev")}</Button>
              {!isThisWeek ? <Button variant="outline" className="pointer-coarse:min-h-11" onClick={() => go(null)} data-testid="my-classes-today">{t("myClasses.thisWeek")}</Button> : null}
              <Button variant="outline" className="pointer-coarse:min-h-11" onClick={() => go(w.next)} data-testid="my-classes-next">{t("myClasses.next")}</Button>
            </div>
          ) : null
        }
      />
      {q.isPending ? <Skeleton className="h-48 rounded-2xl" /> : null}
      {q.isError ? <p role="alert" className="type-callout text-status-infeasible-fg">{t("myClasses.loadFailed")}</p> : null}
      {w && !w.linked ? (
        <Card>
          <CardContent className="type-callout text-label-2" data-testid="my-classes-not-linked">{t("myClasses.notLinked")}</CardContent>
        </Card>
      ) : null}
      {w?.linked && unplaced > 0 ? (
        <p className="mb-3 rounded-xl bg-status-warning px-3 py-2 type-callout text-status-warning-fg" data-testid="my-classes-unplaced">
          {t("myClasses.unplaced", { n: unplaced })}{" "}
          <Link href="/moderation/me" className="font-medium underline pointer-coarse:inline-flex pointer-coarse:min-h-11 pointer-coarse:items-center">{t("myClasses.unplacedLink")}</Link>
        </p>
      ) : null}
      {w?.linked && !w.classes.length ? (
        <Card>
          <CardContent className="type-callout text-label-2" data-testid="my-classes-empty">{t("myClasses.empty")}</CardContent>
        </Card>
      ) : null}
      {w?.linked && w.classes.length ? (
        <div className="flex flex-col gap-4">
          {byDay(w.classes).map(([day, rows]) => (
            <section key={day} aria-labelledby={`mc-${day}`} data-testid={`my-classes-day-${day}`}>
              <h2 id={`mc-${day}`} className="mb-1.5 type-headline text-label-1">
                {dayFmt.format(asDate(day))}
              </h2>
              <Card className="gap-0 py-0">
                <ul>
                  {rows.map((c) => (
                    <li key={c.uid} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 px-4 py-3 [&:not(:last-child)]:hairline-b" data-testid="my-class">
                      <span className="w-28 shrink-0 type-callout font-medium text-label-1 tabular-nums">{c.start}–{c.end}</span>
                      <span className="min-w-0 flex-1 type-callout text-label-1">
                        {c.codes.join(" / ")}
                        {c.section ? <span className="text-label-2"> · {t("myClasses.section", { s: c.section })}</span> : null}
                        {c.title ? <span className="block type-footnote text-label-2">{c.title}</span> : null}
                      </span>
                      <span className="type-callout text-label-1">{c.rooms.length ? c.rooms.join(", ") : <span className="text-label-3">{t("myClasses.noRoom")}</span>}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            </section>
          ))}
        </div>
      ) : null}
    </div>
  );
}
