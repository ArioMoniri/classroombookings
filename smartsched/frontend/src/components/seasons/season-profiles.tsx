"use client";
/**
 * AS-15 "Dönem profilleri" on /admin/weeks (docs/research/2026-10-17-adaptive-scheduling.md §3.1, §3.6). One row per
 * profile key: the version it stands on, a draft waiting for approval (with its explanation and evidence), the
 * weights that differ from the standard, every version, and the one action that fits (Onayla / Geri al). A profile
 * never applies by itself: a draft changes nothing until an admin approves it. The weights and the peak threshold
 * sit behind "Gelişmiş" in the form. Confirmations move focus to the next row (never to <body>).
 */
import { Plus } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Alert, ConfirmDialog, Field, Loading, SectionTitle, SelectField } from "@/components/admin/kit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { BusyLabel } from "@/components/ui/busy-label";
import { useActiveTerm } from "@/components/shell/term-switcher";
import { HttpError } from "@/lib/api/client";
import { apiText, useProfileActions, useProfiles, type AppliesTo, type Profile, type ProfileList } from "@/lib/api/seasons";
import { useI18n } from "@/lib/i18n/provider";
import { appliesText, groupProfiles, nextRowKey, profileKey, weightOverrides, type ProfileGroup } from "./season-model";
import { SeasonPeriods } from "./season-periods";
import { useWeightLabel } from "./weight-label";

type Lang = "tr" | "en";
type Confirm = { kind: "activate" | "revert" | "delete"; profile: Profile; key: string };

