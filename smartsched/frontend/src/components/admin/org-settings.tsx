"use client";
/**
 * /admin/settings (CRBS `settings/{Organisation,General}`, `setup/Language`, `Changelog`): organisation
 * name, website and logo; booking display (type, columns, room groups, ungrouped rooms, show names, grid
 * highlight, max active bookings); date patterns with a live preview; login message; maintenance mode;
 * languages and translation overrides; what's new.
 */
import { ImageUp, Loader2, Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { crbs, crbsError, useCrbsMutation, useDatePatternOptions, useOrgSettings, useTranslations, type OrgSettings, type OrgSettingsIn } from "@/lib/api/crbs";
import { LOCALES, LOCALE_INFO, coverage } from "@/lib/i18n";
import { useI18n } from "@/lib/i18n/provider";
import { dateFormatter } from "@/components/bookings/date-format";
import { bookingErrorMessage } from "@/components/bookings/booking-errors";
import { Alert, FieldRow, Loading, PageTitle, SectionTitle, SelectField } from "./kit";
import { useErrorToast } from "./admin-gate";
import { WhatsNewPanel } from "./whats-new";

const KEYS = [["crbs", "org-settings"], ["crbs", "org-public"], ["crbs", "context"], ["crbs", "grid"], ["crbs", "roles"]];
const TIMEZONES = ["Europe/Istanbul", "Europe/London", "Europe/Berlin", "UTC", "Asia/Baku", "Asia/Dubai", "America/New_York"];
/** the 14 shipped languages (Turkish, English, the 12 other CRBS languages), named in themselves */
const LANGS = LOCALES.map((code) => ({ code, label: LOCALE_INFO[code].name, partial: coverage(code) }));

export function OrgSettingsView() {
  const { t } = useI18n();
  const q = useOrgSettings();
  if (q.isLoading) return <Loading />;
  if (!q.data) return <Alert tone="error">{bookingErrorMessage(crbsError(q.error), t)}</Alert>;
  return <OrgForm key={JSON.stringify(q.data)} data={q.data} />;
}

function OrgForm({ data }: { data: OrgSettings & { grid_highlight?: boolean } }) {
  const { t, n, locale } = useI18n();
  const [d, setD] = useState<OrgSettingsIn & { grid_highlight?: boolean }>({});
  const v = { ...data, ...d } as OrgSettings & { grid_highlight?: boolean };
  const set = <K extends keyof typeof v>(k: K, val: (typeof v)[K]) => setD((p) => ({ ...p, [k]: val }));
  const [error, setError] = useState<string | null>(null);
  const [logo, setLogo] = useState(data.logo_url);
  const toastError = useErrorToast();
  const save = useCrbsMutation(() => crbs.org.putSettings(d), KEYS);
  const upload = useCrbsMutation((f: File) => crbs.org.uploadLogo(f), KEYS);
  const dropLogo = useCrbsMutation(() => crbs.org.deleteLogo(), KEYS);
  // CRBS offers fixed lists (Dates::date_pattern_options); PUT /org/settings accepts only these or "" = default
  const options = useDatePatternOptions(locale);
  const defaults = options.data?.language === locale ? options.data.defaults : undefined;
  const preview = useMemo(
    () => dateFormatter({ pattern_long: v.pattern_long, pattern_weekday: v.pattern_weekday, pattern_time: v.pattern_time }, locale, defaults),
    [v.pattern_long, v.pattern_weekday, v.pattern_time, locale, defaults],
  );
  const dirty = Object.keys(d).length > 0;
  const columnsFor = v.displaytype === "day" ? (["periods", "rooms"] as const) : (["periods", "days"] as const);

  return (
    <div className="flex flex-col gap-8 pb-20">
      <PageTitle title={t("crbs.admin.settings.title")} subtitle={t("crbs.admin.settings.lead")} />

      <section aria-labelledby="org-org">
        <SectionTitle id="org-org">{t("crbs.org.organisation")}</SectionTitle>
        <Card variant="glass" className="gap-0 px-4 py-1">
          <FieldRow label={t("crbs.org.name")} htmlFor="org-name">
            <Input id="org-name" className="w-72" maxLength={255} value={v.name ?? ""} onChange={(e) => set("name", e.target.value)} data-testid="org-name" />
          </FieldRow>
          <FieldRow label={t("crbs.org.website")} hint={t("crbs.org.websiteHint")} htmlFor="org-web" className="hairline-t">
            <Input id="org-web" type="url" className="w-72" placeholder="https://" value={v.website ?? ""} onChange={(e) => set("website", e.target.value)} />
          </FieldRow>
          <FieldRow label={t("crbs.org.logo")} hint={t("crbs.org.logoHint")} className="hairline-t">
            {/* eslint-disable-next-line @next/next/no-img-element -- uploaded by an administrator, served by the backend */}
            {logo ? <img src={logo} alt={t("crbs.org.logo")} className="h-10 max-w-40 rounded-md object-contain" /> : null}
            <Button variant="outline" size="sm" render={<label />} nativeButton={false}>
              <ImageUp aria-hidden />
              {t("crbs.org.uploadLogo")}
              <input type="file" accept="image/png,image/jpeg,image/gif,image/webp" className="sr-only" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0], { onSuccess: (r) => setLogo(r.logo_url ? `${r.logo_url}?v=${Date.now()}` : null), onError: toastError })} />
            </Button>
            {logo ? (
              <Button variant="ghost" size="icon-sm" aria-label={t("crbs.org.removeLogo")} onClick={() => dropLogo.mutate(undefined, { onSuccess: () => setLogo(null), onError: toastError })}>
                <Trash2 />
              </Button>
            ) : null}
          </FieldRow>
          <FieldRow label={t("crbs.org.timezone")} hint={t("crbs.org.timezoneHint")} htmlFor="org-tz" className="hairline-t">
            <SelectField id="org-tz" className="w-56" value={v.timezone ?? "Europe/Istanbul"} onChange={(e) => set("timezone", e.target.value)}>
              {[...new Set([v.timezone ?? "Europe/Istanbul", ...TIMEZONES])].map((z) => (
                <option key={z} value={z}>
                  {z}
                </option>
              ))}
            </SelectField>
          </FieldRow>
        </Card>
      </section>

      <section aria-labelledby="org-grid">
        <SectionTitle id="org-grid">{t("crbs.org.bookings")}</SectionTitle>
        <Card variant="glass" className="gap-0 px-4 py-1">
          <FieldRow label={t("crbs.org.displaytype")} hint={t("crbs.org.displaytypeHint")} htmlFor="org-dt">
            <SelectField id="org-dt" className="w-56" value={v.displaytype} onChange={(e) => setD((p) => ({ ...p, displaytype: e.target.value as "day" | "room", d_columns: "periods" }))}>
              <option value="day">{t("crbs.toolbar.byDay")}</option>
              <option value="room">{t("crbs.toolbar.byRoom")}</option>
            </SelectField>
          </FieldRow>
          <FieldRow label={t("crbs.org.columns")} hint={t("crbs.org.columnsHint")} htmlFor="org-cols" className="hairline-t">
            <SelectField id="org-cols" className="w-56" value={(columnsFor as readonly string[]).includes(v.d_columns) ? v.d_columns : "periods"} onChange={(e) => set("d_columns", e.target.value as OrgSettings["d_columns"])}>
              {columnsFor.map((c) => (
                <option key={c} value={c}>
                  {t(`crbs.org.col.${c}`)}
                </option>
              ))}
            </SelectField>
          </FieldRow>
          <FieldRow label={t("crbs.org.useGroups")} hint={t("crbs.org.useGroupsHint")} htmlFor="org-groups" className="hairline-t">
            <Switch id="org-groups" checked={v.use_room_groups} onCheckedChange={(x) => set("use_room_groups", x)} />
          </FieldRow>
          <FieldRow label={t("crbs.org.showUngrouped")} hint={t("crbs.org.showUngroupedHint")} htmlFor="org-ungrouped" className="hairline-t">
            <Switch id="org-ungrouped" checked={v.show_ungrouped_rooms} onCheckedChange={(x) => set("show_ungrouped_rooms", x)} data-testid="org-show-ungrouped" />
          </FieldRow>
          <FieldRow label={t("crbs.org.showNames")} hint={t("crbs.org.showNamesHint")} htmlFor="org-names" className="hairline-t">
            <Switch id="org-names" checked={v.bookings_show_name} onCheckedChange={(x) => set("bookings_show_name", x)} />
          </FieldRow>
          {"grid_highlight" in data ? (
            <FieldRow label={t("crbs.org.highlight")} hint={t("crbs.org.highlightHint")} htmlFor="org-hl" className="hairline-t">
              <Switch id="org-hl" checked={!!v.grid_highlight} onCheckedChange={(x) => set("grid_highlight", x)} />
            </FieldRow>
          ) : null}
          <FieldRow label={t("crbs.org.maxBookings")} hint={t("crbs.org.maxBookingsHint")} htmlFor="org-max" className="hairline-t">
            <Input
              id="org-max"
              type="number"
              min={0}
              className="w-24"
              placeholder={t("crbs.common.unlimited")}
              value={v.max_active_bookings ?? ""}
              onChange={(e) => setD((p) => (e.target.value === "" ? { ...p, max_active_bookings: null, max_active_bookings_unlimited: true } : { ...p, max_active_bookings: Number(e.target.value), max_active_bookings_unlimited: false }))}
            />
          </FieldRow>
        </Card>
      </section>

      <section aria-labelledby="org-dates">
        <SectionTitle id="org-dates">{t("crbs.org.dates")}</SectionTitle>
        <Card variant="glass" className="gap-0 px-4 py-1">
          {(["pattern_long", "pattern_weekday", "pattern_time"] as const).map((k, i) => (
            <FieldRow key={k} label={t(`crbs.org.${k}`)} hint={t("crbs.org.patternPreview", { value: k === "pattern_time" ? preview.time("08:30") : k === "pattern_long" ? preview.long("2026-04-23") : preview.weekday("2026-04-23") })} htmlFor={`org-${k}`} className={i ? "hairline-t" : undefined}>
              <SelectField id={`org-${k}`} className="w-72" value={v[k] ?? ""} onChange={(e) => set(k, e.target.value)} disabled={!options.data} data-testid={`org-${k}`}>
                {(() => {
                  const list = options.data?.[k] ?? [];
                  const current = v[k] ?? "";
                  // a value saved before the lists existed stays selectable until it is changed
                  const extra = current && !list.some((o) => o.pattern === current) ? [{ pattern: current, example: current, default: false }] : [];
                  return [...list, ...extra].map((o) => (
                    <option key={o.pattern || "default"} value={o.pattern}>
                      {o.default ? t("crbs.org.patternDefault", { example: o.example }) : `${o.example} (${o.pattern})`}
                    </option>
                  ));
                })()}
              </SelectField>
            </FieldRow>
          ))}
          <p className="pb-3 type-footnote text-label-3">{t("crbs.org.patternListHint")}</p>
        </Card>
      </section>

      <section aria-labelledby="org-login">
        <SectionTitle id="org-login">{t("crbs.org.loginAndMaintenance")}</SectionTitle>
        <Card variant="glass" className="gap-0 px-4 py-1">
          <FieldRow label={t("crbs.org.loginMessage")} hint={t("crbs.org.loginMessageHint")} htmlFor="org-lm">
            <Switch id="org-lm" checked={v.login_message_enabled} onCheckedChange={(x) => set("login_message_enabled", x)} />
          </FieldRow>
          {v.login_message_enabled ? <Textarea aria-label={t("crbs.org.loginMessage")} className="mb-3" rows={2} maxLength={1024} value={v.login_message_text ?? ""} onChange={(e) => set("login_message_text", e.target.value)} /> : null}
          <FieldRow label={t("crbs.org.maintenance")} hint={t("crbs.org.maintenanceHint")} htmlFor="org-mm" className="hairline-t">
            <Switch id="org-mm" checked={v.maintenance_mode} onCheckedChange={(x) => set("maintenance_mode", x)} data-testid="org-maintenance" />
          </FieldRow>
          {v.maintenance_mode ? <Textarea aria-label={t("crbs.org.maintenanceMessage")} placeholder={t("crbs.maintenance.default")} className="mb-3" rows={2} maxLength={1024} value={v.maintenance_mode_message ?? ""} onChange={(e) => set("maintenance_mode_message", e.target.value)} /> : null}
        </Card>
      </section>

      <section aria-labelledby="org-lang">
        <SectionTitle id="org-lang">{t("crbs.org.languages")}</SectionTitle>
        <Card variant="glass" className="gap-0 px-4 py-1">
          <FieldRow label={t("crbs.org.enabledLanguages")} hint={t("crbs.org.enabledLanguagesHint")}>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-3" data-testid="org-languages">
            {LANGS.map((l) => (
              <label key={l.code} lang={l.code} className="flex items-center gap-1.5 type-callout text-label-1">
                <Checkbox
                  checked={(v.languages ?? []).includes(l.code)}
                  onCheckedChange={(x) => {
                    const cur = new Set(v.languages ?? []);
                    if (x === true) cur.add(l.code);
                    else cur.delete(l.code);
                    if (cur.size) set("languages", LANGS.map((z) => z.code).filter((c) => cur.has(c)));
                  }}
                  data-testid={`org-language-${l.code}`}
                />
                <span className="flex min-w-0 flex-col leading-tight">
                  {l.label}
                  {l.partial.partial ? (
                    <span className="type-caption text-label-3" lang={locale}>
                      {t("nav.languagePartial", { pct: n(Math.max(l.partial.ratio, 0.01), { style: "percent", maximumFractionDigits: 0 }) })}
                    </span>
                  ) : null}
                </span>
              </label>
            ))}
            </div>
          </FieldRow>
          <FieldRow label={t("crbs.org.defaultLanguage")} htmlFor="org-deflang" className="hairline-t">
            <SelectField id="org-deflang" className="w-40" value={v.default_language ?? "tr"} onChange={(e) => set("default_language", e.target.value)}>
              {LANGS.filter((l) => (v.languages ?? []).includes(l.code)).map((l) => (
                <option key={l.code} value={l.code} lang={l.code}>
                  {l.label}
                </option>
              ))}
            </SelectField>
          </FieldRow>
        </Card>
      </section>

      <TranslationsEditor languages={v.languages ?? ["tr", "en"]} />

      <section aria-labelledby="org-news">
        <SectionTitle id="org-news">{t("crbs.news.title")}</SectionTitle>
        <WhatsNewPanel />
      </section>

      {error ? <Alert tone="error">{error}</Alert> : null}
      {dirty ? (
        <div className="glass-chrome fixed bottom-[max(1rem,env(safe-area-inset-bottom))] left-1/2 z-30 flex -translate-x-1/2 items-center gap-3 rounded-full py-1.5 pr-1.5 pl-4" role="region" aria-label={t("crbs.org.unsaved")}>
          <span className="type-callout text-label-1">{t("crbs.org.unsaved")}</span>
          <Button variant="ghost" size="sm" onClick={() => setD({})}>
            {t("crbs.common.cancel")}
          </Button>
          <Button
            size="sm"
            disabled={save.isPending}
            data-testid="org-save"
            onClick={() => {
              setError(null);
              save.mutate(undefined, { onSuccess: () => toast.success(t("crbs.common.saved")), onError: (e) => setError(bookingErrorMessage(crbsError(e), t)) });
            }}
          >
            {save.isPending ? <Loader2 className="animate-spin" aria-hidden /> : null}
            {t("crbs.common.save")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

/** CRBS `setup/Language`: per-language overrides of any interface string (set + key → text). */
function TranslationsEditor({ languages }: { languages: string[] }) {
  const { t } = useI18n();
  const [lang, setLang] = useState(languages[0] ?? "tr");
  const list = useTranslations(lang);
  const [set, setSet] = useState("crbs");
  const [key, setKey] = useState("");
  const [text, setText] = useState("");
  const toastError = useErrorToast();
  const keys = [["crbs", "translations"]];
  const upsert = useCrbsMutation((items: { language: string; set: string; key: string; text: string }[]) => crbs.org.putTranslations(items), keys);
  const remove = useCrbsMutation((id: number) => crbs.org.deleteTranslation(id), keys);
  return (
    <section aria-labelledby="org-tr" className="flex flex-col gap-3">
      <SectionTitle
        id="org-tr"
        actions={
          <SelectField aria-label={t("crbs.org.language")} className="w-36" value={lang} onChange={(e) => setLang(e.target.value)}>
            {languages.map((l) => (
              <option key={l} value={l}>
                {LANGS.find((x) => x.code === l)?.label ?? l}
              </option>
            ))}
          </SelectField>
        }
      >
        {t("crbs.org.translations")}
      </SectionTitle>
      <p className="type-callout text-label-2">{t("crbs.org.translationsHint")}</p>
      <Card variant="glass" className="py-0">
        {(list.data ?? []).length === 0 ? <p className="px-4 py-4 type-callout text-label-2">{t("crbs.org.noTranslations")}</p> : null}
        <ul>
          {(list.data ?? []).map((tr) => (
            <li key={tr.id} className="flex flex-col gap-1 px-4 py-2.5 shadow-[inset_0_-1px_0_var(--hairline)] last:shadow-none sm:flex-row sm:items-center sm:gap-3">
              <span className="w-56 shrink-0 truncate font-mono type-footnote text-label-2">
                {tr.set}.{tr.key}
              </span>
              <Input aria-label={`${tr.set}.${tr.key}`} defaultValue={tr.text} onBlur={(e) => e.target.value !== tr.text && upsert.mutate([{ language: tr.language, set: tr.set, key: tr.key, text: e.target.value }], { onSuccess: () => toast.success(t("crbs.common.saved")), onError: toastError })} />
              <Button variant="ghost" size="icon-sm" aria-label={t("crbs.common.delete")} onClick={() => remove.mutate(tr.id, { onError: toastError })}>
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      </Card>
      <form
        className="grid items-end gap-2 sm:grid-cols-[120px_1fr_2fr_auto]"
        onSubmit={(e) => {
          e.preventDefault();
          upsert.mutate([{ language: lang, set: set.trim(), key: key.trim(), text }], { onSuccess: () => (setKey(""), setText("")), onError: toastError });
        }}
      >
        <Input aria-label={t("crbs.org.trSet")} placeholder={t("crbs.org.trSet")} value={set} onChange={(e) => setSet(e.target.value)} />
        <Input aria-label={t("crbs.org.trKey")} placeholder={t("crbs.org.trKeyHint")} value={key} onChange={(e) => setKey(e.target.value)} />
        <Input aria-label={t("crbs.org.trText")} placeholder={t("crbs.org.trText")} value={text} onChange={(e) => setText(e.target.value)} />
        <Button type="submit" variant="outline" disabled={!set.trim() || !key.trim() || !text}>
          <Plus aria-hidden />
          {t("crbs.common.add")}
        </Button>
      </form>
    </section>
  );
}
