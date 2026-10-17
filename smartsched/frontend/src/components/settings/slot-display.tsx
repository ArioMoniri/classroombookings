"use client";
/**
 * W3-SLOT · Ayarlar › Rezervasyon › Görünüm (docs/design/v3/slot-display.md §4): the administrator decides how a slot is
 * shown on every booking surface. Form on one side, a live preview on the other (desktop) or under the form (phone);
 * the preview renders the current schedule's real periods through the very components users get (BookingGrid,
 * FreeSlotsList, the quick-reserve slot label) with synthetic statuses, so it never calls the server per change.
 *
 * `SlotDisplaySettings` is the card (to be mounted in settings-view.tsx under its own tab: an ask for the
 * orchestrator, that file is not this lane's); `SlotDisplaySheet` opens the same card from /bookings for administrators.
 * Saving writes `booking.slot_display.*` through PUT /settings (planning.admin).
 */
import { RotateCcw } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";
import { BookingGrid } from "@/components/bookings/booking-grid";
import { dateFormatter } from "@/components/bookings/date-format";
import { FreeSlotsList } from "@/components/bookings/free-slots-list";
import { freeSlotsByRoom } from "@/components/bookings/reserve-model";
import { applySlotDisplay, BLOCK_MINUTES, DEFAULT_SLOT_DISPLAY, DESKTOP_VIEWS, duration, LENGTH_MAX, PHONE_VIEWS, periodVisible, SHORT_MINUTES, slotLabel, type DesktopView, type PhoneView, type SlotDisplay } from "@/components/bookings/slot-display";
import { useBookingFormat } from "@/components/bookings/use-booking-format";
import { useIsPhone } from "@/components/bookings/use-is-phone";
import { useSaveSlotDisplay, useSlotDisplay } from "@/components/bookings/use-slot-display";
import { BareButton, Button } from "@/components/ui/button";
import { BusyButton } from "@/components/ui/busy-label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { useBookingContext, useBookingGrid, type Grid, type GridPeriod, type GridSlot } from "@/lib/api/crbs";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";

type Surface = "grid" | "list" | "quick";

/** Today's periods of the default schedule (GET /bookings/grid, unfiltered: the form lists them all). */
function useSchedulePeriods(): { periods: GridPeriod[]; date: string | null; loading: boolean } {
  const ctx = useBookingContext();
  const grid = useBookingGrid({ display: "day" }, ctx.isSuccess);
  return { periods: grid.data?.periods ?? [], date: grid.data?.date ?? null, loading: ctx.isLoading || grid.isLoading };
}

