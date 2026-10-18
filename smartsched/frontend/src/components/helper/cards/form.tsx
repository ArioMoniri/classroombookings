"use client";
/**
 * HX-04 / HX-05 (helper.md §4.2, A1): the mini `form` (missing or ambiguous arguments of a write, or "Değiştir" on a
 * confirm card). At most 5 fields are visible, the rest behind "Gelişmiş"; native inputs with 16 px text on touch;
 * the options of room / period / reason fields come from the pages' own endpoints (`options_source`). Submitting
 * asks the action's card again (no model call): an R1 write's button names the effect ("Rezerve et") and leads to
 * the confirm card; an R2 write's reads "Önizle".
 */
import { useQuery } from "@tanstack/react-query";
import { useId, useMemo, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { crbs } from "@/lib/api/crbs";
import type { ActionArgs } from "@/lib/api/helper";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import type { CardEntry } from "../helper-store";
import type { ConfirmCard, FormCard, FormField } from "../schema.gen";
import { pickText, useCardHost } from "./context";
import { HelperCardFrame } from "./frame";

export const VISIBLE_FIELDS = 5;

type Value = string | number | boolean | null;

const REASONS: [string, MessageKey][] = [
  ["room_unavailable", "approvals.reasons.room_unavailable"],
  ["capacity", "approvals.reasons.capacity"],
  ["policy", "approvals.reasons.policy"],
  ["other", "approvals.reasons.other"],
];

/** Integer arguments of the registry (sent as numbers, the server's strict schema wants them so). */
const NUMERIC = new Set(["period_id", "booking_id", "request_id", "headcount", "days"]);

let localSeq = 0;

/** "Değiştir" on a create_booking confirm: the same fields as the server's form, prefilled from `confirm.args`. */
export function formFromConfirm(card: ConfirmCard): FormCard | null {
  if (card.action !== "create_booking") return null;
  const a = card.args ?? {};
  const txt = (tr: string, en: string) => ({ tr, en });
  localSeq += 1;
  return {
    v: 1,
    type: "form",
    id: `${Date.now().toString(16)}${localSeq.toString(16)}`.slice(0, 32).padEnd(8, "0"),
    action: "create_booking",
    title: card.title ?? txt("Rezervasyon", "Booking"),
    risk: "R1",
    missing: [],
    fields: [
      { name: "room", label: txt("Salon", "Room"), kind: "room", required: true, value: a.room ?? null, options_source: "rooms", options: [] },
      { name: "date", label: txt("Tarih", "Date"), kind: "date", required: true, value: a.date ?? null, options: [] },
      { name: "period_id", label: txt("Ders saati", "Period"), kind: "period", required: true, value: a.period_id ?? null, options_source: "periods", options: [] },
      { name: "notes", label: txt("Amaç", "Purpose"), kind: "text", required: false, value: a.notes ?? null, max_length: 255, options: [] },
    ],
  };
}

function initial(card: FormCard): Record<string, Value> {
  return Object.fromEntries(card.fields.map((f) => [f.name, f.value ?? (f.kind === "toggle" ? false : "")]));
}

function useRoomOptions(enabled: boolean) {
  return useQuery({ queryKey: ["crbs", "booking-rooms"], queryFn: () => crbs.bookings.rooms(), enabled, retry: false, staleTime: 60_000 });
}

function usePeriodOptions(roomId: number, date: string, enabled: boolean) {
  return useQuery({
    queryKey: ["helper", "periods", roomId, date],
    queryFn: () => crbs.bookings.grid({ display: "room", room_id: roomId, date }),
    enabled: enabled && roomId > 0 && /^\d{4}-\d{2}-\d{2}$/.test(date),
    retry: false,
    staleTime: 60_000,
  });
}

function FieldInput({ field, value, onChange, values, invalid }: { field: FormField; value: Value; onChange: (v: Value) => void; values: Record<string, Value>; invalid: boolean }) {
  const { t } = useI18n();
  const host = useCardHost();
  const id = useId();
  const label = pickText(field.label, host.locale);
  const rooms = useRoomOptions(field.options_source === "rooms");
  const periods = usePeriodOptions(Number(values.room) || 0, String(values.date ?? ""), field.options_source === "periods");
  const common = { id, "aria-invalid": invalid || undefined, required: field.required, "data-testid": `helper-field-${field.name}` };
  let control;
  if (field.kind === "toggle") {
    control = <Switch id={id} checked={value === true} onCheckedChange={(v) => onChange(v)} aria-label={label} data-testid={`helper-field-${field.name}`} />;
  } else if (field.kind === "textarea") {
    control = <Textarea {...common} value={String(value ?? "")} maxLength={field.max_length ?? undefined} onChange={(e) => onChange(e.target.value)} />;
  } else if (field.kind === "room" || field.kind === "period" || field.kind === "select" || field.options.length) {
    const opts: { value: string; label: string }[] = field.options.length
      ? field.options.map((o) => ({ value: String(o.value), label: pickText(o.label, host.locale) }))
      : field.options_source === "rooms"
        ? (rooms.data ?? []).map((r) => ({ value: String(r.id), label: [r.name || r.code, r.capacity ? t("glass.palette.seats", { n: r.capacity }) : null].filter(Boolean).join(" · ") }))
        : field.options_source === "periods"
          ? (periods.data?.periods ?? []).map((p) => ({ value: String(p.id), label: `${p.name} · ${p.time_start.slice(0, 5)}–${p.time_end.slice(0, 5)}` }))
          : field.options_source === "reasons"
            ? REASONS.map(([v, k]) => ({ value: v, label: t(k) }))
            : [];
    const current = value === null || value === undefined ? "" : String(value);
    // an unresolved value the server echoed ("A 204") stays visible until the person picks a real option
    if (current && !opts.some((o) => o.value === current)) opts.unshift({ value: current, label: current });
    control = (
      <NativeSelect {...common} value={current} onChange={(e) => onChange(e.target.value)}>
        <option value="">{t("helper.form.pick")}</option>
        {opts.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </NativeSelect>
    );
  } else {
    const type = field.kind === "number" ? "number" : field.kind === "date" ? "date" : field.kind === "time" ? "time" : "text";
    control = <Input {...common} type={type} value={String(value ?? "")} maxLength={field.max_length ?? undefined} onChange={(e) => onChange(field.kind === "number" ? (e.target.value === "" ? "" : Number(e.target.value)) : e.target.value)} />;
  }
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <Label htmlFor={id}>
        {label}
        {field.required ? null : <span className="font-normal text-label-3"> · {t("helper.form.optional")}</span>}
      </Label>
      {control}
    </div>
  );
}

export function FormView({ card, entry }: { card: FormCard; entry: CardEntry }) {
  const { t } = useI18n();
  const host = useCardHost();
  const [values, setValues] = useState<Record<string, Value>>(() => initial(card));
  const [advanced, setAdvanced] = useState(false);
  const [tried, setTried] = useState(false);
  const open = entry.phase === "pending";
  const visible = card.fields.slice(0, VISIBLE_FIELDS);
  const more = card.fields.slice(VISIBLE_FIELDS);
  const missing = useMemo(() => card.fields.filter((f) => f.required && (values[f.name] === "" || values[f.name] === null || values[f.name] === undefined)).map((f) => f.name), [card.fields, values]);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setTried(true);
    if (missing.length || !open) return;
    const args: ActionArgs = {};
    for (const f of card.fields) {
      const v = values[f.name];
      if (v === "" || v === null || v === undefined) continue;
      args[f.name] = NUMERIC.has(f.name) || f.kind === "number" || f.kind === "period" ? Number(v) : v;
    }
    void host.runner.runAction(card.action, args, { hints: entry.hints, replaces: entry.key });
  };
  const verb = host.actionVerb(card.action);
  const primary = card.risk === "R2" ? t("helper.form.preview") : verb ?? t("helper.form.continue");
  const field = (f: FormField) => <FieldInput key={f.name} field={f} value={values[f.name] ?? ""} values={values} invalid={tried && missing.includes(f.name)} onChange={(v) => setValues((p) => ({ ...p, [f.name]: v }))} />;
  return (
    <HelperCardFrame testId={`helper-card-form-${card.action}`} title={card.title ? pickText(card.title, host.locale) : verb ?? undefined}>
      {card.message ? <p className="type-callout text-label-2">{pickText(card.message, host.locale)}</p> : null}
      <form onSubmit={submit} className="flex flex-col gap-3" noValidate>
        <fieldset disabled={!open} className="flex flex-col gap-3">
          {visible.map(field)}
          {more.length ? (
            <>
              <Button type="button" variant="ghost" size="sm" aria-expanded={advanced} onClick={() => setAdvanced((v) => !v)} className="-ml-2 self-start">
                {t("helper.form.advanced")}
              </Button>
              {advanced ? more.map(field) : null}
            </>
          ) : null}
        </fieldset>
        {tried && missing.length ? (
          <p role="alert" className="type-footnote text-status-infeasible-fg">
            {t("helper.form.missing")}
          </p>
        ) : null}
        {open ? (
          <div className="flex flex-wrap gap-2 max-sm:flex-col max-sm:items-stretch">
            <Button type="submit" size="md" className="max-sm:h-12" data-testid="helper-form-submit">
              {primary}
            </Button>
            <Button type="button" variant="ghost" size="md" onClick={() => host.runner.cancel(entry)} data-testid="helper-form-cancel">
              {t("helper.card.cancel")}
            </Button>
          </div>
        ) : null}
      </form>
    </HelperCardFrame>
  );
}
