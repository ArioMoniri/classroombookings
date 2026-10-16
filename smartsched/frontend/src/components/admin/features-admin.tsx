"use client";
/**
 * Admin → Rooms → Features (P10, docs/product/wave1-api.md §2; `rooms.features` or `setup.rooms`). The
 * typed feature catalogue (yes/no, number with a unit, option, options, text) with filter / public flags,
 * category, icon and the solver tag; the rooms × features values grid (edit in place, save the changed
 * rooms); the bulk CSV (download the template with the current values, upload, check, apply); "Adopt room
 * tags" (PC, TIP … become yes/no features) and the optional starter catalogue.
 *
 * A solver tag feeds the timetable solver (`rooms.tags`): changing or removing one that rooms carry answers
 * 409 `solver_tag_impact`; the admin sees "removes PC from 5 rooms; 37 requests need PC" and confirms.
 */
import { useQueryClient } from "@tanstack/react-query";
import { FileDown, FileUp, ListPlus, Pencil, Plus, Tags, Trash2 } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BusyLabel } from "@/components/ui/busy-label";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useAdminRooms, type AdminRoom } from "@/lib/api/crbs";
import { errorText, FEATURE_CATEGORIES, FEATURE_KINDS, FEATURE_KEYS, Impact, useFeatures, wave1, wave1Error, type BulkReport, type Feature, type FeatureIn, type FeatureKind } from "@/lib/api/wave1";
import { useI18n } from "@/lib/i18n/provider";
import type { MessageKey } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { Alert, ConfirmDialog, Field, Loading, SelectField } from "./kit";
import { EntityIcon, IconPicker } from "./icons";
import { changedCells, parseOptions, readValue, templateCsv, valueLabel, type FeatureValue } from "./features-model";

const KIND_KEY: Record<FeatureKind, MessageKey> = {
  BOOLEAN: "wave1.features.kind.BOOLEAN",
  NUMBER: "wave1.features.kind.NUMBER",
  SELECT: "wave1.features.kind.SELECT",
  MULTISELECT: "wave1.features.kind.MULTISELECT",
  TEXT: "wave1.features.kind.TEXT",
};
const CATEGORY_KEY: Record<string, MessageKey> = {
  av: "wave1.features.cat.av",
  seating: "wave1.features.cat.seating",
  accessibility: "wave1.features.cat.accessibility",
  lab: "wave1.features.cat.lab",
  other: "wave1.features.cat.other",
};

function useInvalidate() {
  const qc = useQueryClient();
  return () => Promise.all(FEATURE_KEYS.map((k) => qc.invalidateQueries({ queryKey: k })));
}

