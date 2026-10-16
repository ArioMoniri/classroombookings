"use client";
/**
 * /find-room (T1, docs/product/wave1-api.md §1): "Boş derslik bul". When (one date, a weekday in term weeks, or
 * a date range), what time (clock, periods, or a duration that may slide in a window), how many people, the
 * features (GET /rooms/facets), buildings and free text (the backend matches Turkish-insensitively). Results come
 * ranked with the backend's TR/EN reasons; one click opens the existing booking sheet prefilled with the room,
 * date and periods. Fewer than three free rooms → the backend's alternatives. Recent searches re-run in one click.
 *
 * Motion: none on search results (a frequent action; motion_designer §2.1). The booking sheet brings its own.
 */
import { Ban, Building2, CalendarClock, CalendarX, CheckCircle2, ChevronDown, CircleDashed, History, Loader2, PackageX, Search, Stamp, Users, type LucideIcon } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Chip } from "@/components/ui/chip";
import { DateField } from "@/components/ui/date-field";
import { Input } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Switch } from "@/components/ui/switch";
import { Alert, Field, Loading, PageTitle, SelectField } from "@/components/admin/kit";
import { useHydrated } from "@/lib/use-hydrated";
import { BookSheet, type BookTarget } from "@/components/bookings/book-sheet";
import { useBookingFormat, useProfileLanguage } from "@/components/bookings/use-booking-format";
import { crbs, crbsKeys, useBookingContext, useBookingDates, type GridQuery } from "@/lib/api/crbs";
import { errorText, pickLang, useFacets, useRecentSearches, w1Keys, wave1, wave1Error, type Feature, type FindAlternative, type FindResponse, type FindRow } from "@/lib/api/wave1";
import { intlLocale, type MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { ACTIONABLE, asRequestable, buildQuery, emptyForm, firstFreeDate, formFromRecent, recentParts, reserveSpan, slotsFor, type FindForm, type FormError, type TimeMode, type WhenMode } from "./find-room-model";

const STATUS: Record<string, { icon: LucideIcon; cls: string; key: MessageKey }> = {
  free: { icon: CheckCircle2, cls: "bg-status-feasible text-status-feasible-fg", key: "wave1.find.status.free" },
  requestable: { icon: Stamp, cls: "bg-tint-soft text-tint-text", key: "wave1.find.status.requestable" },
  partial: { icon: CircleDashed, cls: "bg-status-warning text-status-warning-fg", key: "wave1.find.status.partial" },
  busy: { icon: Ban, cls: "bg-status-preoccupied text-status-preoccupied-fg", key: "wave1.find.status.busy" },
  too_small: { icon: Users, cls: "bg-status-warning text-status-warning-fg", key: "wave1.find.status.too_small" },
  feature_missing: { icon: PackageX, cls: "bg-status-warning text-status-warning-fg", key: "wave1.find.status.feature_missing" },
  capacity_unknown: { icon: CircleDashed, cls: "bg-status-preoccupied text-status-preoccupied-fg", key: "wave1.find.status.capacity_unknown" },
  closed: { icon: CalendarX, cls: "bg-status-preoccupied text-status-preoccupied-fg", key: "wave1.find.status.closed" },
};

const ERROR_KEY: Record<FormError, MessageKey> = {
  date: "wave1.find.err.date",
  weeks: "wave1.find.err.weeks",
  range: "wave1.find.err.range",
  start: "wave1.find.err.start",
  end: "wave1.find.err.end",
  order: "wave1.find.err.order",
  window: "wave1.find.err.window",
};

/** ISO weekday names in the user's language (16 Feb 2026 is a Monday). */
function useWeekdayNames(): { long: string[]; short: string[] } {
  const { locale } = useI18n();
  return useMemo(() => {
    const tag = intlLocale(locale);
    const days = Array.from({ length: 7 }, (_, i) => new Date(Date.UTC(2026, 1, 16 + i)));
    return {
      long: days.map((d) => new Intl.DateTimeFormat(tag, { weekday: "long", timeZone: "UTC" }).format(d)),
      short: days.map((d) => new Intl.DateTimeFormat(tag, { weekday: "short", timeZone: "UTC" }).format(d)),
    };
  }, [locale]);
}

export function FindRoomView() {
  const { t, locale, n } = useI18n();
  useProfileLanguage();
  const fmt = useBookingFormat();
  const qc = useQueryClient();
  const params = useSearchParams();
  const ctx = useBookingContext();
  const dates = useBookingDates({}, ctx.isSuccess);
  const termId = ctx.data?.current_term_id ?? undefined;
  const today = dates.data?.today ?? "";
  const facets = useFacets();
  const recent = useRecentSearches();
  const rooms = useQuery({ queryKey: ["crbs", "booking-rooms"], queryFn: () => crbs.bookings.rooms(), retry: false, staleTime: 60_000 });
  const buildings = useMemo(() => [...new Set((rooms.data ?? []).map((r) => r.building).filter((b): b is string => !!b))].sort((a, b) => a.localeCompare(b, "tr")), [rooms.data]);
  const kinds = useMemo(() => Object.fromEntries((facets.data ?? []).map((f) => [String(f.id), f.kind])), [facets.data]);

  const [form, setForm] = useState<FindForm | null>(null);
  // the form starts on the booking clock's "today" (the backend's, so the e2e clock and the term agree)
  if (form === null && today) {
    const init = emptyForm(params.get("date") ?? today);
    const text = params.get("text");
    const head = params.get("headcount");
    setForm({ ...init, text: text ?? "", headcount: head ?? "" });
  }
  const f = form ?? emptyForm(today || "2026-01-01");
  const set = <K extends keyof FindForm>(k: K, v: FindForm[K]) => setForm((p) => ({ ...(p ?? f), [k]: v }));

  const [formError, setFormError] = useState<FormError | null>(null);
  const [result, setResult] = useState<FindResponse | null>(null);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const lastQuery = useRef<ReturnType<typeof buildQuery> | null>(null);
  const resultsRef = useRef<HTMLElement>(null);

  const run = async (next: FindForm = f, scroll = true) => {
    const built = buildQuery(next, termId, kinds);
    if ("error" in built) {
      setFormError(built.error);
      return;
    }
    setFormError(null);
    setSearchError(null);
    setBusy(true);
    lastQuery.current = built;
    try {
      const res = await wave1.find.search(built.query);
      setResult(res);
      void qc.invalidateQueries({ queryKey: w1Keys.recent });
      if (scroll && window.matchMedia("(max-width: 1023px)").matches) resultsRef.current?.scrollIntoView({ block: "start" });
    } catch (e) {
      const err = wave1Error(e);
      if (err.status === 429) setSearchError(t("wave1.find.rateLimited"));
      else setSearchError(errorText(err, locale));
    } finally {
      setBusy(false);
    }
  };

  // reserve: the room's day grid (the sheet needs it), its periods for the result's span
  const [target, setTarget] = useState<BookTarget | null>(null);
  const [opening, setOpening] = useState<string | null>(null);
  const reserve = async (key: string, roomId: number, date: string, start: number, end: number, request = false) => {
    setOpening(key);
    try {
      const info = rooms.data?.find((r) => r.id === roomId) ?? (await crbs.bookings.room(roomId));
      const q: GridQuery = { display: "day", date, term_id: termId, room_group_id: info.room_group_id ?? undefined };
      const fetched = await qc.fetchQuery({ queryKey: crbsKeys.grid(q), queryFn: () => crbs.bookings.grid(q), staleTime: 0 });
      const grid = request ? asRequestable(fetched, roomId, date, start, end) : fetched;
      const span = reserveSpan(slotsFor(grid, roomId, date, start, end));
      if (!span) {
        toast.error(t("wave1.find.notFree"));
        void run(f, false);
        return;
      }
      setTarget({ slot: span[0]!, grid, span });
    } catch (e) {
      toast.error(errorText(wave1Error(e), locale));
    } finally {
      setOpening(null);
    }
  };

  const days = useWeekdayNames();
  const results = result?.results ?? [];
  const free = results.filter((r) => ACTIONABLE.has(r.status));
  const others = results.filter((r) => !ACTIONABLE.has(r.status));
  const multi = (result?.slots.length ?? 0) > 1;
  // the form starts from the backend's booking clock and the user's facets: client-only (no #418 mismatch)
  const hydrated = useHydrated();
  if (!hydrated) return <Loading />;

  return (
    <div className="flex flex-col gap-5" data-testid="find-room">
      <PageTitle title={t("wave1.find.title")} subtitle={t("wave1.find.lead")} />
      <div className="grid gap-5 lg:grid-cols-[minmax(320px,400px)_1fr] lg:items-start">
        <div className="flex flex-col gap-4 lg:sticky lg:top-16">
          <Card className="gap-0 px-4 py-4">
            <form
              className="flex flex-col gap-4"
              aria-label={t("wave1.find.title")}
              onSubmit={(e) => {
                e.preventDefault();
                void run();
              }}
            >
              <fieldset className="flex flex-col gap-2">
                <legend className="mb-2 type-headline text-label-1">{t("wave1.find.when")}</legend>
                <SegmentedControl<WhenMode>
                  aria-label={t("wave1.find.when")}
                  size="sm"
                  fill
                  value={f.when}
                  onValueChange={(v) => set("when", v)}
                  options={[
                    { value: "date", label: t("wave1.find.mode.date") },
                    { value: "weekday", label: t("wave1.find.mode.weekday") },
                    { value: "range", label: t("wave1.find.mode.range") },
                  ]}
                />
                {f.when === "date" ? (
                  <Field label={t("wave1.find.date")} htmlFor="fr-date" error={formError === "date" ? t(ERROR_KEY.date) : null}>
                    <DateField id="fr-date" value={f.date} onChange={(v) => set("date", v)} data-testid="fr-date" />
                  </Field>
                ) : f.when === "weekday" ? (
                  <div className="grid grid-cols-2 gap-2">
                    <Field label={t("wave1.find.weekday")} htmlFor="fr-weekday">
                      <SelectField id="fr-weekday" value={String(f.weekday)} onChange={(e) => set("weekday", Number(e.target.value))}>
                        {days.long.slice(0, 6).map((d, i) => (
                          <option key={d} value={i + 1}>
                            {d}
                          </option>
                        ))}
                      </SelectField>
                    </Field>
                    <Field label={t("wave1.find.weeks")} htmlFor="fr-weeks" hint={t("wave1.find.weeksHint")} error={formError === "weeks" ? t(ERROR_KEY.weeks) : null}>
                      <Input id="fr-weeks" inputMode="numeric" placeholder="3-5, 7" value={f.weeks} onChange={(e) => set("weeks", e.target.value)} />
                    </Field>
                  </div>
                ) : (
                  <div className="flex flex-col gap-2">
                    <div className="grid grid-cols-2 gap-2">
                      <Field label={t("wave1.find.from")} htmlFor="fr-from" error={formError === "range" ? t(ERROR_KEY.range) : null}>
                        <DateField id="fr-from" value={f.dateFrom} onChange={(v) => set("dateFrom", v)} />
                      </Field>
                      <Field label={t("wave1.find.to")} htmlFor="fr-to">
                        <DateField id="fr-to" value={f.dateTo} min={f.dateFrom || undefined} onChange={(v) => set("dateTo", v)} />
                      </Field>
                    </div>
                    <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("wave1.find.onDays")}>
                      {days.short.slice(0, 6).map((d, i) => (
                        <Chip key={d} size="sm" selected={f.weekdays.includes(i + 1)} onSelectedChange={(on) => set("weekdays", on ? [...f.weekdays, i + 1] : f.weekdays.filter((x) => x !== i + 1))} aria-label={days.long[i]}>
                          {d}
                        </Chip>
                      ))}
                    </div>
                  </div>
                )}
              </fieldset>

              <fieldset className="flex flex-col gap-2">
                <legend className="mb-2 type-headline text-label-1">{t("wave1.find.time")}</legend>
                <SegmentedControl<TimeMode>
                  aria-label={t("wave1.find.time")}
                  size="sm"
                  fill
                  value={f.time}
                  onValueChange={(v) => set("time", v)}
                  options={[
                    { value: "clock", label: t("wave1.find.mode.clock") },
                    { value: "periods", label: t("wave1.find.mode.periods") },
                    { value: "duration", label: t("wave1.find.mode.duration") },
                  ]}
                />
                {f.time === "clock" ? (
                  <div className="grid grid-cols-2 gap-2">
                    <Field label={t("wave1.find.start")} htmlFor="fr-start" error={formError === "start" ? t(ERROR_KEY.start) : null}>
                      <Input id="fr-start" inputMode="numeric" placeholder="10:10" value={f.start} onChange={(e) => set("start", e.target.value)} data-testid="fr-start" />
                    </Field>
                    <Field label={t("wave1.find.end")} htmlFor="fr-end" error={formError === "end" || formError === "order" ? t(ERROR_KEY[formError]) : null}>
                      <Input id="fr-end" inputMode="numeric" placeholder="12:30" value={f.end} onChange={(e) => set("end", e.target.value)} data-testid="fr-end" />
                    </Field>
                  </div>
                ) : f.time === "periods" ? (
                  <div className="grid grid-cols-2 gap-2">
                    <Field label={t("wave1.find.fromPeriod")} htmlFor="fr-p1">
                      <SelectField id="fr-p1" value={String(f.startPeriod)} onChange={(e) => set("startPeriod", Number(e.target.value))}>
                        {Array.from({ length: 18 }, (_, i) => (
                          <option key={i} value={i + 1}>
                            {t("wave1.find.periodN", { n: i + 1 })}
                          </option>
                        ))}
                      </SelectField>
                    </Field>
                    <Field label={t("wave1.find.toPeriod")} htmlFor="fr-p2" error={formError === "order" ? t(ERROR_KEY.order) : null}>
                      <SelectField id="fr-p2" value={String(f.endPeriod)} onChange={(e) => set("endPeriod", Number(e.target.value))}>
                        {Array.from({ length: 18 }, (_, i) => (
                          <option key={i} value={i + 1}>
                            {t("wave1.find.periodN", { n: i + 1 })}
                          </option>
                        ))}
                      </SelectField>
                    </Field>
                  </div>
                ) : (
                  <div className="grid grid-cols-3 gap-2">
                    <Field label={t("wave1.find.duration")} htmlFor="fr-dur">
                      <SelectField id="fr-dur" value={String(f.durationPeriods)} onChange={(e) => set("durationPeriods", Number(e.target.value))}>
                        {Array.from({ length: 8 }, (_, i) => (
                          <option key={i} value={i + 1}>
                            {t("wave1.find.periodsN", { n: i + 1 })}
                          </option>
                        ))}
                      </SelectField>
                    </Field>
                    <Field label={t("wave1.find.between")} htmlFor="fr-w1" error={formError === "start" ? t(ERROR_KEY.start) : null}>
                      <Input id="fr-w1" inputMode="numeric" value={f.windowStart} onChange={(e) => set("windowStart", e.target.value)} />
                    </Field>
                    <Field label={t("wave1.find.and")} htmlFor="fr-w2" error={formError === "window" ? t(ERROR_KEY.window) : null}>
                      <Input id="fr-w2" inputMode="numeric" value={f.windowEnd} onChange={(e) => set("windowEnd", e.target.value)} />
                    </Field>
                  </div>
                )}
              </fieldset>

              <div className="grid grid-cols-[1fr_auto] items-end gap-2">
                <Field label={t("wave1.find.headcount")} htmlFor="fr-head" hint={t("wave1.find.headcountHint")}>
                  <Input id="fr-head" type="number" min={0} max={5000} inputMode="numeric" placeholder="0" value={f.headcount} onChange={(e) => set("headcount", e.target.value)} data-testid="fr-headcount" />
                </Field>
                <label className="flex h-8 items-center gap-2 type-footnote text-label-2">
                  <Switch checked={f.purpose === "exam"} onCheckedChange={(v) => set("purpose", v ? "exam" : "teaching")} aria-label={t("wave1.find.exam")} />
                  {t("wave1.find.exam")}
                </label>
              </div>

              {facets.data?.length ? <FeaturePicker facets={facets.data} value={f.features} onChange={(v) => set("features", v)} /> : null}

              {buildings.length ? (
                <div className="flex flex-col gap-1.5">
                  <span className="type-footnote font-medium text-label-2">{t("wave1.find.buildings")}</span>
                  <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("wave1.find.buildings")}>
                    {buildings.map((b) => (
                      <Chip key={b} size="sm" icon={<Building2 aria-hidden />} selected={f.buildings.includes(b)} onSelectedChange={(on) => set("buildings", on ? [...f.buildings, b] : f.buildings.filter((x) => x !== b))}>
                        {buildingLabel(b, t)}
                      </Chip>
                    ))}
                  </div>
                </div>
              ) : null}

              <Field label={t("wave1.find.text")} htmlFor="fr-text" hint={t("wave1.find.textHint")}>
                <Input id="fr-text" type="search" value={f.text} placeholder={t("wave1.find.textPlaceholder")} onChange={(e) => set("text", e.target.value)} data-testid="fr-text" />
              </Field>

              <div className="flex flex-col gap-2">
                <label className="flex items-center justify-between gap-3 type-callout text-label-1">
                  {t("wave1.find.showBusy")}
                  <Switch checked={f.showBusy} onCheckedChange={(v) => set("showBusy", v)} aria-label={t("wave1.find.showBusy")} />
                </label>
                {f.when === "date" ? (
                  <label className="flex items-center justify-between gap-3 type-callout text-label-1">
                    {t("wave1.find.otherDays")}
                    <Switch checked={f.otherDays} onCheckedChange={(v) => set("otherDays", v)} aria-label={t("wave1.find.otherDays")} />
                  </label>
                ) : null}
              </div>

              <Button type="submit" disabled={busy || !form} aria-busy={busy || undefined} data-testid="fr-search">
                <BusyLabel busy={busy} label={t("busy.searching")} icon={<Search aria-hidden />}>
                {busy ? t("wave1.find.searching") : t("wave1.find.search")}</BusyLabel>
              </Button>
            </form>
          </Card>
          <RecentSearches
            items={recent.data ?? []}
            onPick={(body) => {
              const next = formFromRecent(body, f);
              setForm(next);
              void run(next);
            }}
          />
        </div>

        <section ref={resultsRef} aria-labelledby="fr-results" aria-busy={busy} className="flex min-w-0 scroll-mt-16 flex-col gap-3">
          <h2 id="fr-results" className="sr-only">
            {t("wave1.find.results")}
          </h2>
          {searchError ? <Alert tone="error">{searchError}</Alert> : null}
          {!result && !searchError ? <p className="py-6 type-callout text-label-2">{t("wave1.find.empty")}</p> : null}
          {result ? (
            <>
              <div className="flex flex-wrap items-baseline justify-between gap-2" role="status" aria-live="polite">
                <p className="type-title-3 text-label-1 outline-hidden" data-testid="fr-summary" tabIndex={-1} data-focus-fallback>
                  {result.summary ? (locale === "tr" ? result.summary.text_tr : result.summary.text_en) : t("wave1.find.count", { n: results.length })}
                </p>
                {result.time ? (
                  <p className="type-footnote text-label-3 tabular-nums">
                    {fmt.time(result.time.start)}–{fmt.time(result.time.end)}
                    {result.timing_ms != null ? ` · ${t("wave1.find.ms", { ms: n(Math.round(result.timing_ms)) })}` : null}
                  </p>
                ) : null}
              </div>
              {result.closed_dates.length ? (
                <Alert tone="warning" title={t("wave1.find.closedTitle", { n: result.closed_dates.length })}>
                  {result.closed_dates
                    .slice(0, 6)
                    .map((c) => `${fmt.short(c.date)}${c.holiday ? ` (${c.holiday})` : ""}`)
                    .join(", ")}
                </Alert>
              ) : null}
              {free.length ? (
                <Card className="gap-0 overflow-hidden py-0">
                  <ul data-testid="fr-results">
                    {free.map((r, i) => (
                      <ResultRow key={r.room_id} row={r} rank={i + 1} multi={multi} headcount={Number(f.headcount) || 0} opening={opening === `r${r.room_id}`} onReserve={() => {
                        const date = firstFreeDate(r, result.slots);
                        if (date) void reserve(`r${r.room_id}`, r.room_id, date, r.start_period, r.end_period, r.action === "request");
                      }} />
                    ))}
                  </ul>
                </Card>
              ) : (
                <div className="flex flex-col items-start gap-2" data-testid="fr-none">
                  <p className="type-callout text-label-2">{f.text.trim() ? t("wave1.find.noneText", { text: f.text.trim() }) : t("wave1.find.noneFree")}</p>
                  {f.text.trim() ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        const next = { ...f, text: "" };
                        setForm(next);
                        void run(next, false);
                      }}
                      data-testid="fr-clear-text"
                    >
                      {t("wave1.find.clearText")}
                    </Button>
                  ) : null}
                </div>
              )}
              {result.alternatives.length ? (
                <section aria-labelledby="fr-alts" className="flex flex-col gap-2">
                  <h3 id="fr-alts" className="type-headline text-label-1">
                    {t("wave1.find.alternatives")}
                  </h3>
                  <p className="type-footnote text-label-2">{t("wave1.find.alternativesLead")}</p>
                  <Card variant="plain" className="gap-0 overflow-hidden py-0">
                    <ul data-testid="fr-alternatives">
                      {result.alternatives.map((a, i) => (
                        <AlternativeRow key={`${a.kind}-${a.room_id}-${i}`} alt={a} opening={opening === `a${i}`} onReserve={() => {
                          const date = a.dates[0] ?? a.date ?? result.slots[0]?.date;
                          if (date) void reserve(`a${i}`, a.room_id, date, a.start_period, a.end_period);
                        }} />
                      ))}
                    </ul>
                  </Card>
                </section>
              ) : null}
              {others.length ? (
                <details className="group rounded-xl">
                  <summary className="flex cursor-pointer list-none items-center gap-1.5 rounded-lg py-1 type-callout text-label-2 outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)">
                    <ChevronDown className="size-4 transition-transform duration-(--dur-fast) group-open:rotate-180" aria-hidden />
                    {t("wave1.find.othersN", { n: others.length })}
                  </summary>
                  <Card variant="plain" className="mt-2 gap-0 overflow-hidden py-0">
                    <ul>
                      {others.map((r, i) => (
                        <ResultRow key={r.room_id} row={r} rank={free.length + i + 1} multi={multi} headcount={Number(f.headcount) || 0} opening={false} />
                      ))}
                    </ul>
                  </Card>
                </details>
              ) : null}
            </>
          ) : null}
        </section>
      </div>
      <BookSheet
        target={target}
        fmt={fmt}
        onOpenChange={(o) => {
          if (o) return;
          setTarget(null);
          // the slot may now be booked or requested: refresh the ranking quietly
          if (result) void run(f, false);
        }}
      />
    </div>
  );
}

