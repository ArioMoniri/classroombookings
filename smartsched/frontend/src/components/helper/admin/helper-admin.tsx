"use client";
/**
 * HX-09 (helper.md §13, ROADMAP HX-09; backend HB-14 / HB-15 `GET/PUT /ai/admin/helper`, `…/summary`):
 * `/admin/ai` › **Yardımcı**. One primary action (Kaydet). Visible: on / off, the mode (Yapay zekâ / Yalnızca dizin),
 * who may use it, and what it may do per action with plain risk words ("Kendi rezervasyonu", "Başkalarını
 * etkiler"); memory, retention, feedback notes and the off-topic scope sit behind "Gelişmiş". The summary is the
 * server's four sentence tiles and the unanswered searches typed by at least k = 5 people (no KPI wall).
 * A save sends `version`; 409 `stale_settings` reloads the current values and says so.
 */
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { Alert, SectionTitle } from "@/components/admin/kit";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { helperAdminKeys, helperRefusal, useHelperAdmin, useHelperSummary, useSaveHelperAdmin, type HelperAdmin as AdminData, type HelperAdminSettings } from "@/lib/api/helper";
import { useI18n } from "@/lib/i18n/provider";
import { pickText } from "../cards/context";

function Row({ id, label, hint, checked, onChange, disabled, testId }: { id: string; label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; testId?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <div className="min-w-0">
        <Label htmlFor={id} className="type-body">
          {label}
        </Label>
        {hint ? <p className="type-footnote text-label-2">{hint}</p> : null}
      </div>
      <Switch id={id} checked={checked} disabled={disabled} onCheckedChange={onChange} data-testid={testId} />
    </div>
  );
}

