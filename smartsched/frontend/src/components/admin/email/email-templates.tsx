"use client";
/**
 * E-mail templates (W3-MAIL; docs/design/v3/emails.md): every message the system sends, its live preview with sample
 * data (desktop 600 px / phone 390 px toggle, TR / EN), the organisation's subject and opening-text overrides (rows of
 * the CRBS `translations` table, set `email`) and "Test gönder". The preview is the server's HTML in a sandboxed
 * iframe (no scripts, no same-origin), so a template can never run code in the panel.
 */
import { Send } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Alert, Field, Loading } from "@/components/admin/kit";
import { Badge } from "@/components/ui/badge";
import { BusyLabel } from "@/components/ui/busy-label";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n/provider";
import { cn } from "@/lib/utils";
import { useQueryClient } from "@tanstack/react-query";
import { mailApi, mailError, mailKeys, useTemplates, type Locale, type Preview, type Template } from "./api";

export const PREVIEW_WIDTH = { desktop: 640, phone: 390 } as const;

export function EmailTemplates() {
  const { t, locale } = useI18n();
  const q = useTemplates();
  const [kind, setKind] = useState<string | null>(null);
  const selected = q.data?.find((x) => x.kind === kind) ?? null;
  if (q.isLoading) return <Loading />;
  if (!q.data) return <Alert tone="error">{mailError(q.error, locale)}</Alert>;
  return (
    <div className="flex flex-col gap-4">
      <p className="type-callout text-label-2">{t("email.tpl.lead")}</p>
      <div className="grid gap-4 xl:grid-cols-[18rem_1fr]">
        <Card className="max-h-[70vh] gap-0 overflow-y-auto py-1 max-xl:max-h-80" aria-label={t("email.tpl.list")} role="region">
          <ul>
            {q.data.map((tpl) => {
              const changed = !!(tpl.overrides.tr.subject || tpl.overrides.tr.intro || tpl.overrides.en.subject || tpl.overrides.en.intro);
              return (
                <li key={tpl.kind} className="not-last:edge-hairline-b">
                  <Button
                    onClick={() => setKind(tpl.kind)}
                    aria-current={tpl.kind === kind ? "true" : undefined}
                    data-testid={`mail-tpl-${tpl.kind}`}
                    className={cn("h-auto whitespace-normal rounded-none flex min-h-11 w-full flex-col items-start gap-0.5 px-4 py-2 text-left", tpl.kind === kind ? "bg-tint-soft" : "hover:bg-fill-2")}
                  >
                    <span className="type-headline text-label-1">{locale === "tr" ? tpl.label_tr : tpl.label_en}</span>
                    <span className="flex flex-wrap items-center gap-1.5 type-footnote text-label-3">
                      {t("email.tpl.audience", { who: locale === "tr" ? tpl.audience_tr : tpl.audience_en })}
                      <Badge variant="secondary" tone={tpl.sender === "wired" ? "feasible" : "none"} title={tpl.sender === "wired" ? undefined : t("email.tpl.templateHint", { owner: tpl.owner })}>
                        {tpl.sender === "wired" ? t("email.tpl.wired") : t("email.tpl.template")}
                      </Badge>
                      {changed ? <Badge variant="secondary" tone="tint">{t("email.tpl.changed")}</Badge> : null}
                    </span>
                  </Button>
                </li>
              );
            })}
          </ul>
        </Card>
        {selected ? <TemplateEditor key={selected.kind} tpl={selected} /> : <p className="type-callout text-label-2">{t("email.tpl.choose")}</p>}
      </div>
    </div>
  );
}