/** "A Blok" stays "A Blok"; a bare "A" becomes "A Blok" / "A block" (persona U-10: no "A Blok Blok"). */
function buildingLabel(b: string, t: ReturnType<typeof useI18n>["t"]): string {
  return /\b(blok|bloğu|block|bina|building)\b/i.test(b) || b.length > 3 ? b : t("wave1.find.building", { b });
}

/* ------------------------------------------------------------------------------------- features */

function FeaturePicker({ facets, value, onChange }: { facets: Feature[]; value: FindForm["features"]; onChange: (v: FindForm["features"]) => void }) {
  const { t } = useI18n();
  const setOne = (id: number, v: true | number | number[] | null) => {
    const next = { ...value };
    if (v === null || (Array.isArray(v) && v.length === 0)) delete next[String(id)];
    else next[String(id)] = v;
    onChange(next);
  };
  const booleans = facets.filter((x) => x.kind === "BOOLEAN");
  const numbers = facets.filter((x) => x.kind === "NUMBER");
  const options = facets.filter((x) => x.kind === "SELECT" || x.kind === "MULTISELECT");
  return (
    <div className="flex flex-col gap-2" data-testid="fr-features">
      <span className="type-footnote font-medium text-label-2">{t("wave1.find.features")}</span>
      {booleans.length ? (
        <div className="flex flex-wrap gap-1.5" role="group" aria-label={t("wave1.find.features")}>
          {booleans.map((x) => {
            const n = x.counts?.true;
            return (
              <Chip key={x.id} size="sm" selected={value[String(x.id)] === true} onSelectedChange={(on) => setOne(x.id, on ? true : null)} data-testid={`fr-feature-${x.id}`}>
                {x.name}
                {n !== undefined ? <span className="text-label-3 tabular-nums">{n}</span> : null}
              </Chip>
            );
          })}
        </div>
      ) : null}
      {numbers.map((x) => {
        const v = value[String(x.id)];
        return (
          <label key={x.id} className="flex items-center justify-between gap-3 type-callout text-label-1">
            <span className="min-w-0 truncate">{x.name}</span>
            <span className="flex items-center gap-1.5 type-footnote text-label-2">
              ≥
              <Input
                type="number"
                min={0}
                inputMode="decimal"
                className="h-7 w-20"
                aria-label={t("wave1.find.atLeast", { name: x.name })}
                value={typeof v === "number" ? v : ""}
                onChange={(e) => setOne(x.id, e.target.value === "" ? null : Math.max(0, Number(e.target.value)))}
              />
              {x.unit ?? ""}
            </span>
          </label>
        );
      })}
      {options.map((x) => {
        const v = value[String(x.id)];
        const picked = Array.isArray(v) ? v : [];
        return (
          <div key={x.id} className="flex flex-col gap-1" role="group" aria-label={x.name}>
            <span className="type-footnote text-label-3">{x.name}</span>
            <div className="flex flex-wrap gap-1.5">
              {x.options.map((o) => (
                <Chip key={o.id} size="sm" selected={picked.includes(o.id)} onSelectedChange={(on) => setOne(x.id, on ? [...picked, o.id] : picked.filter((p) => p !== o.id))}>
                  {o.value}
                </Chip>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* --------------------------------------------------------------------------------------- results */

function StatusTag({ status }: { status: string }) {
  const { t } = useI18n();
  const s = STATUS[status] ?? STATUS.busy!;
  return (
    <span className={cn("inline-flex h-6 shrink-0 items-center gap-1 rounded-full px-2 type-caption", s.cls)} data-status={status}>
      <s.icon className="size-3.5" aria-hidden />
      {t(s.key)}
    </span>
  );
}

/** Seats used by the group: a static bar (no animation: it changes on every search). */
function FitBar({ capacity, headcount }: { capacity: number; headcount: number }) {
  const { t } = useI18n();
  if (!capacity || !headcount) return null;
  const used = Math.min(1, headcount / capacity);
  return (
    <span className="flex items-center gap-1.5" aria-label={t("wave1.find.fitAria", { used: headcount, cap: capacity })}>
      <span aria-hidden className="relative block h-1.5 w-16 overflow-hidden rounded-full bg-fill-1">
        <span className="absolute inset-y-0 left-0 rounded-full bg-(--accent)" style={{ width: `${Math.round(used * 100)}%` }} />
      </span>
      <span aria-hidden className="type-caption text-label-3 tabular-nums">
        {headcount}/{capacity}
      </span>
    </span>
  );
}

function ResultRow({ row: r, rank, multi, headcount, opening, onReserve }: { row: FindRow; rank: number; multi: boolean; headcount: number; opening: boolean; onReserve?: () => void }) {
  const { t, locale } = useI18n();
  const fmt = useBookingFormat();
  const reason = pickLang(r.reason, locale);
  const extra = r.reasons.map((x) => pickLang(x, locale)).filter((x) => x && x !== reason);
  const request = r.action === "request";
  return (
    <li className="flex flex-col gap-2 px-4 py-3 not-last:edge-hairline-b sm:flex-row sm:items-start sm:gap-4" data-testid={`fr-room-${r.code}`} data-status={r.status} data-action={r.action}>
      <span className="hidden w-5 pt-0.5 text-right type-footnote text-label-3 tabular-nums sm:block" aria-hidden>
        {rank}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <p className="type-headline text-label-1">{r.name}</p>
          <StatusTag status={r.status} />
          {multi ? <span className="type-footnote text-label-2 tabular-nums">{t("wave1.find.freeDates", { free: r.free_dates, open: r.open_dates })}</span> : null}
        </div>
        <p className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 type-footnote text-label-2">
          <span>{[r.capacity ? t("crbs.grid.seats", { n: r.capacity }) : t("wave1.find.status.capacity_unknown"), r.building ? buildingLabel(r.building, t) : null, ...r.features.slice(0, 3)].filter(Boolean).join(" · ")}</span>
          <FitBar capacity={r.capacity ?? 0} headcount={headcount} />
        </p>
        {reason ? <p className="mt-1 type-callout text-label-1">{reason}</p> : null}
        {extra.length ? <p className="type-footnote text-label-3">{extra.join(" · ")}</p> : null}
        {r.busy_with ? <p className="type-footnote text-label-2">{t("wave1.find.busyWith", { what: r.busy_with })}</p> : null}
        {request ? <p className="mt-1 type-footnote text-tint-text">{t("wave1.find.needsApproval")}</p> : null}
        {multi && r.per_date?.length ? (
          <details className="mt-1">
            <summary className="cursor-pointer type-footnote text-label-2 outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)">{t("wave1.find.perDate")}</summary>
            <ul className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 type-footnote sm:grid-cols-3">
              {r.per_date.map((d) => (
                <li key={d.date} className="flex items-center gap-1.5 text-label-2">
                  <span className="tabular-nums">{fmt.short(d.date)}</span>
                  <span className={d.status === "free" ? "text-status-feasible-fg" : "text-label-3"}>{STATUS[d.status] ? t(STATUS[d.status]!.key) : d.status}</span>
                </li>
              ))}
            </ul>
          </details>
        ) : null}
      </div>
      {onReserve && r.action !== "none" ? (
        <Button size="sm" variant="outline" className="min-h-11 self-start sm:min-h-0" onClick={onReserve} disabled={opening} aria-label={t(request ? "wave1.find.requestRoom" : "wave1.find.reserveRoom", { room: r.name })} data-testid={`fr-reserve-${r.code}`}>
          {opening ? <Loader2 className="animate-spin" aria-hidden /> : request ? <Stamp aria-hidden /> : <CalendarClock aria-hidden />}
          {t(request ? "wave1.find.request" : "wave1.find.reserve")}
        </Button>
      ) : null}
    </li>
  );
}

const ALT_KIND: Record<string, MessageKey> = { time: "wave1.find.alt.time", day: "wave1.find.alt.day", near_miss: "wave1.find.alt.near_miss" };

function AlternativeRow({ alt: a, opening, onReserve }: { alt: FindAlternative; opening: boolean; onReserve: () => void }) {
  const { t, locale } = useI18n();
  const fmt = useBookingFormat();
  const date = a.dates[0] ?? a.date;
  return (
    <li className="flex items-center gap-3 px-4 py-2.5 not-last:edge-hairline-b" data-testid={`fr-alt-${a.code}`}>
      <div className="min-w-0 flex-1">
        <p className="type-callout font-medium text-label-1">
          {a.name}
          <span className="ml-2 type-footnote font-normal text-label-3">
            {t(ALT_KIND[a.kind] ?? "wave1.find.alt.other")}
            {date ? ` · ${fmt.weekday(date)}` : ""} · P{a.start_period}–P{a.end_period}
          </span>
        </p>
        <p className="type-footnote text-label-2">{pickLang(a.reason, locale)}</p>
      </div>
      {a.kind !== "near_miss" ? (
        <Button size="sm" variant="outline" className="min-h-11 sm:min-h-0" onClick={onReserve} disabled={opening} aria-label={t("wave1.find.reserveRoom", { room: a.name })} aria-busy={opening || undefined}>
          <BusyLabel busy={opening} label={t("busy.opening")}>
          {t("wave1.find.reserve")}</BusyLabel>
        </Button>
      ) : null}
    </li>
  );
}

/* --------------------------------------------------------------------------------------- recent */

function RecentSearches({ items, onPick }: { items: Record<string, unknown>[]; onPick: (body: Record<string, unknown>) => void }) {
  const { t } = useI18n();
  const fmt = useBookingFormat();
  const days = useWeekdayNames();
  if (!items.length) return null;
  const label = (body: Record<string, unknown>): ReactNode => {
    const p = recentParts(body);
    const when = p.date ? fmt.short(p.date) : p.weekday ? days.long[p.weekday - 1] : p.range ? `${fmt.short(p.range[0])}–${fmt.short(p.range[1])}` : "";
    return [when, p.time, p.headcount ? t("wave1.find.people", { n: p.headcount }) : null, p.text ? `“${p.text}”` : null].filter(Boolean).join(" · ");
  };
  return (
    <section aria-labelledby="fr-recent" className="flex flex-col gap-2">
      <h2 id="fr-recent" className="flex items-center gap-1.5 type-footnote font-semibold text-label-3">
        <History className="size-3.5" aria-hidden />
        {t("wave1.find.recent")}
      </h2>
      <ul className="flex flex-col gap-1" data-testid="fr-recent">
        {items.slice(0, 6).map((body, i) => (
          <li key={i}>
            <button type="button" onClick={() => onPick(body)} className="w-full truncate rounded-lg px-2 py-1.5 text-left type-callout text-label-1 outline-hidden hover:bg-fill-2 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)">
              {label(body)}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