function Editor({ data, canEdit, error, setError }: { data: AdminData; canEdit: boolean; error: string | null; setError: (e: string | null) => void }) {
  const { t, locale } = useI18n();
  const save = useSaveHelperAdmin();
  const [s, setS] = useState<HelperAdminSettings>(data.settings);
  const [advanced, setAdvanced] = useState(false);
  const qc = useQueryClient();
  const audiences = data.catalog.audiences;
  const set = (patch: Partial<HelperAdminSettings>) => setS((p) => ({ ...p, ...patch }));
  const setAction = (name: string, patch: { enabled?: boolean; audiences?: string[] | null }) =>
    setS((p) => ({ ...p, actions: { ...p.actions, [name]: { enabled: p.actions[name]?.enabled ?? true, audiences: p.actions[name]?.audiences ?? null, ...patch } } }));

  const submit = async () => {
    setError(null);
    try {
      await save.mutateAsync({
        version: data.version ?? undefined,
        enabled: s.enabled,
        mode: s.mode,
        audiences: s.audiences,
        actions: Object.fromEntries(Object.entries(s.actions).map(([k, v]) => [k, { enabled: v.enabled, audiences: v.audiences ?? null }])),
        memory: { enabled: s.memory.enabled, retention_days: s.memory.retention_days },
        history_days: s.history_days,
        feedback_notes: s.feedback_notes,
        guard: { scope: s.guard.scope },
      });
      toast(t("helper.admin.saved"));
    } catch (err) {
      const r = helperRefusal(err);
      if (r.code === "stale_settings") {
        setError(t("helper.admin.stale"));
        void qc.invalidateQueries({ queryKey: helperAdminKeys.settings });
      } else setError((locale === "en" ? r.en : r.tr) ?? t("helper.error.provider"));
    }
  };

  return (
    <div className="flex flex-col gap-4">
      {data.effective?.message ? (
        <p className="type-callout text-label-1" data-testid="helper-admin-effective">
          {t("helper.admin.effective", { text: pickText(data.effective.message, locale) })}
          {data.effective.reason === "not_routed" ? <span className="block type-footnote text-label-2">{t("helper.admin.routeHint")}</span> : null}
        </p>
      ) : null}
      <Card variant="glass" className="gap-3 px-4">
        <Row id="hx-enabled" label={t("helper.admin.enabled")} hint={t("helper.admin.enabledHint")} checked={s.enabled} onChange={(v) => set({ enabled: v })} disabled={!canEdit} testId="helper-admin-enabled" />
        <div className="flex flex-col gap-1.5">
          <p className="type-body text-label-1" id="hx-mode">
            {t("helper.admin.mode")}
          </p>
          <SegmentedControl
            semantics="radiogroup"
            aria-labelledby="hx-mode"
            data-testid="helper-admin-mode"
            value={s.mode}
            onValueChange={(v) => canEdit && set({ mode: v })}
            options={[
              { value: "ai", label: t("helper.admin.modeAi"), testId: "helper-admin-mode-ai" },
              { value: "index", label: t("helper.admin.modeIndex"), testId: "helper-admin-mode-index" },
            ]}
          />
          {s.mode === "index" ? <p className="type-footnote text-label-2">{t("helper.admin.modeIndexHint")}</p> : null}
        </div>
      </Card>

      <Card variant="glass" className="gap-1 px-4">
        <h3 className="type-headline text-label-1">{t("helper.admin.audiences")}</h3>
        {audiences.map((a) => (
          <Row key={a.id} id={`hx-aud-${a.id}`} label={pickText(a.label, locale)} checked={s.audiences[a.id] !== false} onChange={(v) => set({ audiences: { ...s.audiences, [a.id]: v } })} disabled={!canEdit} testId={`helper-admin-audience-${a.id}`} />
        ))}
      </Card>

      <Card variant="glass" className="gap-1 px-4">
        <h3 className="type-headline text-label-1">{t("helper.admin.actions")}</h3>
        <p className="type-footnote text-label-2">{t("helper.admin.actionsLead")}</p>
        {data.catalog.actions.map((a) => {
          const cur = s.actions[a.name] ?? { enabled: true, audiences: null };
          const who = cur.audiences ?? null;
          return (
            <div key={a.name} className="flex flex-col gap-1 py-1.5 not-last:edge-hairline-b" data-testid={`helper-admin-action-${a.name}`}>
              <Row id={`hx-act-${a.name}`} label={pickText(a.summary, locale) || a.name} hint={pickText(a.risk_label, locale)} checked={cur.enabled} onChange={(v) => setAction(a.name, { enabled: v })} disabled={!canEdit} />
              {advanced && cur.enabled ? (
                <fieldset className="flex flex-wrap gap-x-4 gap-y-1 pb-1">
                  <legend className="sr-only">{t("helper.admin.audiences")}</legend>
                  {audiences.map((au) => {
                    const on = who === null || who.includes(au.id);
                    return (
                      <label key={au.id} className="inline-flex min-h-11 items-center gap-2 type-footnote text-label-1">
                        <Checkbox
                          checked={on}
                          disabled={!canEdit}
                          onCheckedChange={(v) => {
                            const base = who ?? audiences.map((x) => x.id);
                            const next = v ? [...new Set([...base, au.id])] : base.filter((x) => x !== au.id);
                            setAction(a.name, { audiences: next.length === audiences.length ? null : next });
                          }}
                        />
                        {pickText(au.label, locale)}
                      </label>
                    );
                  })}
                </fieldset>
              ) : null}
            </div>
          );
        })}
      </Card>

      <Button variant="ghost" className="self-start" aria-expanded={advanced} onClick={() => setAdvanced((v) => !v)} data-testid="helper-admin-advanced">
        {t("helper.admin.advanced")}
      </Button>
      {advanced ? (
        <Card variant="glass" className="gap-3 px-4">
          <Row id="hx-mem" label={t("helper.admin.memory")} checked={s.memory.enabled} onChange={(v) => set({ memory: { ...s.memory, enabled: v } })} disabled={!canEdit} />
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="hx-ret">{t("helper.admin.retention")}</Label>
              <Input id="hx-ret" type="number" min={1} max={365} value={s.memory.retention_days} disabled={!canEdit} onChange={(e) => set({ memory: { ...s.memory, retention_days: Number(e.target.value) || 1 } })} />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="hx-hist">{t("helper.admin.history")}</Label>
              <Input id="hx-hist" type="number" min={1} max={365} value={s.history_days} disabled={!canEdit} onChange={(e) => set({ history_days: Number(e.target.value) || 1 })} />
            </div>
          </div>
          <Row id="hx-fb" label={t("helper.admin.feedbackNotes")} checked={s.feedback_notes} onChange={(v) => set({ feedback_notes: v })} disabled={!canEdit} />
          {data.catalog.scopes.length ? (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="hx-scope">{t("helper.admin.scope")}</Label>
              <NativeSelect id="hx-scope" value={s.guard.scope} disabled={!canEdit} onChange={(e) => set({ guard: { ...s.guard, scope: e.target.value } })}>
                {data.catalog.scopes.map((sc) => (
                  <option key={sc.id} value={sc.id}>
                    {pickText(sc.label, locale)}
                  </option>
                ))}
              </NativeSelect>
            </div>
          ) : null}
        </Card>
      ) : null}

      {error ? (
        <Alert tone="error" testId="helper-admin-error">
          {error}
        </Alert>
      ) : null}
      {canEdit ? (
        <Button className="self-start" onClick={() => void submit()} disabled={save.isPending} data-testid="helper-admin-save">
          {save.isPending ? t("busy.saving") : t("helper.admin.save")}
        </Button>
      ) : null}
    </div>
  );
}