export function SeasonProfiles() {
  const { t, locale } = useI18n();
  const lang: Lang = locale === "tr" ? "tr" : "en";
  const q = useProfiles();
  const act = useProfileActions();
  const [editing, setEditing] = useState<{ profile: Profile | null } | null>(null);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const newRef = useRef<HTMLButtonElement>(null);
  /** the row to focus once the list re-renders after an action (ROADMAP AS-15: focus to the next row) */
  const pendingFocus = useRef<string | null>(null);
  const groups = useMemo(() => groupProfiles(q.data?.profiles ?? [], lang), [q.data, lang]);
  const focusRow = (key: string | null) => {
    const row = key ? listRef.current?.querySelector<HTMLElement>(`[data-row-key="${CSS.escape(key)}"]`) : null;
    (row ?? newRef.current)?.focus();
  };
  const setFocusKey = (key: string | null) => {
    pendingFocus.current = key;
    // the dialog closes first; the row (or "Yeni profil") takes focus, never <body>
    requestAnimationFrame(() => focusRow(key));
  };
  useEffect(() => {
    if (pendingFocus.current === null) return;
    focusRow(pendingFocus.current);
    pendingFocus.current = null;
  }, [groups]);

  const termId = useActiveTerm().term?.id ?? null;
  const [proposeNote, setProposeNote] = useState<string | null>(null);
  const propose = () => {
    if (termId === null) return;
    act.propose.mutate(termId, {
      onSuccess: (out) => {
        if (out.proposal?.key) {
          setProposeNote(null);
          toast.success(t("seasons.proposed", { v: out.proposal.version ?? 1 }));
          setFocusKey(out.proposal.key);
        } else setProposeNote(out.needs?.[lang] || t("seasons.proposeNone"));
      },
      onError: (e) => toast.error(apiText(e, locale)),
    });
  };

  const run = () => {
    if (!confirm) return;
    const { kind, profile, key } = confirm;
    const id = profile.id ?? 0;
    const m = kind === "activate" ? act.activate : kind === "revert" ? act.revert : act.remove;
    m.mutate(id, {
      onSuccess: () => {
        toast.success(t(`seasons.done.${kind}`));
        setConfirm(null);
        setFocusKey(kind === "delete" ? (nextRowKey(groups.map((g) => g.key), key) ?? "") : key);
      },
      onError: (e) => toast.error(apiText(e, locale)),
    });
  };

  // ADMIN only: anyone else who opens /admin/weeks keeps the week editor alone (no 403 panel)
  if (q.error instanceof HttpError && q.error.status === 403) return null;

  return (
    <section aria-labelledby="season-profiles" className="flex flex-col gap-3" data-testid="season-profiles">
      <SectionTitle
        id="season-profiles"
        actions={
          <span className="flex flex-wrap gap-2">
            {/* AS-14: a learned draft from the term's manual edits; only an admin activates it */}
            <Button variant="outline" onClick={propose} disabled={termId === null || act.propose.isPending} data-testid="profile-propose">
              <BusyLabel busy={act.propose.isPending} label={t("busy.working")}>{t("seasons.propose")}</BusyLabel>
            </Button>
            <Button ref={newRef} onClick={() => setEditing({ profile: null })} data-testid="profile-new">
              <Plus /> {t("seasons.new")}
            </Button>
          </span>
        }
      >
        {t("seasons.title")}
      </SectionTitle>
      <p className="-mt-2 type-callout text-label-2">{t("seasons.lead")}</p>
      {proposeNote ? (
        <p role="status" className="rounded-lg bg-fill-3 px-3 py-2 type-callout text-label-1" data-testid="profile-propose-note">
          {proposeNote}
        </p>
      ) : null}
      <Card className="py-0">
        {q.isLoading ? (
          <Loading className="px-4" />
        ) : q.isError ? (
          <div className="p-4">
            <Alert tone="error" title={t("seasons.loadError")}>
              {apiText(q.error, locale)}
            </Alert>
          </div>
        ) : (
          <ul ref={listRef} data-testid="profile-list">
            {groups.map((g) => (
              <ProfileRow key={g.key} g={g} meta={q.data} lang={lang} onEdit={(p) => setEditing({ profile: p })} onConfirm={(kind, profile) => setConfirm({ kind, profile, key: g.key })} />
            ))}
          </ul>
        )}
      </Card>
      {q.data ? <SeasonPeriods /> : null}
      {editing && q.data ? <ProfileForm meta={q.data} profile={editing.profile} onClose={() => setEditing(null)} onSaved={(key) => setFocusKey(key)} /> : null}
      <ConfirmDialog
        open={!!confirm}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm ? t(`seasons.confirm.${confirm.kind}.title`, { name: confirm.profile.name[lang], v: confirm.profile.version }) : ""}
        description={confirm ? t(`seasons.confirm.${confirm.kind}.body`) : undefined}
        confirmLabel={confirm ? t(`seasons.confirm.${confirm.kind}.go`) : ""}
        destructive={confirm?.kind === "delete"}
        busy={act.activate.isPending || act.revert.isPending || act.remove.isPending}
        onConfirm={run}
      />
    </section>
  );
}

function StatusBadge({ p }: { p: Profile }) {
  const { t } = useI18n();
  if (p.builtin) return <Badge variant="secondary">{t("seasons.status.builtin")}</Badge>;
  if (p.status === "active") return <Badge tone="feasible">{t("seasons.status.active", { v: p.version })}</Badge>;
  if (p.status === "draft") return <Badge tone="warning">{t("seasons.status.draft", { v: p.version })}</Badge>;
  return <Badge variant="outline">{t("seasons.status.retired", { v: p.version })}</Badge>;
}