export function FeaturesTab() {
  const { t, locale } = useI18n();
  const features = useFeatures();
  const rooms = useAdminRooms();
  const invalidate = useInvalidate();
  const [editing, setEditing] = useState<Feature | "new" | null>(null);
  const [deleting, setDeleting] = useState<Feature | null>(null);
  const [bulk, setBulk] = useState(false);
  const [busy, setBusy] = useState<"adopt" | "template" | null>(null);
  const list = features.data ?? [];

  const starter = async (which: "adopt" | "template") => {
    setBusy(which);
    try {
      const out = which === "adopt" ? await wave1.features.adoptTags() : await wave1.features.template();
      await invalidate();
      toast.success(out.length ? t(which === "adopt" ? "wave1.features.adopted" : "wave1.features.templated", { n: out.length, names: out.map((f) => f.name).join(", ") }) : t("wave1.features.nothingNew"));
    } catch (e) {
      toast.error(errorText(wave1Error(e), locale));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-6" data-testid="features-tab">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <p className="max-w-prose type-callout text-label-2">{t("wave1.features.lead")}</p>
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={() => void starter("adopt")} disabled={!!busy} data-testid="features-adopt" aria-busy={busy === "adopt" || undefined}>
            <BusyLabel busy={busy === "adopt"} label={t("busy.working")} icon={<Tags aria-hidden />}>
            {t("wave1.features.adopt")}</BusyLabel>
          </Button>
          <Button variant="outline" onClick={() => void starter("template")} disabled={!!busy} data-testid="features-starter" aria-busy={busy === "template" || undefined}>
            <BusyLabel busy={busy === "template"} label={t("busy.working")} icon={<ListPlus aria-hidden />}>
            {t("wave1.features.starter")}</BusyLabel>
          </Button>
          <Button variant="outline" onClick={() => setBulk(true)} data-testid="features-bulk">
            <FileUp aria-hidden />
            {t("wave1.features.bulk")}
          </Button>
          <Button onClick={() => setEditing("new")} data-testid="feature-new">
            <Plus aria-hidden />
            {t("wave1.features.new")}
          </Button>
        </div>
      </div>

      <Card className="py-0">
        {features.isLoading ? (
          <Loading className="px-4" />
        ) : features.isError ? (
          <Alert tone="error" className="m-4">
            {errorText(wave1Error(features.error), locale)}
          </Alert>
        ) : list.length === 0 ? (
          <p className="px-4 py-5 type-callout text-label-2">{t("wave1.features.none")}</p>
        ) : (
          <Table data-testid="features-table">
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">{t("crbs.common.name")}</TableHead>
                <TableHead>{t("crbs.fields.type")}</TableHead>
                <TableHead className="hidden md:table-cell">{t("wave1.features.solverTag")}</TableHead>
                <TableHead className="hidden lg:table-cell">{t("wave1.features.flags")}</TableHead>
                <TableHead className="w-24 pr-4">
                  <span className="sr-only">{t("crbs.common.actions")}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.map((f) => (
                <TableRow key={f.id} data-testid={`feature-${f.id}`}>
                  <TableCell className="pl-4">
                    <span className="flex items-center gap-2 font-medium text-label-1">
                      {f.icon ? <EntityIcon name={f.icon} className="size-4 text-label-2" /> : null}
                      {f.name}
                    </span>
                    {f.options.length ? <span className="block max-w-80 truncate type-footnote text-label-3">{f.options.map((o) => o.value).join(", ")}</span> : null}
                  </TableCell>
                  <TableCell className="text-label-2">
                    {t(KIND_KEY[f.kind])}
                    {f.unit ? ` (${f.unit})` : ""}
                  </TableCell>
                  <TableCell className="hidden md:table-cell">{f.solver_tag ? <Badge tone="locked">{f.solver_tag}</Badge> : <span className="text-label-3">—</span>}</TableCell>
                  <TableCell className="hidden type-footnote text-label-2 lg:table-cell">
                    {[f.filterable ? t("wave1.features.filterable") : null, f.public ? t("wave1.features.public") : t("wave1.features.private"), f.category && CATEGORY_KEY[f.category] ? t(CATEGORY_KEY[f.category]!) : null].filter(Boolean).join(" · ")}
                  </TableCell>
                  <TableCell className="pr-4 text-right whitespace-nowrap">
                    <Button variant="ghost" size="icon-sm" className="pointer-coarse:size-11" aria-label={t("crbs.rooms.editNamed", { name: f.name })} onClick={() => setEditing(f)}>
                      <Pencil />
                    </Button>
                    <Button variant="ghost" size="icon-sm" className="pointer-coarse:size-11" aria-label={t("crbs.rooms.deleteNamed", { name: f.name })} onClick={() => setDeleting(f)}>
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Card>

      {list.length && rooms.data?.length ? <ValuesGrid features={list} rooms={rooms.data} /> : rooms.isLoading ? <Loading /> : null}

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="sm:max-w-lg">{editing !== null ? <FeatureForm key={editing === "new" ? "new" : editing.id} feature={editing === "new" ? null : editing} onClose={() => setEditing(null)} /> : null}</DialogContent>
      </Dialog>
      <DeleteFeature feature={deleting} onClose={() => setDeleting(null)} />
      <Dialog open={bulk} onOpenChange={setBulk}>
        <DialogContent className="sm:max-w-2xl">{bulk ? <BulkDialog features={list} rooms={rooms.data ?? []} onClose={() => setBulk(false)} /> : null}</DialogContent>
      </Dialog>
    </div>
  );
}

/* ----------------------------------------------------------------------------- impact confirm */

function impactText(i: Impact, locale: string, t: ReturnType<typeof useI18n>["t"]): string {
  const own = locale === "tr" ? i.message_tr : i.message;
  return own || t("wave1.features.impactBody", { tag: i.tag ?? "", rooms: i.room_count, requests: i.requests_needing });
}

/** `detail.impact` of a 409 `solver_tag_impact`, or null for any other error. */
function impactOf(e: unknown): Impact | null {
  const err = wave1Error(e);
  if (err.status !== 409 || err.code !== "solver_tag_impact") return null;
  const parsed = Impact.safeParse(err.data.impact ?? err.data);
  return parsed.success ? parsed.data : null;
}

function ImpactAlert({ impact }: { impact: Impact }) {
  const { t, locale } = useI18n();
  return (
    <Alert tone="warning" title={t("wave1.features.impactTitle", { tag: impact.tag ?? "" })} testId="feature-impact">
      <span className="block">{impactText(impact, locale, t)}</span>
      {impact.rooms.length ? <span className="mt-1 block type-footnote">{impact.rooms.slice(0, 12).join(", ")}{impact.rooms.length > 12 ? ` +${impact.rooms.length - 12}` : ""}</span> : null}
    </Alert>
  );
}

/* --------------------------------------------------------------------------------- feature form */

function FeatureForm({ feature, onClose }: { feature: Feature | null; onClose: () => void }) {
  const { t, locale } = useI18n();
  const invalidate = useInvalidate();
  const [f, setF] = useState({
    name: feature?.name ?? "",
    type: (feature?.kind ?? "BOOLEAN") as FeatureKind,
    options: (feature?.options ?? []).map((o) => o.value).join("\n"),
    unit: feature?.unit ?? "",
    solver_tag: feature?.solver_tag ?? "",
    category: feature?.category ?? "",
    icon: feature?.icon ?? null,
    filterable: feature?.filterable ?? true,
    public: feature?.public ?? true,
  });
  const [error, setError] = useState<string | null>(null);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [saving, setSaving] = useState(false);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((p) => ({ ...p, [k]: v }));
  const withOptions = f.type === "SELECT" || f.type === "MULTISELECT";
  const body = (): FeatureIn => ({
    name: f.name.trim(),
    type: f.type,
    options: withOptions ? parseOptions(f.options) : [],
    filterable: f.filterable,
    public: f.public,
    icon: f.icon,
    unit: f.type === "NUMBER" ? f.unit.trim() || null : null,
    solver_tag: f.solver_tag.trim() ? f.solver_tag.trim().toUpperCase() : null,
    category: (f.category || null) as FeatureIn["category"],
  });
  const save = async (confirm: boolean) => {
    setError(null);
    if (!f.name.trim()) return setError(t("wave1.features.needName"));
    if (withOptions && parseOptions(f.options).length === 0) return setError(t("wave1.features.needOptions"));
    setSaving(true);
    try {
      if (feature) await wave1.features.update(feature.id, body(), confirm);
      else await wave1.features.create(body());
      await invalidate();
      toast.success(t("crbs.common.saved"));
      onClose();
    } catch (e) {
      const i = impactOf(e);
      if (i) setImpact(i);
      else setError(errorText(wave1Error(e), locale));
    } finally {
      setSaving(false);
    }
  };
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        void save(impact !== null);
      }}
    >
      <DialogHeader>
        <DialogTitle>{feature ? t("wave1.features.editTitle", { name: feature.name }) : t("wave1.features.new")}</DialogTitle>
        <DialogDescription>{t("wave1.features.formHint")}</DialogDescription>
      </DialogHeader>
      <div className="flex max-h-[min(70dvh,620px)] flex-col gap-3 overflow-y-auto pr-1">
        <Field label={t("crbs.common.name")} htmlFor="feat-name">
          <Input id="feat-name" maxLength={64} required value={f.name} onChange={(e) => set("name", e.target.value)} data-testid="feature-name" />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("crbs.fields.type")} htmlFor="feat-type">
            <SelectField id="feat-type" value={f.type} onChange={(e) => set("type", e.target.value as FeatureKind)} data-testid="feature-type">
              {FEATURE_KINDS.map((k) => (
                <option key={k} value={k}>
                  {t(KIND_KEY[k])}
                </option>
              ))}
            </SelectField>
          </Field>
          <Field label={t("wave1.features.category")} htmlFor="feat-cat">
            <SelectField id="feat-cat" value={f.category} onChange={(e) => set("category", e.target.value)}>
              <option value="">{t("crbs.common.none")}</option>
              {FEATURE_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {t(CATEGORY_KEY[c]!)}
                </option>
              ))}
            </SelectField>
          </Field>
        </div>
        {withOptions ? (
          <Field label={t("crbs.fields.options")} htmlFor="feat-options" hint={t("wave1.features.optionsHint")}>
            <Textarea id="feat-options" rows={4} value={f.options} onChange={(e) => set("options", e.target.value)} data-testid="feature-options" />
          </Field>
        ) : null}
        {f.type === "NUMBER" ? (
          <Field label={t("wave1.features.unit")} htmlFor="feat-unit" hint={t("wave1.features.unitHint")}>
            <Input id="feat-unit" maxLength={16} value={f.unit} onChange={(e) => set("unit", e.target.value)} />
          </Field>
        ) : null}
        <Field label={t("wave1.features.solverTag")} htmlFor="feat-tag" hint={t("wave1.features.solverTagHint")}>
          <Input id="feat-tag" maxLength={16} value={f.solver_tag} onChange={(e) => (set("solver_tag", e.target.value), setImpact(null))} data-testid="feature-solver-tag" />
        </Field>
        {f.solver_tag.trim() || feature?.solver_tag ? (
          <p className="type-footnote text-status-warning-fg" role="note">
            {t("wave1.features.solverWarning")}
          </p>
        ) : null}
        <Field label={t("crbs.icons.label")} htmlFor="feat-icon">
          <IconPicker id="feat-icon" value={f.icon} onChange={(v) => set("icon", v)} />
        </Field>
        <label className="flex items-center justify-between gap-3 type-callout text-label-1">
          <span>
            {t("wave1.features.filterable")}
            <span className="block type-footnote text-label-3">{t("wave1.features.filterableHint")}</span>
          </span>
          <Switch checked={f.filterable} onCheckedChange={(v) => set("filterable", v)} aria-label={t("wave1.features.filterable")} />
        </label>
        <label className="flex items-center justify-between gap-3 type-callout text-label-1">
          <span>
            {t("wave1.features.public")}
            <span className="block type-footnote text-label-3">{t("wave1.features.publicHint")}</span>
          </span>
          <Switch checked={f.public} onCheckedChange={(v) => set("public", v)} aria-label={t("wave1.features.public")} />
        </label>
        {impact ? <ImpactAlert impact={impact} /> : null}
        {error ? <Alert tone="error">{error}</Alert> : null}
      </div>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          {t("crbs.common.cancel")}
        </Button>
        <Button type="submit" disabled={saving} variant={impact ? "destructive" : "default"} data-testid="feature-save" aria-busy={saving || undefined}>
          <BusyLabel busy={saving} label={t("busy.saving")}>
          {impact ? t("wave1.features.saveAnyway") : t("crbs.common.save")}</BusyLabel>
        </Button>
      </DialogFooter>
    </form>
  );
}

