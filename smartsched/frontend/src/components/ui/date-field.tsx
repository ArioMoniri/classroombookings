"use client"
// SmartSched DateField — a localised date field (design-system overhaul 2026-10-15, review §2 "Selects / dates").
// Native <input type="date"> rendered mm/dd/yyyy inside a Turkish UI; this field always formats with
// Intl.DateTimeFormat(locale) (tr: gg.aa.yyyy → 15.10.2026, en: 10/15/2026), accepts typed input in the same
// order, and opens a month grid in a Popover. Value in/out is ISO "YYYY-MM-DD" ("" = empty).
// Keyboard (APG date picker dialog): Alt+↓ or the calendar button opens; in the grid ← → ↑ ↓ move by day/week,
// PageUp/PageDown by month, Home/End to the week edges, Enter/Space picks, Escape closes and returns focus.
// Original work; references: Apple Calendar / Linear date popovers (compact month grid, today ring).
// Touch (2026-10-16): 16 px input text on phones (no iOS zoom), a 44 × 44 hit area on the calendar trigger
// (ui/hit-area.ts), month arrows / Today / Clear on the ui Button, and 44 px day cells in a wider grid on coarse pointers.
import * as React from "react"
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react"
import { cn } from "cn"

import { Button, IconButton } from "@/components/ui/button"
import { fieldSize, fieldSurface, type FieldSize } from "@/components/ui/field-styles"
import { coarsePhoneText, coarseHitArea } from "@/components/ui/hit-area"
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover"
import { useI18n } from "@/lib/i18n/provider"
import { intlLocale } from "@/lib/i18n"

const ISO = /^(\d{4})-(\d{2})-(\d{2})$/

function toDate(iso: string): Date | null {
  const m = ISO.exec(iso)
  if (!m) return null
  const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]))
  return d.getUTCMonth() === +m[2] - 1 ? d : null
}
function toIso(d: Date): string {
  return d.toISOString().slice(0, 10)
}
function addDays(iso: string, n: number): string {
  const d = toDate(iso)!
  d.setUTCDate(d.getUTCDate() + n)
  return toIso(d)
}
function addMonths(iso: string, n: number): string {
  const d = toDate(iso)!
  const day = d.getUTCDate()
  d.setUTCDate(1)
  d.setUTCMonth(d.getUTCMonth() + n)
  const last = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 0)).getUTCDate()
  d.setUTCDate(Math.min(day, last))
  return toIso(d)
}