function ProfileRow({ g, meta, lang, onEdit, onConfirm }: { g: ProfileGroup; meta: ProfileList | undefined; lang: Lang; onEdit: (p: Profile) => void; onConfirm: (kind: Confirm["kind"], p: Profile) => void }) {
  const { t, locale } = useI18n();
  const wl = useWeightLabel();
  const p = g.current;
  const pending = g.draft ?? (p.status === "draft" ? p : null);
  const applies = appliesText(p.applies_to, meta?.seasons ?? [], meta?.period_kinds ?? [], lang, { season: t("seasons.anySeason"), kind: t("seasons.anyKind") });
  const explanation = pending ? (pending.explanation[lang] ?? pending.explanation.tr ?? "") : (p.explanation[lang] ?? "");
  const evidence = pending ? Object.entries(pending.evidence).filter(([, v]) => typeof v === "number" || typeof v === "string") : [];
  const diff = (pending ?? p).weights_diff;
  return (
    <li className="flex flex-col gap-2 px-4 py-3 outline-hidden focus-visible:outline-2 focus-visible:outline-solid focus-visible:outline-(--focus) not-last:edge-hairline-b" tabIndex={-1} data-row-key={g.key} data-testid="profile-row" data-status={p.status}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="type-headline text-label-1">{p.name[lang] || p.name.tr}</span>
        <StatusBadge p={p} />
        {g.draft ? <Badge tone="warning">{t("seasons.status.draft", { v: g.draft.version })}</Badge> : null}
        {pending && pending.origin === "learned" ? <Badge tone="tint">{t("seasons.origin.learned")}</Badge> : null}
      </div>
      {applies ? <p className="type-footnote text-label-2">{t("seasons.appliesTo", { text: applies })}</p> : null}
      {explanation ? <p className="type-callout text-label-1" data-testid="profile-explanation">{explanation}</p> : null}
      {evidence.length ? (
        <p className="type-footnote text-label-3" data-testid="profile-evidence">
          {t("seasons.evidence")}: {evidence.map(([k, v]) => `${wl(k)} ${typeof v === "number" ? v.toLocaleString(locale === "tr" ? "tr-TR" : "en-GB") : v}`).join(" · ")}
        </p>
      ) : null}
      {diff.length || g.versions.length > 1 ? (
        <details className="type-footnote">
          <summary className="flex min-h-11 cursor-pointer items-center text-tint-text pointer-fine:min-h-0 pointer-fine:py-1">{t("seasons.details")}</summary>
          {diff.length ? (
            <table className="mt-2 w-full max-w-md type-footnote" data-testid="profile-weights">
              <caption className="sr-only">{t("seasons.weightsCaption")}</caption>
              <thead>
                <tr className="text-left text-label-2">
                  <th scope="col" className="py-1 font-medium">{t("seasons.col.weight")}</th>
                  <th scope="col" className="py-1 text-right font-medium">{t("seasons.col.standard")}</th>
                  <th scope="col" className="py-1 text-right font-medium">{t("seasons.col.profile")}</th>
                </tr>
              </thead>
              <tbody>
                {diff.map((d) => (
                  <tr key={d.key} className="not-last:edge-hairline-b">
                    <th scope="row" className="py-1 text-left font-normal">{wl(d.key)}</th>
                    <td className="py-1 text-right tabular-nums">{d.default ?? "—"}</td>
                    <td className="py-1 text-right font-semibold tabular-nums">{d.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {g.versions.length > 1 ? (
            <ol className="mt-2 flex flex-col gap-1" aria-label={t("seasons.versions")} data-testid="profile-versions">
              {g.versions.map((v) => (
                <li key={v.id ?? v.version} className="flex flex-wrap items-center gap-2">
                  <StatusBadge p={v} />
                  <span className="text-label-2">{v.approved_at ? t("seasons.approvedAt", { date: new Date(v.approved_at).toLocaleDateString(locale === "tr" ? "tr-TR" : "en-GB") }) : v.created_at ? t("seasons.createdAt", { date: new Date(v.created_at).toLocaleDateString(locale === "tr" ? "tr-TR" : "en-GB") }) : ""}</span>
                </li>
              ))}
            </ol>
          ) : null}
        </details>
      ) : null}
      {p.builtin ? (
        <p className="type-footnote text-label-3">{t("seasons.builtinHint")}</p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {pending ? (
            <Button size="sm" onClick={() => onConfirm("activate", pending)} data-testid="profile-activate">
              {t("seasons.activate", { v: pending.version })}
            </Button>
          ) : null}
          {p.status === "active" && p.parent_id !== null && !g.draft ? (
            <Button size="sm" variant="outline" onClick={() => onConfirm("revert", p)} data-testid="profile-revert">
              {t("seasons.revert")}
            </Button>
          ) : null}
          <Button size="sm" variant="ghost" onClick={() => onEdit(pending ?? p)} data-testid="profile-edit">
            {t("seasons.edit")}
          </Button>
          {pending ? (
            <Button size="sm" variant="ghost" onClick={() => onConfirm("delete", pending)} data-testid="profile-delete">
              {t("seasons.deleteDraft")}
            </Button>
          ) : null}
        </div>
      )}
    </li>
  );
}

function ProfileForm({ meta, profile, onClose, onSaved }: { meta: ProfileList; profile: Profile | null; onClose: () => void; onSaved: (key: string) => void }) {
  const { t, locale } = useI18n();
  const lang: Lang = locale === "tr" ? "tr" : "en";
  const wl = useWeightLabel();
  const act = useProfileActions();
  const [nameTr, setNameTr] = useState(profile?.name_tr ?? "");
  const [nameEn, setNameEn] = useState(profile?.name_en ?? "");
  const [applies, setApplies] = useState<AppliesTo[]>(profile?.applies_to.length ? profile.applies_to : [{ season: "*", period_kind: "EXAM" }]);
  const [why, setWhy] = useState(profile?.explanation.tr ?? "");
  const [threshold, setThreshold] = useState(String(profile?.peak_threshold_pct ?? 85));
  const [weights, setWeights] = useState<Record<string, string>>(() => Object.fromEntries(Object.entries(profile?.solver_weights ?? {}).map(([k, v]) => [k, String(v)])));
  const [error, setError] = useState<string | null>(null);
  const busy = act.create.isPending || act.update.isPending;

  const save = () => {
    if (!nameTr.trim()) return setError(t("seasons.form.nameMissing"));
    const w = weightOverrides(weights, meta.defaults);
    if (w.invalid.length) return setError(t("seasons.form.weightInvalid", { names: w.invalid.map(wl).join(", ") }));
    const pct = Number(threshold);
    if (!Number.isInteger(pct) || pct < 50 || pct > 100) return setError(t("seasons.form.thresholdInvalid"));
    const body = { name_tr: nameTr.trim(), name_en: nameEn.trim() || nameTr.trim(), applies_to: applies, solver_weights: w.weights, peak_threshold_pct: pct, explanation: { tr: why.trim(), en: why.trim() } };
    const ok = (p: Profile) => {
      toast.success(profile?.status === "active" ? t("seasons.done.newVersion", { v: p.version }) : t("seasons.done.saved"));
      onClose();
      onSaved(p.key);
    };
    const fail = (e: unknown) => setError(apiText(e, locale));
    if (profile?.id) act.update.mutate({ id: profile.id, body }, { onSuccess: ok, onError: fail });
    else act.create.mutate({ ...body, key: profileKey(nameEn.trim() || nameTr) }, { onSuccess: ok, onError: fail });
  };

  const setApply = (i: number, patch: Partial<AppliesTo>) => setApplies((a) => a.map((x, j) => (j === i ? { ...x, ...patch } : x)));
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg" data-testid="profile-form">
        <DialogHeader>
          <DialogTitle>{profile ? t("seasons.form.editTitle") : t("seasons.form.newTitle")}</DialogTitle>
          <DialogDescription>{profile?.status === "active" ? t("seasons.form.activeHint") : t("seasons.form.draftHint")}</DialogDescription>
        </DialogHeader>
        <div className="flex max-h-[60dvh] flex-col gap-3 overflow-y-auto">
          <Field label={t("seasons.form.nameTr")} htmlFor="pf-name-tr">
            <Input id="pf-name-tr" value={nameTr} onChange={(e) => setNameTr(e.target.value)} placeholder={t("seasons.form.namePh")} data-testid="pf-name-tr" />
          </Field>
          <Field label={t("seasons.form.nameEn")} htmlFor="pf-name-en">
            <Input id="pf-name-en" value={nameEn} onChange={(e) => setNameEn(e.target.value)} />
          </Field>
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 type-footnote font-medium text-label-2">{t("seasons.form.when")}</legend>
            {applies.map((a, i) => (
              <div key={i} className="flex flex-wrap items-center gap-2">
                <SelectField aria-label={t("seasons.form.season")} value={a.season} onChange={(e) => setApply(i, { season: e.target.value })} className="min-w-0 flex-1" data-testid={`pf-season-${i}`}>
                  <option value="*">{t("seasons.anySeason")}</option>
                  {meta.seasons.map((s) => (
                    <option key={s.key} value={s.key}>{s.label[lang]}</option>
                  ))}
                </SelectField>
                <SelectField aria-label={t("seasons.form.kind")} value={a.period_kind} onChange={(e) => setApply(i, { period_kind: e.target.value })} className="min-w-0 flex-1" data-testid={`pf-kind-${i}`}>
                  <option value="*">{t("seasons.anyKind")}</option>
                  {meta.period_kinds.map((k) => (
                    <option key={k.key} value={k.key}>{k.label[lang]}</option>
                  ))}
                </SelectField>
                {applies.length > 1 ? (
                  <Button size="sm" variant="ghost" onClick={() => setApplies((x) => x.filter((_, j) => j !== i))}>
                    {t("seasons.form.removeWhen")}
                  </Button>
                ) : null}
              </div>
            ))}
            <Button size="sm" variant="ghost" className="self-start" onClick={() => setApplies((x) => [...x, { season: "*", period_kind: "*" }])}>
              <Plus /> {t("seasons.form.addWhen")}
            </Button>
          </fieldset>
          <Field label={t("seasons.form.why")} htmlFor="pf-why" hint={t("seasons.form.whyHint")}>
            <Textarea id="pf-why" value={why} onChange={(e) => setWhy(e.target.value)} rows={2} />
          </Field>
          <details className="rounded-lg bg-fill-3 px-3 py-1" data-testid="pf-advanced">
            <summary className="flex min-h-11 cursor-pointer items-center type-callout font-medium text-label-1">{t("seasons.form.advanced")}</summary>
            <div className="flex flex-col gap-3 pb-3">
              <Field label={t("seasons.form.threshold")} htmlFor="pf-threshold" hint={t("seasons.form.thresholdHint")}>
                <Input id="pf-threshold" type="number" inputMode="numeric" min={50} max={100} value={threshold} onChange={(e) => setThreshold(e.target.value)} className="w-28" />
              </Field>
              <p className="type-footnote text-label-2">{t("seasons.form.weightsHint")}</p>
              <div className="grid gap-2 sm:grid-cols-2">
                {meta.weight_keys.map((k) => (
                  <label key={k} className="flex items-center justify-between gap-2 type-footnote">
                    <span className="min-w-0 text-label-1">{wl(k)}</span>
                    <Input type="number" inputMode="numeric" min={0} max={10000} placeholder={String(meta.defaults[k] ?? "")} value={weights[k] ?? ""} onChange={(e) => setWeights((w) => ({ ...w, [k]: e.target.value }))} className="w-24 tnum" aria-label={wl(k)} data-testid={`pf-weight-${k}`} />
                  </label>
                ))}
              </div>
            </div>
          </details>
          {error ? (
            <p role="alert" className="type-footnote text-status-infeasible-fg" data-testid="pf-error">
              {error}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            {t("crbs.common.cancel")}
          </Button>
          <Button onClick={save} disabled={busy} data-testid="pf-save">
            <BusyLabel busy={busy} label={t("busy.saving")}>
              {t("seasons.form.saveDraft")}
            </BusyLabel>
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
