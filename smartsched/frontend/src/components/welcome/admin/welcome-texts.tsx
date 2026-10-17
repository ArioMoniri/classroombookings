"use client";
/**
 * Metinler (spec §4.6): one chip per audience; title and lead line up front, the card texts under "Kart metinleri".
 * Turkish and English side by side (stacked on phones, 16 px inputs). Text only: order, links and icons are fixed.
 * Placeholders `{ad}` / `{name}` and `{bölüm}` / `{department}` only; 80 / 200 characters. "Varsayılana dön" per
 * field (an empty override = the product text), "Önizle" renders the sheet in place, "Kaydet" asks whether to show the
 * guide again with "Güncellendi". A stale save answers 409 "Bu metni siz düzenlerken {ad} değiştirdi…".
 */
import { ChevronDown, RotateCcw } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog, Loading } from "@/components/admin/kit";
import { Button, IconButton } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { HttpError } from "@/lib/api/client";
import { AUDIENCES, type Audience, type WelcomeContent, useSaveWelcomeContent, useWelcomeContent } from "@/lib/api/welcome";
import { intlLocale, translate, type Locale, type MessageKey } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { CARDS, audienceKey, cardKey, sheetKey } from "../content";
import { badPlaceholders } from "../model";
import { useWelcomeStore } from "../welcome-store";

const LOCALES: Locale[] = ["tr", "en"];
type Drafts = Record<string, Record<string, string>>;

export interface TextField {
  field: string;
  max: 80 | 200;
  multiline: boolean;
  defaultKey: MessageKey;
  card?: string;
}

export function fieldsFor(audience: Audience): TextField[] {
  return [
    { field: "title", max: 80, multiline: false, defaultKey: sheetKey(audience, "title") },
    { field: "lead", max: 200, multiline: true, defaultKey: sheetKey(audience, "lead") },
    ...CARDS[audience].flatMap((c): TextField[] => [
      { field: `cards.${c.key}.title`, max: 80, multiline: false, defaultKey: cardKey(audience, c.key, "title"), card: c.key },
      { field: `cards.${c.key}.body`, max: 200, multiline: true, defaultKey: cardKey(audience, c.key, "body"), card: c.key },
    ]),
  ];
}

/** "Bu metni siz düzenlerken {ad} değiştirdi…" from a 409 (the backend's own sentence when it sends one). */
export function staleMessage(err: unknown, locale: Locale, t: (k: MessageKey, v?: Record<string, string>) => string): string | null {
  if (!(err instanceof HttpError) || err.status !== 409) return null;
  const d = (err.detail ?? {}) as Record<string, unknown>;
  const own = locale === "tr" ? d.message_tr : d.message_en;
  if (typeof own === "string" && own.trim()) return own;
  const who = [d.updated_by, d.by, d.name].find((x): x is string => typeof x === "string" && !!x.trim()) ?? t("welcome.admin.texts.staleSomeone");
  return t("welcome.admin.texts.stale", { ad: who, name: who });
}