export function SlotDisplaySettings({ onSaved, className }: { onSaved?: () => void; className?: string }) {
  const { t } = useI18n();
  const fmt = useBookingFormat();
  const saved = useSlotDisplay();
  const save = useSaveSlotDisplay();
  const { periods, date, loading } = useSchedulePeriods();
  const [draft, setDraft] = useState<SlotDisplay | null>(null);
  const v = draft ?? saved.display;
  const dirty = draft !== null && JSON.stringify(draft) !== JSON.stringify(saved.display);
  const set = <K extends keyof SlotDisplay>(k: K, value: SlotDisplay[K]) => setDraft((p) => ({ ...(p ?? saved.display), [k]: value }));
  const ids = { first: useId(), last: useId(), desktop: useId(), phone: useId(), min: useId(), max: useId(), block: useId(), short: useId(), weekend: useId() };
  const labelFormat = useMemo(() => ({ time: fmt.time, ordinal: (n: number) => t("slotDisplay.ordinal", { n }) }), [fmt, t]);
  const sample = periods[2] ?? periods[0];
  const short = periods.filter((p) => duration(p) < SHORT_MINUTES);
  const visibleCount = periods.filter((p) => periodVisible(p, v)).length;
  const orderError = !!(v.first_period && v.last_period && v.first_period > v.last_period);
  const noneVisible = periods.length > 0 && visibleCount === 0;
  const example = sample ? slotLabel(sample, v, labelFormat).inline : "";

  // the polite summary reads the effect of a change, debounced (slot-display.md §9)
  const [live, setLive] = useState("");
  useEffect(() => {
    const id = window.setTimeout(() => setLive(example ? t("slotDisplay.preview.live", { example, n: visibleCount, total: periods.length }) : ""), 500);
    return () => window.clearTimeout(id);
  }, [example, visibleCount, periods.length, t]);

  const submit = () => {
    if (orderError || noneVisible) {
      document.getElementById(ids.first)?.focus();
      return;
    }
    save.mutate(v, {
      onSuccess: () => {
        setDraft(null);
        toast.success(t("slotDisplay.saved"));
        onSaved?.();
      },
      onError: () => toast.error(t("slotDisplay.failed")),
    });
  };

  const periodOption = (p: GridPeriod) => `${slotLabel(p, { ...DEFAULT_SLOT_DISPLAY, label: "period", period_name: v.period_name }, labelFormat).inline} · ${fmt.time(p.time_start)}`;
  const unitLabel = (n: number) => (v.unit === "blocks" ? t("slotDisplay.length.blocks", { n, min: n * v.block_minutes }) : t("slotDisplay.length.periods", { n }));

  return (
    <div className={cn("grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]", className)} data-testid="slot-display-settings">
      <Card>
        <CardHeader>
          <CardTitle>{t("slotDisplay.title")}</CardTitle>
          <CardDescription>
            {t("slotDisplay.description")}{" "}
            <Link href="/admin/schedules" className="font-medium underline">
              {t("slotDisplay.schedulesLink")}
            </Link>
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-5">
          <Group legend={t("slotDisplay.unit.legend")}>
            <div role="radiogroup" aria-label={t("slotDisplay.unit.legend")} className="grid gap-2 sm:grid-cols-2">
              {(["periods", "blocks"] as const).map((u) => (
                <RadioCard key={u} checked={v.unit === u} onSelect={() => set("unit", u)} title={t(`slotDisplay.unit.${u}`)} help={t(`slotDisplay.unit.${u}Help`)} testId={`sd-unit-${u}`} glyph={<UnitGlyph unit={u} />} />
              ))}
            </div>
            {v.unit === "blocks" ? (
              <Row label={t("slotDisplay.unit.blockMinutes")} id={ids.block}>
                <SegmentedControl<string>
                  aria-labelledby={ids.block}
                  semantics="radiogroup"
                  size="sm"
                  value={String(v.block_minutes)}
                  onValueChange={(x) => set("block_minutes", Number(x) as 15 | 30 | 60)}
                  options={BLOCK_MINUTES.map((m) => ({ value: String(m), label: t("slotDisplay.unit.minutes", { n: m }) }))}
                  data-testid="sd-block"
                />
              </Row>
            ) : null}
          </Group>

          <Group legend={t("slotDisplay.label.legend")}>
            <SegmentedControl<SlotDisplay["label"]>
              aria-label={t("slotDisplay.label.legend")}
              semantics="radiogroup"
              fill
              value={v.label}
              onValueChange={(x) => set("label", x)}
              options={(["period", "time", "both"] as const).map((x) => ({ value: x, label: t(`slotDisplay.label.${x}`), testId: `sd-label-${x}` }))}
              data-testid="sd-label"
            />
            {v.label !== "time" ? (
              <SegmentedControl<SlotDisplay["period_name"]>
                aria-label={t("slotDisplay.periodName.legend")}
                semantics="radiogroup"
                fill
                size="sm"
                value={v.period_name}
                onValueChange={(x) => set("period_name", x)}
                options={(["schedule", "ordinal"] as const).map((x) => ({
                  value: x,
                  label: t(`slotDisplay.periodName.${x}`, { example: sample ? (x === "ordinal" ? t("slotDisplay.ordinal", { n: sample.start_period }) : sample.name || t("slotDisplay.ordinal", { n: sample.start_period })) : "" }),
                }))}
              />
            ) : null}
            {v.label !== "period" ? (
              <SegmentedControl<SlotDisplay["time_format"]>
                aria-label={t("slotDisplay.timeFormat.legend")}
                semantics="radiogroup"
                fill
                size="sm"
                value={v.time_format}
                onValueChange={(x) => set("time_format", x)}
                options={(["start", "range"] as const).map((x) => ({ value: x, label: t(`slotDisplay.timeFormat.${x}`, { example: sample ? (x === "start" ? fmt.time(sample.time_start) : `${fmt.time(sample.time_start)}–${fmt.time(sample.time_end)}`) : "" }) }))}
              />
            ) : null}
          </Group>

          <Group legend={t("slotDisplay.density.legend")} hint={t("slotDisplay.density.phoneNote")}>
            <SegmentedControl<SlotDisplay["density"]>
              aria-label={t("slotDisplay.density.legend")}
              semantics="radiogroup"
              fill
              value={v.density}
              onValueChange={(x) => set("density", x)}
              options={(["compact", "standard", "comfortable"] as const).map((x) => ({ value: x, label: t(`slotDisplay.density.${x}`), testId: `sd-density-${x}` }))}
              data-testid="sd-density"
            />
          </Group>

          <Group legend={t("slotDisplay.visible.legend")} hint={t("slotDisplay.visible.note")}>
            <div className="grid gap-3 sm:grid-cols-2">
              <Row label={t("slotDisplay.visible.first")} id={`${ids.first}-l`} htmlFor={ids.first}>
                <NativeSelect id={ids.first} value={String(v.first_period)} onChange={(e) => set("first_period", Number(e.target.value))} aria-invalid={orderError || undefined} aria-describedby={orderError ? `${ids.first}-err` : undefined} disabled={loading} data-testid="sd-first">
                  <option value="0">{t("slotDisplay.visible.all")}</option>
                  {periods.map((p) => (
                    <option key={p.id} value={p.start_period}>
                      {periodOption(p)}
                    </option>
                  ))}
                </NativeSelect>
              </Row>
              <Row label={t("slotDisplay.visible.last")} id={`${ids.last}-l`} htmlFor={ids.last}>
                <NativeSelect id={ids.last} value={String(v.last_period)} onChange={(e) => set("last_period", Number(e.target.value))} aria-invalid={orderError || undefined} disabled={loading} data-testid="sd-last">
                  <option value="0">{t("slotDisplay.visible.all")}</option>
                  {periods.map((p) => (
                    <option key={p.id} value={p.start_period}>
                      {periodOption(p)}
                    </option>
                  ))}
                </NativeSelect>
              </Row>
            </div>
            {orderError ? (
              <p id={`${ids.first}-err`} className="type-footnote text-status-infeasible-fg" role="alert">
                {t("slotDisplay.visible.errorOrder")}
              </p>
            ) : null}
            <SwitchRow id={ids.short} checked={v.hide_short} onChange={(x) => set("hide_short", x)} label={short.length ? t("slotDisplay.visible.hideShort", { list: short.map((p) => `${fmt.time(p.time_start)}–${fmt.time(p.time_end)}`).join(", ") }) : t("slotDisplay.visible.hideShortNone")} testId="sd-hide-short" />
            <SwitchRow id={ids.weekend} checked={v.hide_weekend} onChange={(x) => set("hide_weekend", x)} label={t("slotDisplay.visible.hideWeekend")} testId="sd-hide-weekend" />
            {periods.length ? (
              <p className={cn("type-footnote", noneVisible ? "text-status-infeasible-fg" : "text-label-2")} data-testid="sd-visible-summary">
                {t("slotDisplay.visible.summary", { n: visibleCount, total: periods.length })}
              </p>
            ) : !loading ? (
              <p className="type-footnote text-label-2">{t("slotDisplay.empty")}</p>
            ) : null}
          </Group>

          <Group legend={t("slotDisplay.defaultView.legend")}>
            <div className="grid gap-3 sm:grid-cols-2">
              <Row label={t("slotDisplay.defaultView.desktop")} id={`${ids.desktop}-l`} htmlFor={ids.desktop}>
                <NativeSelect id={ids.desktop} value={v.default_view_desktop ?? ""} onChange={(e) => set("default_view_desktop", (e.target.value || null) as DesktopView | null)} data-testid="sd-view-desktop">
                  <option value="">{t("slotDisplay.defaultView.org")}</option>
                  {DESKTOP_VIEWS.map((x) => (
                    <option key={x} value={x}>
                      {t(`slotDisplay.view.${x}`)}
                    </option>
                  ))}
                </NativeSelect>
              </Row>
              <Row label={t("slotDisplay.defaultView.phone")} id={`${ids.phone}-l`} htmlFor={ids.phone}>
                <NativeSelect id={ids.phone} value={v.default_view_phone} onChange={(e) => set("default_view_phone", e.target.value as PhoneView)} data-testid="sd-view-phone">
                  {PHONE_VIEWS.map((x) => (
                    <option key={x} value={x}>
                      {t(`slotDisplay.view.${x}`)}
                    </option>
                  ))}
                </NativeSelect>
              </Row>
            </div>
          </Group>

          <Group legend={t("slotDisplay.length.legend")} hint={t("slotDisplay.length.hint")}>
            <div className="grid gap-3 sm:grid-cols-2">
              <Row label={t("slotDisplay.length.min")} id={`${ids.min}-l`} htmlFor={ids.min}>
                <NativeSelect id={ids.min} value={String(v.min_length)} onChange={(e) => {
                  const n = Number(e.target.value);
                  setDraft((p) => {
                    const base = p ?? saved.display;
                    return { ...base, min_length: n, quick_span: Math.max(n, base.quick_span) };
                  });
                }} data-testid="sd-min-length">
                  {Array.from({ length: LENGTH_MAX }, (_, i) => i + 1).map((n) => (
                    <option key={n} value={n}>
                      {unitLabel(n)}
                    </option>
                  ))}
                </NativeSelect>
              </Row>
              <Row label={t("slotDisplay.length.max")} id={`${ids.max}-l`} htmlFor={ids.max}>
                <NativeSelect id={ids.max} value={String(v.quick_span)} onChange={(e) => set("quick_span", Number(e.target.value))} data-testid="sd-quick-span">
                  {Array.from({ length: LENGTH_MAX - v.min_length + 1 }, (_, i) => i + v.min_length).map((n) => (
                    <option key={n} value={n}>
                      {unitLabel(n)}
                    </option>
                  ))}
                </NativeSelect>
              </Row>
            </div>
          </Group>

          <p className="sr-only" aria-live="polite">
            {live}
          </p>
          <div className="sticky bottom-0 -mx-4 flex flex-wrap items-center gap-2 border-t border-hairline bg-(--mat-thick-solid) px-4 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">
            {dirty ? <span className="type-footnote text-label-2" data-testid="sd-unsaved">{t("slotDisplay.unsaved")}</span> : null}
            <Button variant="ghost" className="ml-auto" onClick={() => setDraft({ ...DEFAULT_SLOT_DISPLAY })} data-testid="sd-reset">
              <RotateCcw aria-hidden />
              {t("slotDisplay.reset")}
            </Button>
            <BusyButton busy={save.isPending} busyLabel={t("slotDisplay.saving")} disabled={!dirty || orderError || noneVisible} focusableWhenDisabled onClick={submit} data-testid="sd-save">
              {t("slotDisplay.save")}
            </BusyButton>
          </div>
        </CardContent>
      </Card>
      <SlotPreview display={v} periods={periods} date={date} />
    </div>
  );
}