/** Formats ISO → the locale's numeric date (tr "15.10.2026", en "10/15/2026"). */
export function formatDateField(iso: string, locale: string): string {
  const d = toDate(iso)
  if (!d) return ""
  return new Intl.DateTimeFormat(locale, { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" }).format(d)
}

/** Parses typed text in the locale's field order (day/month/year for tr, month/day/year for en-US). */
export function parseDateField(text: string, locale: string): string | null {
  const parts = text.trim().split(/[./\-\s]+/).filter(Boolean)
  if (parts.length !== 3 || parts.some((p) => !/^\d+$/.test(p))) return null
  if (parts[0].length === 4) return validIso(+parts[0], +parts[1], +parts[2])
  const order = new Intl.DateTimeFormat(locale, { day: "2-digit", month: "2-digit", year: "numeric" })
    .formatToParts(new Date(2026, 9, 15))
    .filter((p) => p.type === "day" || p.type === "month" || p.type === "year")
    .map((p) => p.type)
  const v: Record<string, number> = {}
  order.forEach((k, i) => (v[k] = +parts[i]))
  if (v.year < 100) v.year += 2000
  return validIso(v.year, v.month, v.day)
}
function validIso(y: number, m: number, d: number): string | null {
  const iso = `${String(y).padStart(4, "0")}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`
  return toDate(iso) ? iso : null
}

const COPY = {
  tr: { open: "Takvimi aç", prev: "Önceki ay", next: "Sonraki ay", today: "Bugün", clear: "Temizle", invalid: "Geçersiz tarih" },
  en: { open: "Open calendar", prev: "Previous month", next: "Next month", today: "Today", clear: "Clear", invalid: "Invalid date" },
} as const

type DateFieldProps = {
  value: string
  onChange: (iso: string) => void
  min?: string
  max?: string
  id?: string
  name?: string
  disabled?: boolean
  required?: boolean
  size?: FieldSize
  className?: string
  "aria-label"?: string
  "aria-describedby"?: string
  "data-testid"?: string
  /** override the UI locale (tests) */
  locale?: string
}

export function DateField({
  value,
  onChange,
  min,
  max,
  id,
  name,
  disabled,
  required,
  size = "md",
  className,
  locale: localeProp,
  "aria-label": ariaLabel,
  "aria-describedby": describedBy,
  "data-testid": testId,
}: DateFieldProps) {
  const { locale: uiLocale } = useI18n()
  const locale = localeProp ?? intlLocale(uiLocale)
  const copy = COPY[locale.startsWith("tr") ? "tr" : "en"]
  const [text, setText] = React.useState(() => formatDateField(value, locale))
  const [invalid, setInvalid] = React.useState(false)
  const [open, setOpen] = React.useState(false)
  const today = React.useMemo(() => toIso(new Date(Date.UTC(new Date().getFullYear(), new Date().getMonth(), new Date().getDate()))), [])
  const [cursor, setCursor] = React.useState(value || today)
  const gridRef = React.useRef<HTMLDivElement>(null)
  const placeholder = React.useMemo(
    () =>
      new Intl.DateTimeFormat(locale, { day: "2-digit", month: "2-digit", year: "numeric" })
        .formatToParts(new Date(2026, 9, 15))
        .map((p) => (p.type === "day" ? (locale.startsWith("tr") ? "gg" : "dd") : p.type === "month" ? (locale.startsWith("tr") ? "aa" : "mm") : p.type === "year" ? (locale.startsWith("tr") ? "yyyy" : "yyyy") : p.value))
        .join(""),
    [locale],
  )

  // re-sync the text when the value or locale changes from outside (state adjusted during render, no effect)
  const [synced, setSynced] = React.useState(`${value}|${locale}`)
  if (synced !== `${value}|${locale}`) {
    setSynced(`${value}|${locale}`)
    setText(formatDateField(value, locale))
    setInvalid(false)
  }

  const inRange = (iso: string) => (!min || iso >= min) && (!max || iso <= max)
  const commit = (raw: string) => {
    if (!raw.trim()) {
      setInvalid(false)
      if (value) onChange("")
      return
    }
    const iso = parseDateField(raw, locale)
    if (!iso || !inRange(iso)) {
      setInvalid(true)
      return
    }
    setInvalid(false)
    if (iso !== value) onChange(iso)
    else setText(formatDateField(iso, locale))
  }

  const openPicker = (next: boolean) => {
    setOpen(next)
    if (next) setCursor(value || (min && today < min ? min : today))
  }
  React.useEffect(() => {
    if (!open) return
    const id = requestAnimationFrame(() => gridRef.current?.querySelector<HTMLElement>('[tabindex="0"]')?.focus())
    return () => cancelAnimationFrame(id)
  }, [open, cursor])

  const monthStart = cursor.slice(0, 8) + "01"
  const first = toDate(monthStart)!
  const lead = (first.getUTCDay() + 6) % 7 // Monday first (tr and the academic calendar)
  const gridStart = addDays(monthStart, -lead)
  const days = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i))
  const monthLabel = new Intl.DateTimeFormat(locale, { month: "long", year: "numeric", timeZone: "UTC" }).format(first)
  const weekdayFmt = new Intl.DateTimeFormat(locale, { weekday: "short", timeZone: "UTC" })
  const weekdays = days.slice(0, 7).map((d) => weekdayFmt.format(toDate(d)!))
  const dayLabel = new Intl.DateTimeFormat(locale, { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" })

  const onGridKey = (e: React.KeyboardEvent) => {
    const moves: Record<string, () => string> = {
      ArrowLeft: () => addDays(cursor, -1),
      ArrowRight: () => addDays(cursor, 1),
      ArrowUp: () => addDays(cursor, -7),
      ArrowDown: () => addDays(cursor, 7),
      PageUp: () => addMonths(cursor, -1),
      PageDown: () => addMonths(cursor, 1),
      Home: () => addDays(cursor, -((toDate(cursor)!.getUTCDay() + 6) % 7)),
      End: () => addDays(cursor, 6 - ((toDate(cursor)!.getUTCDay() + 6) % 7)),
    }
    const move = moves[e.key]
    if (move) {
      e.preventDefault()
      setCursor(move())
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault()
      if (inRange(cursor)) {
        onChange(cursor)
        setOpen(false)
      }
    }
  }

  return (
    <div data-slot="date-field" className={cn("relative inline-flex w-full min-w-0", className)}>
      <input
        id={id}
        name={name}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        value={text}
        placeholder={placeholder}
        disabled={disabled}
        required={required}
        aria-label={ariaLabel}
        aria-describedby={describedBy}
        aria-invalid={invalid || undefined}
        data-testid={testId}
        data-value={value}
        onChange={(e) => setText(e.target.value)}
        onBlur={(e) => commit(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit(e.currentTarget.value)
          if (e.key === "ArrowDown" && e.altKey) {
            e.preventDefault()
            openPicker(true)
          }
        }}
        className={cn(fieldSurface, fieldSize[size], "w-full min-w-0 pr-9 tnum", coarsePhoneText)}
      />
      {invalid ? <span className="sr-only" role="status">{copy.invalid}</span> : null}
      <Popover open={open} onOpenChange={openPicker}>
        <PopoverTrigger
          disabled={disabled}
          aria-label={copy.open}
          title={copy.open}
          className={cn("absolute inset-y-0 right-1 my-auto inline-flex size-(--control-h-xs) items-center justify-center rounded-md text-label-2 hover:bg-fill-2 hover:text-label-1 focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-(--focus)", coarseHitArea)}
        >
          <CalendarDays aria-hidden className="size-4 stroke-[1.75]" />
        </PopoverTrigger>
        <PopoverContent align="end" className="w-[17.5rem] gap-2 p-2.5 pointer-coarse:w-[min(21rem,calc(100vw-1.5rem))]">
          <div className="flex items-center justify-between">
            <IconButton label={copy.prev} size="sm" shape="rect" onClick={() => setCursor(addMonths(cursor, -1))} className="rounded-md text-label-2">
              <ChevronLeft aria-hidden className="size-4 stroke-[1.75]" />
            </IconButton>
            <p aria-live="polite" className="type-headline capitalize text-label-1">{monthLabel}</p>
            <IconButton label={copy.next} size="sm" shape="rect" onClick={() => setCursor(addMonths(cursor, 1))} className="rounded-md text-label-2">
              <ChevronRight aria-hidden className="size-4 stroke-[1.75]" />
            </IconButton>
          </div>
          <div ref={gridRef} role="grid" aria-label={monthLabel} onKeyDown={onGridKey} className="grid grid-cols-7 gap-0.5 pointer-coarse:gap-0">
            {weekdays.map((w) => (
              <span key={w} role="columnheader" aria-label={w} className="py-1 text-center type-caption text-label-3">{w}</span>
            ))}
            {days.map((d) => {
              const other = d.slice(0, 7) !== cursor.slice(0, 7)
              const picked = d === value
              const isToday = d === today
              const ok = inRange(d)
              return (
                <button
                  key={d}
                  type="button"
                  role="gridcell"
                  tabIndex={d === cursor ? 0 : -1}
                  aria-selected={picked}
                  aria-disabled={!ok || undefined}
                  aria-label={dayLabel.format(toDate(d)!)}
                  onClick={() => {
                    if (!ok) return
                    onChange(d)
                    setOpen(false)
                  }}
                  className={cn(
                    "relative inline-flex h-(--control-h-md) items-center justify-center rounded-md type-callout tnum hover:bg-fill-2 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--focus)",
                    other ? "text-label-3" : "text-label-1",
                    !ok && "cursor-not-allowed line-through opacity-50",
                    isToday && !picked && "font-semibold text-tint-text",
                    picked && "bg-tint text-tint-foreground hover:bg-(--accent-hover)",
                  )}
                >
                  {Number(d.slice(8))}
                </button>
              )
            })}
          </div>
          <div className="flex justify-between pt-1">
            <Button variant="ghost" size="xs" shape="rect" onClick={() => { if (inRange(today)) { onChange(today); setOpen(false) } }} className="rounded-md px-2 text-tint-text">{copy.today}</Button>
            {!required && value ? (
              <Button variant="ghost" size="xs" shape="rect" onClick={() => { onChange(""); setOpen(false) }} className="rounded-md px-2 font-normal text-label-2">{copy.clear}</Button>
            ) : null}
          </div>
        </PopoverContent>
      </Popover>
    </div>
  )
}