export function HelperSummary() {
  const { t, locale } = useI18n();
  const q = useHelperSummary(7);
  if (q.isLoading) return <Skeleton className="h-24 w-full" />;
  if (!q.data) return null;
  return (
    <section aria-labelledby="hx-summary" className="flex flex-col gap-3" data-testid="helper-summary">
      <h3 id="hx-summary" className="type-headline text-label-1">
        {t("helper.admin.summary")}
      </h3>
      <ul className="grid gap-3 sm:grid-cols-2">
        {q.data.tiles.slice(0, 4).map((tile, i) => (
          <li key={tile.id} className="rounded-(--radius-md) bg-fill-3 p-4 type-callout text-label-1 edge-hairline" data-testid={`helper-summary-tile-${i}`}>
            {locale === "en" ? tile.en || tile.tr : tile.tr}
          </li>
        ))}
      </ul>
      <div className="flex flex-col gap-1">
        <h4 className="type-callout font-semibold text-label-1">{t("helper.admin.misses")}</h4>
        <p className="type-footnote text-label-2">{t("helper.admin.missesLead", { k: q.data.k_min })}</p>
        {q.data.misses.length ? (
          <ul className="flex flex-col type-callout text-label-1">
            {q.data.misses.map((m) => (
              <li key={m.query} className="py-1 not-last:edge-hairline-b">
                {t("helper.admin.missRow", { q: m.query, users: m.users })}
              </li>
            ))}
          </ul>
        ) : (
          <p className="type-footnote text-label-3">{t("helper.admin.noMisses")}</p>
        )}
      </div>
    </section>
  );
}

/** The tab body. `canEdit`: the same rule as the other `/admin/ai` tabs. */
export function HelperAdminTab({ canEdit = true }: { canEdit?: boolean }) {
  const { t } = useI18n();
  const q = useHelperAdmin();
  const [error, setError] = useState<string | null>(null);
  return (
    <div className="flex flex-col gap-6" data-testid="helper-admin">
      <div>
        <SectionTitle>{t("helper.admin.title")}</SectionTitle>
        <p className="-mt-2 type-callout text-label-2">{t("helper.admin.lead")}</p>
      </div>
      {q.isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : q.data ? (
        <Editor key={q.data.version ?? "v"} data={q.data} canEdit={canEdit} error={error} setError={setError} />
      ) : (
        <Alert tone="error" action={<Button size="sm" variant="secondary" onClick={() => void q.refetch()}>{t("helper.retry")}</Button>}>
          {t("helper.admin.loadError")}
        </Alert>
      )}
      <HelperSummary />
    </div>
  );
}