function FieldEditor({ f, audience, drafts, setDraft }: { f: TextField; audience: Audience; drafts: Drafts; setDraft: (loc: Locale, field: string, v: string) => void }) {
  const { t } = useI18n();
  const base = useId();
  const label = f.card ? t(f.field.endsWith(".title") ? "welcome.admin.texts.cardTitle" : "welcome.admin.texts.cardBody", { card: translate("tr", cardKey(audience, f.card, "title")) }) : t(`welcome.admin.texts.field.${f.field}` as MessageKey);
  return (
    <fieldset className="flex flex-col gap-2 px-4 py-3 not-last:edge-hairline-b">
      <legend className="sr-only">{label}</legend>
      <p aria-hidden className="type-footnote font-semibold text-label-2">
        {label}
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        {LOCALES.map((loc) => {
          const id = `${base}-${loc}`;
          const value = drafts[loc]?.[f.field] ?? "";
          const bad = badPlaceholders(value).length > 0;
          const Field = f.multiline ? Textarea : Input;
          const errId = `${id}-err`;
          return (
            <div key={loc} className="flex flex-col gap-1">
              <div className="flex items-center justify-between gap-2">
                <label htmlFor={id} className="type-caption text-label-3">
                  {t(`welcome.admin.texts.${loc}`)}
                </label>
                <span className="type-caption text-label-3 tabular-nums">{t("welcome.admin.texts.count", { n: value.length, max: f.max })}</span>
              </div>
              <div className="flex items-start gap-1">
                <Field
                  id={id}
                  value={value}
                  maxLength={f.max}
                  placeholder={translate(loc, f.defaultKey)}
                  aria-invalid={bad || undefined}
                  aria-describedby={bad ? errId : undefined}
                  onChange={(e: React.ChangeEvent<HTMLInputElement & HTMLTextAreaElement>) => setDraft(loc, f.field, e.target.value)}
                  className={cn("min-w-0 flex-1", f.multiline && "min-h-20")}
                  data-testid={`welcome-text-${audience}-${f.field}-${loc}`}
                />
                <IconButton label={t("welcome.admin.texts.resetLabel", { field: label, locale: t(`welcome.admin.texts.${loc}`) })} disabled={!value} onClick={() => setDraft(loc, f.field, "")} data-testid={`welcome-reset-${audience}-${f.field}-${loc}`}>
                  <RotateCcw aria-hidden />
                </IconButton>
              </div>
              {bad ? (
                <p id={errId} className="type-caption text-status-infeasible-fg">
                  {t("welcome.admin.texts.badPlaceholder")}
                </p>
              ) : null}
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}

function Editor({ audience, content }: { audience: Audience; content: WelcomeContent }) {
  const { t, locale } = useI18n();
  const save = useSaveWelcomeContent(audience);
  const openSheet = useWelcomeStore((s) => s.openSheet);
  const [drafts, setDrafts] = useState<Drafts>(() => ({ tr: { ...(content.texts.tr ?? {}) }, en: { ...(content.texts.en ?? {}) } }));
  const [cardsOpen, setCardsOpen] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [reshow, setReshow] = useState(false);
  const [stale, setStale] = useState<string | null>(null);
  const cardsId = useId();
  const fields = fieldsFor(audience);
  const setDraft = (loc: Locale, field: string, v: string) => setDrafts((d) => ({ ...d, [loc]: { ...(d[loc] ?? {}), [field]: v } }));
  const invalid = LOCALES.some((loc) => Object.values(drafts[loc] ?? {}).some((v) => badPlaceholders(v).length > 0 || v.length > 200));
  const when = content.updatedAt ? new Intl.DateTimeFormat(intlLocale(locale), { dateStyle: "medium", timeStyle: "short", timeZone: "Europe/Istanbul" }).format(new Date(content.updatedAt)) : null;
  const doSave = () => {
    setStale(null);
    // only the fields the editor knows; "" = back to the product text
    const texts: Drafts = {};
    for (const loc of LOCALES) texts[loc] = Object.fromEntries(fields.map((f) => [f.field, (drafts[loc]?.[f.field] ?? "").trim()]));
    save.mutate(
      { version: content.version, texts, reshow },
      {
        onSuccess: () => {
          setConfirm(false);
          toast.success(t("welcome.admin.saved"));
        },
        onError: (err) => {
          setConfirm(false);
          const msg = staleMessage(err, locale, t);
          if (msg) setStale(msg);
          else toast.error(t("welcome.admin.saveFailed"));
        },
      },
    );
  };
  return (
    <div className="flex flex-col gap-4" data-testid={`welcome-editor-${audience}`}>
      <p className="type-footnote text-label-2">{t("welcome.admin.texts.placeholders")}</p>
      <Card variant="plain" className="py-0">
        {fields.filter((f) => !f.card).map((f) => (
          <FieldEditor key={f.field} f={f} audience={audience} drafts={drafts} setDraft={setDraft} />
        ))}
      </Card>
      <div>
        <Button variant="ghost" className="pointer-coarse:min-h-11" aria-expanded={cardsOpen} aria-controls={cardsId} onClick={() => setCardsOpen((v) => !v)} data-testid="welcome-cards-toggle">
          <ChevronDown aria-hidden className={cardsOpen ? "rotate-180" : ""} />
          {t("welcome.admin.texts.cards")}
        </Button>
      </div>
      {cardsOpen ? (
        <Card variant="plain" className="py-0" id={cardsId}>
          {fields.filter((f) => f.card).map((f) => (
            <FieldEditor key={f.field} f={f} audience={audience} drafts={drafts} setDraft={setDraft} />
          ))}
        </Card>
      ) : null}
      {stale ? (
        <p role="alert" className="rounded-xl bg-status-warning px-3 py-2 type-callout text-status-warning-fg" data-testid="welcome-stale">
          {stale}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2 max-sm:sticky max-sm:bottom-[calc(5rem+env(safe-area-inset-bottom))] max-sm:z-10 max-sm:rounded-2xl max-sm:bg-(--mat-thick-solid) max-sm:p-2">
        <Button className="pointer-coarse:min-h-11" disabled={invalid || save.isPending} onClick={() => setConfirm(true)} data-testid="welcome-save">
          {t("welcome.admin.texts.save")}
        </Button>
        <Button variant="secondary" className="pointer-coarse:min-h-11" onClick={() => openSheet({ mode: "preview", kind: "sheet", audience, overrides: drafts[locale] ?? {} })} data-testid="welcome-text-preview">
          {t("welcome.admin.texts.preview")}
        </Button>
        <p className="type-caption text-label-3" data-testid="welcome-last-change">
          {when ? t("welcome.admin.texts.lastChange", { who: content.updatedBy ?? t("welcome.admin.texts.staleSomeone"), when }) : t("welcome.admin.texts.never")}
        </p>
      </div>
      <ConfirmDialog open={confirm} onOpenChange={setConfirm} title={t("welcome.admin.texts.confirmTitle")} description={t("welcome.admin.texts.confirmBody")} confirmLabel={t("welcome.admin.texts.save")} busy={save.isPending} onConfirm={doSave}>
        <label className="flex min-h-11 items-center gap-3 type-callout text-label-1">
          <Checkbox checked={reshow} onCheckedChange={(v) => setReshow(!!v)} data-testid="welcome-reshow" />
          {t("welcome.admin.texts.reshow")}
        </label>
      </ConfirmDialog>
    </div>
  );
}

export function WelcomeTexts() {
  const { t } = useI18n();
  const [audience, setAudience] = useState<Audience>("academician");
  const q = useWelcomeContent(audience);
  const [key, setKey] = useState(0);
  // a fresh editor per audience and per loaded version
  useEffect(() => setKey((k) => k + 1), [audience, q.data?.version]);
  const empty: WelcomeContent = { audience, version: 0, texts: { tr: {}, en: {} }, updatedBy: null, updatedAt: null, contentVersion: null };
  return (
    <div className="flex flex-col gap-4">
      <div role="radiogroup" aria-label={t("welcome.admin.texts.audiences")} className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1 scrollbar-thin">
        {AUDIENCES.map((a) => (
          <Button
            key={a}
            role="radio"
            aria-checked={a === audience}
            variant={a === audience ? "default" : "secondary"}
            size="sm"
            className="shrink-0 pointer-coarse:min-h-11"
            onClick={() => setAudience(a)}
            data-testid={`welcome-audience-${a}`}
          >
            {t(audienceKey(a))}
          </Button>
        ))}
      </div>
      {q.isLoading ? <Loading /> : <Editor key={`${audience}-${key}`} audience={audience} content={q.data ?? empty} />}
    </div>
  );
}
