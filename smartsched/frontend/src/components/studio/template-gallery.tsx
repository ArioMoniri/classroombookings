"use client";

import { ArrowLeft, Building2, Clock, DoorOpen, GraduationCap, Loader2, NotebookPen, Plus, type LucideIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api/endpoints";
import type { Preview, RuleTemplate } from "@/lib/api/studio-schemas";
import type { MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { HardnessControl } from "./hardness-control";
import { AffectedBadge } from "./rule-card";
import { defaultParams, missingRequired, plainSentence, readField, tokens, writeField, type Params } from "./rule-sentence";
import { SlotChip, SlotEditor } from "./slot-picker";
import { useStudio } from "./studio-context";
import { useRuleActions } from "./use-rule-actions";

const TOPICS = ["rooms", "times", "buildings", "programmes", "exams"] as const;
type Topic = (typeof TOPICS)[number];
const TOPIC_ICON: Record<Topic, LucideIcon> = { rooms: DoorOpen, times: Clock, buildings: Building2, programmes: GraduationCap, exams: NotebookPen };
const TOPIC_KEY: Record<Topic, MessageKey> = { rooms: "studio.topic.rooms", times: "studio.topic.times", buildings: "studio.topic.buildings", programmes: "studio.topic.programmes", exams: "studio.topic.exams" };

const FIELD_KEY: Record<string, MessageKey> = {
  applies_to: "studio.field.applies_to",
  building: "studio.field.building",
  buildings: "studio.field.buildings",
  days: "studio.field.days",
  latest: "studio.field.latest",
  earliest: "studio.field.earliest",
  tag: "studio.field.tag",
  rooms: "studio.field.rooms",
  room: "studio.field.room",
  course: "studio.field.course",
  courses: "studio.field.courses",
  from_date: "studio.field.from_date",
  periods: "studio.field.periods",
  weeks: "studio.field.weeks",
  unit: "studio.field.unit",
  n: "studio.field.n",
};

export interface BuilderPrefill {
  templateId?: string;
  eventIds?: number[];
}

/** (b) Pick a template: gallery (topic tabs + cards), then the builder (live sentence on top, fields below). */
export function TemplateGallery({ open, onOpenChange, prefill }: { open: boolean; onOpenChange: (v: boolean) => void; prefill?: BuilderPrefill | null }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-3xl" data-testid="template-gallery">
        {open ? <GalleryBody prefill={prefill} onDone={() => onOpenChange(false)} /> : null}
      </DialogContent>
    </Dialog>
  );
}

function GalleryBody({ prefill, onDone }: { prefill?: BuilderPrefill | null; onDone: () => void }) {
  const { t, locale } = useI18n();
  const { meta, kind } = useStudio();
  const [topic, setTopic] = useState<Topic>("rooms");
  const [chosen, setChosen] = useState<RuleTemplate | null>(() => (prefill?.templateId ? (meta?.templates.find((x) => x.id === prefill.templateId) ?? null) : null));

  const list = (meta?.templates ?? []).filter((x) => x.topic === topic).filter((x) => kind === "EXAM" || x.topic !== "exams");
  return (
    <>
        <DialogHeader>
          <DialogTitle>{chosen ? chosen.title[locale] : t("studio.add.template")}</DialogTitle>
          <DialogDescription>{chosen ? t("studio.builder.help") : t("studio.gallery.help")}</DialogDescription>
        </DialogHeader>
        {chosen ? (
          <Builder template={chosen} eventIds={prefill?.eventIds} onBack={() => setChosen(null)} onDone={onDone} />
        ) : (
          <div className="grid gap-4 md:grid-cols-[10rem_1fr]">
            <div role="tablist" aria-orientation="vertical" aria-label={t("studio.gallery.topics")} className="flex gap-1 overflow-x-auto md:flex-col">
              {TOPICS.filter((x) => kind === "EXAM" || x !== "exams").map((x) => {
                const Icon = TOPIC_ICON[x];
                return (
                  <button key={x} type="button" role="tab" aria-selected={topic === x} onClick={() => setTopic(x)} className={cn("flex shrink-0 items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm pointer-coarse:min-h-11", topic === x ? "bg-primary-tint font-medium text-primary" : "hover:bg-muted")}>
                    <Icon className="size-4" aria-hidden /> {t(TOPIC_KEY[x])}
                  </button>
                );
              })}
            </div>
            <ul className="grid gap-2 sm:grid-cols-2" role="tabpanel">
              {list.map((tpl) => {
                const Icon = TOPIC_ICON[(tpl.topic as Topic) ?? "rooms"] ?? DoorOpen;
                return (
                  <li key={tpl.id}>
                    <button type="button" onClick={() => setChosen(tpl)} className="flex h-full w-full flex-col items-start gap-1.5 rounded-lg border bg-card p-3 text-left hover:border-primary focus-visible:ring-3 focus-visible:ring-ring/50" data-testid={`template-${tpl.id}`}>
                      <span className="flex items-center gap-2 font-medium">
                        <Icon className="size-4 text-primary" aria-hidden /> {tpl.title[locale]}
                      </span>
                      <span className="text-xs text-muted-foreground">{tpl.sentence[locale].replace(/[[\]]/g, "").replace(/\{(\w+)\}/g, "…")}</span>
                      <span className="text-[11px] text-muted-foreground">{tpl.default_hardness === "hard" ? t("studio.rule.must") : t("studio.rule.try")}</span>
                    </button>
                  </li>
                );
              })}
              {list.length === 0 ? <li className="text-sm text-muted-foreground">{t("studio.gallery.empty")}</li> : null}
            </ul>
          </div>
        )}
    </>
  );
}

function Builder({ template, eventIds, onBack, onDone }: { template: RuleTemplate; eventIds?: number[]; onBack: () => void; onDone: () => void }) {
  const { t, locale } = useI18n();
  const { sentence, meta, termId, kind, advanced } = useStudio();
  const actions = useRuleActions();
  const [params, setParams] = useState<Params>(() => {
    const base = defaultParams(template);
    const applies = template.fields.find((f) => f.type === "applies_to" || f.type === "courses");
    if (eventIds?.length && applies) return writeField(applies, base, applies.type === "courses" ? eventIds : { mode: "classes", event_ids: eventIds }, sentence);
    return base;
  });
  const [hardness, setHardness] = useState<"hard" | "soft">(template.default_hardness);
  const [weight, setWeight] = useState(template.default_weight);
  const [previewed, setPreviewed] = useState<{ key: string; data: Preview | null } | null>(null);
  const [saving, setSaving] = useState(false);

  const toks = useMemo(() => tokens(template, params, sentence, { showEmptyOptional: true }), [template, params, sentence]);
  const missing = missingRequired(template, params, sentence);
  const paramsKey = JSON.stringify(params);
  const previewKey = `${paramsKey}|${hardness}`;
  const loading = previewed?.key !== previewKey;
  const preview = previewed?.data ?? null;

  useEffect(() => {
    const ctrl = new AbortController();
    const id = setTimeout(() => {
      api.studio
        .preview({ term_id: termId, kind: template.kind, params: JSON.parse(paramsKey) as Params, hardness, draft_kind: kind }, ctrl.signal)
        .then((p) => setPreviewed({ key: `${paramsKey}|${hardness}`, data: p }))
        .catch(() => !ctrl.signal.aborted && setPreviewed({ key: `${paramsKey}|${hardness}`, data: null }));
    }, 400);
    return () => {
      clearTimeout(id);
      ctrl.abort();
    };
  }, [paramsKey, hardness, template.kind, termId, kind]);

  const set = (name: string, v: unknown) => {
    const f = template.fields.find((x) => x.name === name);
    if (f) setParams((p) => writeField(f, p, v, sentence));
  };

  const add = async () => {
    setSaving(true);
    try {
      await actions.create({ kind: template.kind, params, hardness, weight, nl_text: plainSentence(tokens(template, params, sentence)), source: "ADMIN" });
      actions.undoToast(t("studio.builder.added"));
      onDone();
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="rule-builder">
      <div className="rounded-lg border bg-muted/40 p-3">
        <p className="text-xs font-medium text-muted-foreground">{t("studio.builder.preview")}</p>
        <p className="mt-1 text-base leading-relaxed">
          {toks.map((tok, i) => (tok.kind === "text" ? <span key={i}>{tok.text}</span> : <SlotChip key={`${tok.slot.name}-${i}`} slot={tok.slot} onChange={(v) => set(tok.slot.name, v)} />))}
        </p>
        <div className="mt-2">
          <AffectedBadge affected={{ count: preview?.affected_count ?? null, loading, percent: preview?.percent ?? null, targeted: preview?.targeted }} />
          {preview && preview.targeted && preview.affected_count === 0 ? <p className="mt-1 text-xs text-status-warning-fg">{t("studio.rule.matchesNone")}</p> : null}
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {template.fields
          .filter((f) => advanced || !f.advanced)
          .map((f) => (
            <div key={f.name} className="grid gap-1.5">
              <span className="text-sm font-medium">
                {t(FIELD_KEY[f.name] ?? "studio.slot.value")} {f.required ? <span className="text-xs font-normal text-muted-foreground">{t("studio.builder.required")}</span> : <span className="text-xs font-normal text-muted-foreground">{t("studio.builder.optional")}</span>}
              </span>
              <SlotEditor field={f} value={readField(f, params, sentence)} onChange={(v) => set(f.name, v)} />
            </div>
          ))}
      </div>
      {template.note ? <p className="rounded-md bg-muted/60 px-2.5 py-1.5 text-xs text-muted-foreground">{template.note[locale]}</p> : null}
      <HardnessControl hardness={hardness} weight={weight} allowed={template.allowed_hardness} onHardness={setHardness} onWeight={setWeight} scale={meta?.weight_scale} advanced={advanced} idPrefix="builder" />
      {missing.length ? <p className="text-xs text-status-warning-fg">{t("studio.builder.missing", { fields: missing.map((f) => t(FIELD_KEY[f.name] ?? "studio.slot.value")).join(", ") })}</p> : null}
      <div className="flex flex-wrap justify-between gap-2">
        <Button variant="ghost" onClick={onBack}>
          <ArrowLeft aria-hidden /> {t("studio.builder.back")}
        </Button>
        <Button onClick={() => void add()} disabled={missing.length > 0 || saving} data-testid="builder-add">
          {saving ? <Loader2 className="animate-spin" aria-hidden /> : <Plus aria-hidden />} {t("studio.builder.add")}
        </Button>
      </div>
    </div>
  );
}