function TemplateEditor({ tpl }: { tpl: Template }) {
  const { t, locale: uiLocale } = useI18n();
  const qc = useQueryClient();
  const ids = useId();
  const [lang, setLang] = useState<Locale>(uiLocale === "en" ? "en" : "tr");
  const [width, setWidth] = useState<keyof typeof PREVIEW_WIDTH>("desktop");
  const [subject, setSubject] = useState<string>(tpl.overrides[lang].subject ?? "");
  const [intro, setIntro] = useState<string>(tpl.overrides[lang].intro ?? "");
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [to, setTo] = useState("");
  const [sending, setSending] = useState(false);
  const [showText, setShowText] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const label = uiLocale === "tr" ? tpl.label_tr : tpl.label_en;

  useEffect(() => headingRef.current?.focus(), []);
  const draft = useMemo(() => ({ locale: lang, subject: subject || null, intro: intro || null }), [lang, subject, intro]);
  useEffect(() => {
    let live = true;
    const timer = window.setTimeout(() => {
      mailApi
        .preview(tpl.kind, draft)
        .then((p) => {
          if (live) {
            setPreview(p);
            setError(null);
          }
        })
        .catch((e: unknown) => live && setError(mailError(e, uiLocale)));
    }, 300);
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [tpl.kind, draft, uiLocale]);

  const save = async (reset = false) => {
    setSaving(true);
    try {
      await mailApi.save(tpl.kind, reset ? { locale: lang, subject: "", intro: "" } : { locale: lang, subject, intro });
      if (reset) {
        setSubject("");
        setIntro("");
      }
      await qc.invalidateQueries({ queryKey: mailKeys.templates });
      toast.success(t("email.tpl.saved"));
      setError(null);
    } catch (e) {
      setError(mailError(e, uiLocale));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="flex min-w-0 flex-col gap-4" aria-labelledby={`${ids}-h`}>
      <h3 id={`${ids}-h`} ref={headingRef} tabIndex={-1} className="type-title-3 text-label-1 focus:outline-hidden">
        {label}
      </h3>
      <div className="flex flex-wrap items-center gap-3">
        <SegmentedControl
          aria-label={t("email.tpl.language")}
          semantics="radiogroup"
          value={lang}
          onValueChange={(v) => {
            setLang(v);
            setSubject(tpl.overrides[v].subject ?? "");
            setIntro(tpl.overrides[v].intro ?? "");
          }}
          options={[
            { value: "tr", label: "Türkçe" },
            { value: "en", label: "English" },
          ]}
        />
        <SegmentedControl
          aria-label={t("email.tpl.width")}
          semantics="radiogroup"
          value={width}
          onValueChange={(v) => setWidth(v)}
          options={[
            { value: "desktop", label: t("email.tpl.desktop") },
            { value: "phone", label: t("email.tpl.phone") },
          ]}
        />
      </div>
      <div className="grid gap-3">
        <Field label={t("email.tpl.subject")} htmlFor={`${ids}-s`} hint={tpl.shipped[lang].subject ? t("email.tpl.shipped", { text: tpl.shipped[lang].subject! }) : undefined}>
          <Input id={`${ids}-s`} className="max-sm:text-base" value={subject} maxLength={255} onChange={(e) => setSubject(e.target.value)} data-testid="mail-tpl-subject" />
        </Field>
        <Field label={t("email.tpl.intro")} htmlFor={`${ids}-i`} hint={tpl.shipped[lang].intro ? t("email.tpl.shipped", { text: tpl.shipped[lang].intro! }) : undefined}>
          <Textarea id={`${ids}-i`} rows={3} className="max-sm:text-base" value={intro} maxLength={2000} onChange={(e) => setIntro(e.target.value)} />
        </Field>
        <p className="type-footnote text-label-3">{t("email.tpl.fields", { list: tpl.placeholders.map((p) => `{${p}}`).join(", ") })}</p>
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => void save()} disabled={saving} className="pointer-coarse:min-h-11" data-testid="mail-tpl-save">
            <BusyLabel busy={saving} label={t("busy.saving")}>
              {t("email.tpl.save")}
            </BusyLabel>
          </Button>
          <Button variant="outline" onClick={() => void save(true)} disabled={saving || !(tpl.overrides[lang].subject || tpl.overrides[lang].intro)} className="pointer-coarse:min-h-11">
            {t("email.tpl.reset")}
          </Button>
        </div>
      </div>
      {error ? <Alert tone="error">{error}</Alert> : null}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-2">
          <p className="type-headline text-label-1">{t("email.tpl.preview")}</p>
          <Button variant="ghost" size="sm" className="pointer-coarse:min-h-11" aria-pressed={showText} onClick={() => setShowText((x) => !x)}>
            {t("email.tpl.text")}
          </Button>
        </div>
        {preview ? <p className="type-callout text-label-1" data-testid="mail-tpl-preview-subject">{preview.subject}</p> : null}
        <div className="overflow-x-auto rounded-2xl bg-fill-2 p-2">
          {preview ? (
            showText ? (
              <pre className="max-h-[36rem] overflow-auto p-2 font-mono type-caption whitespace-pre-wrap text-label-1" data-testid="mail-tpl-text">
                {preview.text}
              </pre>
            ) : (
              <iframe
                title={t("email.tpl.previewTitle", { kind: label })}
                sandbox=""
                srcDoc={preview.html}
                data-testid="mail-tpl-frame"
                style={{ width: PREVIEW_WIDTH[width] }}
                className="mx-auto block h-[36rem] max-w-none rounded-xl bg-white"
              />
            )
          ) : (
            <Loading />
          )}
        </div>
      </div>
      <form
        className="flex flex-wrap items-end gap-2"
        onSubmit={async (e) => {
          e.preventDefault();
          setSending(true);
          try {
            const r = await mailApi.testTemplate(tpl.kind, { ...draft, to });
            if (r.ok) toast.success(t("email.tpl.testSent", { to }));
            else toast.warning((uiLocale === "tr" ? r.hint_tr : r.hint_en) ?? r.error ?? r.status);
          } catch (err) {
            toast.error(mailError(err, uiLocale));
          } finally {
            setSending(false);
          }
        }}
      >
        <Field label={t("email.tpl.testTo")} htmlFor={`${ids}-to`} className="min-w-0 max-sm:w-full">
          <Input id={`${ids}-to`} type="email" inputMode="email" className="w-full sm:w-64 max-sm:text-base" value={to} onChange={(e) => setTo(e.target.value)} />
        </Field>
        <Button type="submit" variant="outline" disabled={!to || sending} className="pointer-coarse:min-h-11 max-sm:w-full" data-testid="mail-tpl-test">
          <BusyLabel busy={sending} label={t("busy.sending")} icon={<Send aria-hidden />}>
            {t("email.tpl.testSend")}
          </BusyLabel>
        </Button>
      </form>
    </section>
  );
}