function DeleteFeature({ feature, onClose }: { feature: Feature | null; onClose: () => void }) {
  const { t, locale } = useI18n();
  const invalidate = useInvalidate();
  const [impact, setImpact] = useState<Impact | null>(null);
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState<number | null>(null);
  if ((feature?.id ?? null) !== last) {
    setLast(feature?.id ?? null);
    setImpact(null);
  }
  const run = async () => {
    if (!feature) return;
    setBusy(true);
    try {
      await wave1.features.remove(feature.id, impact !== null);
      await invalidate();
      toast.success(t("wave1.features.deleted", { name: feature.name }));
      onClose();
      // the deleted row's buttons are gone: focus "New feature" instead of <body> (motion audit T4)
      window.setTimeout(() => document.querySelector<HTMLElement>('[data-testid="feature-new"]')?.focus(), 320);
    } catch (e) {
      const i = impactOf(e);
      if (i) setImpact(i);
      else toast.error(errorText(wave1Error(e), locale));
    } finally {
      setBusy(false);
    }
  };
  return (
    <ConfirmDialog
      open={!!feature}
      onOpenChange={(o) => !o && onClose()}
      title={t("wave1.features.deleteTitle", { name: feature?.name ?? "" })}
      description={t("wave1.features.deleteBody")}
      confirmLabel={impact ? t("wave1.features.deleteAnyway") : t("crbs.common.delete")}
      destructive
      busy={busy}
      onConfirm={() => void run()}
    >
      {impact ? <ImpactAlert impact={impact} /> : null}
    </ConfirmDialog>
  );
}