/** The live preview: the real surfaces fed by today's periods and a fixed synthetic pattern (no server, no people). */
export function SlotPreview({ display, periods, date }: { display: SlotDisplay; periods: GridPeriod[]; date: string | null }) {
  const { t, locale } = useI18n();
  const [surface, setSurface] = useState<Surface>("grid");
  const fmt = useMemo(() => dateFormatter(undefined, locale), [locale]);
  const grid = useMemo(() => sampleGrid(periods, date ?? "2026-01-05", (n) => t("slotDisplay.preview.room", { n })), [periods, date, t]);
  const shown = useMemo(() => applySlotDisplay(grid, display), [grid, display]);
  const labelFormat = useMemo(() => ({ time: fmt.time, ordinal: (n: number) => t("slotDisplay.ordinal", { n }) }), [fmt, t]);
  if (!periods.length) return null;
  return (
    <Card className="self-start lg:sticky lg:top-24" data-testid="slot-preview">
      <CardHeader>
        <CardTitle>{t("slotDisplay.preview.title")}</CardTitle>
        <CardDescription>{t("slotDisplay.preview.note")}</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <SegmentedControl<Surface>
          aria-label={t("slotDisplay.preview.surface")}
          size="sm"
          fill
          value={surface}
          onValueChange={setSurface}
          options={(["grid", "list", "quick"] as const).map((x) => ({ value: x, label: t(`slotDisplay.preview.${x}`), testId: `sd-preview-${x}` }))}
        />
        {/* a picture of the result: readable, not interactive */}
        <div inert aria-label={t("slotDisplay.preview.title")} className="max-w-full overflow-hidden" data-testid={`sd-preview-${surface}-body`}>
          {surface === "grid" ? (
            <BookingGrid grid={shown} columns="periods" fmt={fmt} multi={false} selected={EMPTY} onActivate={NOOP} slotDisplay={display} />
          ) : surface === "list" ? (
            <FreeSlotsList rooms={freeSlotsByRoom([shown])} loading={false} week={false} fmt={fmt} deptFirst={false} onReserve={NOOP} onRoomInfo={NOOP} slotDisplay={display} />
          ) : (
            <ul className="flex flex-wrap gap-2">
              {shown.periods.map((p) => (
                <li key={p.id} className="inline-flex min-h-9 items-center rounded-full bg-fill-2 px-3 type-callout text-label-1">
                  {slotLabel(p, display, labelFormat).inline}
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

const EMPTY: ReadonlySet<string> = new Set();
const NOOP = () => undefined;

/** Two sample rooms over the real periods: a fixed free / booked / class pattern (never real bookings). */
export function sampleGrid(periods: GridPeriod[], date: string, roomName: (n: number) => string): Grid {
  const rooms = [1, 2].map((n) => ({ id: -n, name: roomName(n), code: `S${n}`, capacity: n === 1 ? 40 : 24 }));
  const slots: GridSlot[] = [];
  periods.forEach((p, i) => {
    rooms.forEach((r, j) => {
      const k = (i + j * 2) % 5;
      if (k === 1) slots.push({ date, period_id: p.id, room_id: r.id, status: "timetable", reason: "timetable", label: "MAT 101" });
      else if (k === 3) slots.push({ date, period_id: p.id, room_id: r.id, status: "booked", reason: "single", booking: { id: -(i * 10 + j), type: "single", status: "BOOKED", date, weekday: 1, period_id: p.id, start_period: p.start_period, end_period: p.end_period, room_id: r.id, room_name: r.name, user_hidden: true, notes_hidden: true, is_owner: false } });
      else slots.push({ date, period_id: p.id, room_id: r.id, status: "available", allow_single: true, allow_recur: false });
    });
  });
  return {
    display: "day",
    term: { id: 0, code: "", name: "", start: date, end: date },
    date,
    dates: [{ date, weekday: 1, open: true }],
    periods,
    rooms,
    slots,
    nav: {},
    limits: {},
    problems: [],
  };
}

function Group({ legend, hint, children }: { legend: string; hint?: string; children: ReactNode }) {
  return (
    <fieldset className="flex min-w-0 flex-col gap-2">
      <legend className="mb-1 type-headline text-label-1">{legend}</legend>
      {children}
      {hint ? <p className="type-footnote text-label-2">{hint}</p> : null}
    </fieldset>
  );
}

function Row({ label, id, htmlFor, children }: { label: string; id: string; htmlFor?: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label id={id} htmlFor={htmlFor} className="type-footnote font-medium text-label-2">
        {label}
      </label>
      {children}
    </div>
  );
}

function SwitchRow({ id, checked, onChange, label, testId }: { id: string; checked: boolean; onChange: (v: boolean) => void; label: string; testId: string }) {
  return (
    <label htmlFor={id} className="flex min-h-11 items-center justify-between gap-3 type-callout text-label-1">
      <span className="min-w-0">{label}</span>
      <Switch id={id} checked={checked} onCheckedChange={(x) => onChange(!!x)} data-testid={testId} />
    </label>
  );
}

function RadioCard({ checked, onSelect, title, help, glyph, testId }: { checked: boolean; onSelect: () => void; title: string; help: string; glyph: ReactNode; testId: string }) {
  return (
    <BareButton
      role="radio"
      aria-checked={checked}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === "ArrowRight" || e.key === "ArrowLeft" || e.key === "ArrowDown" || e.key === "ArrowUp") {
          e.preventDefault();
          const sib = (e.key === "ArrowRight" || e.key === "ArrowDown" ? e.currentTarget.nextElementSibling : e.currentTarget.previousElementSibling) as HTMLButtonElement | null;
          sib?.focus();
          sib?.click();
        }
      }}
      tabIndex={checked ? 0 : -1}
      data-testid={testId}
      className={cn(
        "flex min-h-[88px] items-center gap-3 rounded-xl px-3 py-2 text-left edge-hairline outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-offset-2 focus-visible:outline-(--focus)",
        checked ? "bg-tint-soft inset-ring-2 inset-ring-(--accent)" : "bg-(--mat-thick-solid) hover:bg-fill-3",
      )}
    >
      {glyph}
      <span className="flex min-w-0 flex-col">
        <span className="type-headline text-label-1">{title}</span>
        <span className="type-footnote text-label-2">{help}</span>
      </span>
    </BareButton>
  );
}

function UnitGlyph({ unit }: { unit: "periods" | "blocks" }) {
  const sizes = unit === "periods" ? [10, 10, 10, 10] : [10, 14, 6, 12];
  return (
    <span aria-hidden className="flex h-12 w-10 shrink-0 flex-col justify-center gap-0.5 rounded-md bg-fill-3 px-1.5">
      {sizes.map((h, i) => (
        <span key={i} className="block w-full rounded-xs bg-tint" style={{ height: h * 0.6 + "px", opacity: 0.35 + i * 0.12 }} />
      ))}
    </span>
  );
}

/** /bookings › Görünüm for administrators: the same card in a sheet (right on desktop, bottom on phones). */
export function SlotDisplaySheet({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { t } = useI18n();
  const phone = useIsPhone();
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side={phone ? "bottom" : "right"} className="gap-0 data-[side=bottom]:max-h-[92dvh] data-[side=right]:w-full data-[side=right]:sm:max-w-5xl" data-testid="slot-display-sheet">
        <SheetHeader className="px-5 pt-5">
          <SheetTitle className="type-title-3">{t("slotDisplay.title")}</SheetTitle>
          <SheetDescription className="sr-only">{t("slotDisplay.description")}</SheetDescription>
        </SheetHeader>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 pb-5">{open ? <SlotDisplaySettings /> : null}</div>
      </SheetContent>
    </Sheet>
  );
}