/* --------------------------------------------------------------------------------- values grid */

function ValuesGrid({ features, rooms }: { features: Feature[]; rooms: AdminRoom[] }) {
  const { t, locale } = useI18n();
  const invalidate = useInvalidate();
  const [q, setQ] = useState("");
  const [draft, setDraft] = useState<Record<number, Record<string, FeatureValue>>>({});
  const [errors, setErrors] = useState<Record<number, string>>({});
  const [saving, setSaving] = useState(false);
  const fold = (s: string) => s.toLocaleLowerCase("tr-TR");
  const shown = useMemo(() => {
    const needle = fold(q.trim());
    return rooms.filter((r) => !needle || fold(`${r.code} ${r.display_name} ${r.room_group ?? ""}`).includes(needle));
  }, [q, rooms]);
  const changed = useMemo(() => {
    const out: { room: AdminRoom; cells: Record<string, FeatureValue> }[] = [];
    for (const r of rooms) {
      const d = draft[r.id];
      if (!d) continue;
      const cells = changedCells(features, r.fields, d);
      if (Object.keys(cells).length) out.push({ room: r, cells });
    }
    return out;
  }, [draft, features, rooms]);
  const value = (r: AdminRoom, f: Feature): FeatureValue => {
    const d = draft[r.id];
    return d && String(f.id) in d ? (d[String(f.id)] ?? null) : readValue(f, r.fields[String(f.id)]);
  };
  const setCell = (r: AdminRoom, f: Feature, v: FeatureValue) => setDraft((p) => ({ ...p, [r.id]: { ...(p[r.id] ?? {}), [String(f.id)]: v } }));

  const saveAll = async () => {
    setSaving(true);
    const errs: Record<number, string> = {};
    let ok = 0;
    for (const { room, cells } of changed) {
      try {
        await wave1.features.putRoomValues(room.id, cells);
        ok++;
      } catch (e) {
        const err = wave1Error(e);
        const list = Array.isArray(err.data.errors) ? (err.data.errors as unknown[]).map((x) => (typeof x === "string" ? x : x && typeof x === "object" && "message" in x ? String((x as { message: unknown }).message) : JSON.stringify(x))) : [];
        errs[room.id] = list.length ? list.join("; ") : errorText(err, locale);
      }
    }
    await invalidate();
    setErrors(errs);
    setDraft((p) => Object.fromEntries(Object.entries(p).filter(([id]) => errs[Number(id)])));
    setSaving(false);
    if (ok) toast.success(t("wave1.features.valuesSaved", { n: ok }));
  };

  return (
    <section aria-labelledby="feature-values" className="flex flex-col gap-3" data-testid="feature-values">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h3 id="feature-values" className="type-title-3 text-label-1">
            {t("wave1.features.values")}
          </h3>
          <p className="type-footnote text-label-2">{t("wave1.features.valuesLead")}</p>
        </div>
        <div className="flex items-center gap-2">
          <Input type="search" aria-label={t("wave1.features.filterRooms")} placeholder={t("wave1.features.filterRooms")} value={q} onChange={(e) => setQ(e.target.value)} className="w-48" />
          <Button onClick={() => void saveAll()} disabled={!changed.length || saving} data-testid="feature-values-save" aria-busy={saving || undefined}>
            <BusyLabel busy={saving} label={t("busy.saving")}>
            {t("wave1.features.saveRooms", { n: changed.length })}</BusyLabel>
          </Button>
        </div>
      </div>
      <Card variant="plain" className="overflow-hidden py-0">
        <div className="max-h-[min(70dvh,720px)] overflow-auto">
          <table className="w-max min-w-full border-separate border-spacing-0 type-callout">
            <thead className="sticky top-0 z-10 bg-(--mat-thick-solid)">
              <tr>
                <th scope="col" className="sticky left-0 z-20 bg-(--mat-thick-solid) px-3 py-2 text-left font-semibold text-label-2 border-r border-b border-hairline">
                  {t("wave1.features.room")}
                </th>
                {features.map((f) => (
                  <th key={f.id} scope="col" className="max-w-40 px-3 py-2 text-left font-semibold whitespace-nowrap text-label-2 edge-hairline-b">
                    {f.name}
                    {f.unit ? <span className="ml-1 font-normal text-label-3">({f.unit})</span> : null}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => {
                const dirty = changed.some((c) => c.room.id === r.id);
                return (
                  <tr key={r.id} data-testid={`values-row-${r.code}`} data-dirty={dirty || undefined} className={cn(dirty && "bg-tint-soft/50")}>
                    <th scope="row" className="sticky left-0 bg-(--mat-thick-solid) px-3 py-1.5 text-left font-medium whitespace-nowrap text-label-1 border-r border-b border-hairline">
                      {r.display_name}
                      <span className="ml-1.5 font-normal text-label-3">{r.code}</span>
                      {errors[r.id] ? <span className="block max-w-56 truncate type-caption text-status-infeasible-fg" title={errors[r.id]}>{errors[r.id]}</span> : null}
                    </th>
                    {features.map((f) => (
                      <td key={f.id} className="px-2 py-1 edge-hairline-b">
                        <CellInput feature={f} value={value(r, f)} onChange={(v) => setCell(r, f, v)} label={`${r.display_name}, ${f.name}`} />
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </section>
  );
}

function CellInput({ feature: f, value, onChange, label }: { feature: Feature; value: FeatureValue; onChange: (v: FeatureValue) => void; label: string }) {
  const { t } = useI18n();
  if (f.kind === "BOOLEAN") return <Checkbox checked={value === true} onCheckedChange={(v) => onChange(v === true)} aria-label={label} />;
  if (f.kind === "NUMBER")
    return (
      <Input
        type="number"
        min={0}
        step="any"
        inputMode="decimal"
        aria-label={label}
        className="h-7 w-20"
        value={typeof value === "number" ? value : ""}
        onChange={(e) => onChange(e.target.value === "" ? null : Math.max(0, Number(e.target.value)))}
      />
    );
  if (f.kind === "SELECT")
    return (
      <SelectField aria-label={label} className="h-7 min-w-28" value={typeof value === "number" ? String(value) : ""} onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}>
        <option value="">—</option>
        {f.options.map((o) => (
          <option key={o.id} value={o.id}>
            {o.value}
          </option>
        ))}
      </SelectField>
    );
  if (f.kind === "MULTISELECT") {
    const ids = Array.isArray(value) ? value : [];
    return (
      <details className="relative">
        <summary className="max-w-40 cursor-pointer list-none truncate rounded-md px-1.5 py-1 text-label-1 outline-hidden hover:bg-fill-2 focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus)" aria-label={label}>
          {valueLabel(f, ids, { yes: "", no: "" }) || <span className="text-label-3">{t("wave1.features.pick")}</span>}
        </summary>
        <div className="absolute z-30 mt-1 flex min-w-40 flex-col gap-1 rounded-xl bg-(--mat-thick-solid) p-2 shadow-lg">
          {f.options.map((o) => (
            <label key={o.id} className="flex items-center gap-2 whitespace-nowrap">
              <Checkbox checked={ids.includes(o.id)} onCheckedChange={(v) => onChange(v === true ? [...ids, o.id].sort((a, b) => a - b) : ids.filter((x) => x !== o.id))} />
              {o.value}
            </label>
          ))}
        </div>
      </details>
    );
  }
  return <Input aria-label={label} maxLength={255} className="h-7 w-36" value={typeof value === "string" ? value : ""} onChange={(e) => onChange(e.target.value)} />;
}

/* ------------------------------------------------------------------------------------ bulk CSV */

function BulkDialog({ features, rooms, onClose }: { features: Feature[]; rooms: AdminRoom[]; onClose: () => void }) {
  const { t, locale } = useI18n();
  const invalidate = useInvalidate();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<BulkReport | null>(null);
  const [skip, setSkip] = useState(false);
  const [busy, setBusy] = useState<"check" | "apply" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const download = () => {
    const csv = templateCsv(rooms, features, locale === "tr" ? { yes: "evet", no: "hayır" } : { yes: "yes", no: "no" });
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "oda-ozellikleri.csv";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const run = async (dryRun: boolean) => {
    if (!file) return;
    setBusy(dryRun ? "check" : "apply");
    setError(null);
    try {
      const out = await wave1.features.bulk(file, dryRun, skip);
      setReport(out);
      if (!dryRun) {
        await invalidate();
        toast.success(t("wave1.features.bulkApplied", { n: out.applied }));
        onClose();
      }
    } catch (e) {
      const err = wave1Error(e);
      setError(errorText(err, locale));
    } finally {
      setBusy(null);
    }
  };
  const problems = report?.report.filter((r) => r.status !== "ok") ?? [];
  return (
    <div className="flex flex-col gap-4" data-testid="features-bulk-dialog">
      <DialogHeader>
        <DialogTitle>{t("wave1.features.bulk")}</DialogTitle>
        <DialogDescription>{t("wave1.features.bulkLead")}</DialogDescription>
      </DialogHeader>
      <ol className="flex list-decimal flex-col gap-3 pl-5 type-callout text-label-1">
        <li>
          <span className="block">{t("wave1.features.bulkStep1")}</span>
          <Button variant="outline" size="sm" className="mt-1.5" onClick={download} data-testid="features-template">
            <FileDown aria-hidden />
            {t("wave1.features.template")}
          </Button>
        </li>
        <li>
          <span className="block">{t("wave1.features.bulkStep2")}</span>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            className="mt-1.5 block type-footnote file:mr-3 file:rounded-full file:border-0 file:bg-fill-2 file:px-3 file:py-1.5 file:text-label-1"
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              setReport(null);
              setError(null);
            }}
            data-testid="features-file"
            aria-label={t("wave1.features.bulkStep2")}
          />
        </li>
      </ol>
      {report ? (
        <div className="flex flex-col gap-2" data-testid="features-report">
          <Alert tone={report.errors ? "warning" : "success"} title={t("wave1.features.reportTitle", { rooms: report.rooms, cells: report.cells, errors: report.errors })}>
            {report.unknown_columns.length ? t("wave1.features.unknownColumns", { names: report.unknown_columns.join(", ") }) : report.errors ? t("wave1.features.reportErrors") : t("wave1.features.reportOk")}
          </Alert>
          {problems.length ? (
            <div className="max-h-56 overflow-auto rounded-xl bg-fill-3">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-3">{t("wave1.features.line")}</TableHead>
                    <TableHead>{t("wave1.features.room")}</TableHead>
                    <TableHead>{t("crbs.common.name")}</TableHead>
                    <TableHead className="pr-3">{t("wave1.features.problem")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {problems.slice(0, 200).map((p, i) => (
                    <TableRow key={i}>
                      <TableCell className="pl-3 tabular-nums">{p.line ?? ""}</TableCell>
                      <TableCell>{p.room ?? ""}</TableCell>
                      <TableCell>{p.field ?? ""}</TableCell>
                      <TableCell className="pr-3 text-status-infeasible-fg">{p.message ?? p.status}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : null}
          {report.errors ? (
            <label className="flex items-center gap-2 type-callout text-label-1">
              <Checkbox checked={skip} onCheckedChange={(v) => setSkip(v === true)} />
              {t("wave1.features.skipErrors")}
            </label>
          ) : null}
        </div>
      ) : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      <DialogFooter>
        <Button variant="ghost" onClick={onClose}>
          {t("crbs.common.cancel")}
        </Button>
        <Button variant="outline" disabled={!file || !!busy} onClick={() => void run(true)} data-testid="features-check" aria-busy={busy === "check" || undefined}>
          <BusyLabel busy={busy === "check"} label={t("busy.checking")}>
          {t("wave1.features.check")}</BusyLabel>
        </Button>
        <Button disabled={!file || !report || !!busy || (report.errors > 0 && !skip)} onClick={() => void run(false)} data-testid="features-apply" aria-busy={busy === "apply" || undefined}>
          <BusyLabel busy={busy === "apply"} label={t("busy.working")}>
          {t("wave1.features.apply")}</BusyLabel>
        </Button>
      </DialogFooter>
    </div>
  );
}
