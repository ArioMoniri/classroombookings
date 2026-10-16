"use client";
/**
 * Admin → Approval rules (P1, `setup.rooms_acl`; docs/product/wave1-api.md §4). A rule on a room, a room
 * group or a room type (solver tag, e.g. TIP) makes bookings there requests that a designated approver
 * decides. The most specific rule wins (room > group > type; a session's rule before an every-session rule).
 * No rule = CRBS behaviour. Below the rules: the designated approvers and what they approve for (also set in
 * the user form, "Approves for").
 */
import { Pencil, Plus, Stamp, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Alert, ConfirmDialog, Field, Loading, PageTitle, SectionTitle, SelectField } from "@/components/admin/kit";
import { useCrbsMutation, useOrgSettings } from "@/lib/api/crbs";
import { errorText, useApprovalRules, useApprovers, wave1, wave1Error, w1Keys, type Approver, type Rule, type RuleIn, type Scope, type StepIn } from "@/lib/api/wave1";
import { usePermissions } from "@/lib/permissions";
import { useI18n } from "@/lib/i18n/provider";
import { normaliseScopes, ruleTarget, stepApprovers } from "./approvals-model";
import { ScopePicker, scopeLabel, useScopeLookups, type ScopeLookups } from "./scope-picker";

const RULE_KEYS = [w1Keys.rules, ["w1", "approvals"]];

export function ApprovalRulesAdmin() {
  const { t, locale } = useI18n();
  const { can } = usePermissions();
  const rules = useApprovalRules();
  const org = useOrgSettings(can("setup.settings"));
  const approvers = useApprovers(can(["setup.users", "approvals.decide", "setup.rooms_acl"]));
  const l = useScopeLookups();
  const [editing, setEditing] = useState<Rule | "new" | null>(null);
  const [deleting, setDeleting] = useState<Rule | null>(null);
  const [editApprover, setEditApprover] = useState<Approver | null>(null);
  const del = useCrbsMutation((r: Rule) => wave1.approvals.deleteRule(r.id), RULE_KEYS);
  const userName = (id: number) => approvers.data?.find((a) => a.user_id === id)?.name ?? undefined;
  const canDesignate = can("setup.users") && can("approvals.decide");
  return (
    <div className="flex flex-col gap-6" data-testid="approval-rules">
      <PageTitle
        title={t("wave1.rules.title")}
        subtitle={t("wave1.rules.subtitle")}
        actions={
          <Button onClick={() => setEditing("new")} data-testid="rule-new">
            <Plus aria-hidden />
            {t("wave1.rules.new")}
          </Button>
        }
      />
      <Card variant="glass" className="py-0">
        {rules.isLoading ? (
          <Loading className="px-4" />
        ) : rules.isError ? (
          <Alert tone="error" className="m-4">
            {errorText(wave1Error(rules.error), locale)}
          </Alert>
        ) : (rules.data ?? []).length === 0 ? (
          <p className="px-4 py-5 type-callout text-label-2" data-testid="rules-empty">
            {/* T-R1-10 (R1-M-24): the empty state says what happens now, from Rezervasyon onayı */}
            {t(org.data?.approval_mode === "all" ? "wave1.rules.noneAll" : "wave1.rules.none")}
          </p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-4">{t("wave1.rules.target")}</TableHead>
                <TableHead className="hidden md:table-cell">{t("wave1.rules.approvers")}</TableHead>
                <TableHead className="hidden lg:table-cell">{t("wave1.rules.conditions")}</TableHead>
                <TableHead>{t("wave1.rules.state")}</TableHead>
                <TableHead className="w-24 pr-4">
                  <span className="sr-only">{t("crbs.common.actions")}</span>
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(rules.data ?? []).map((r) => {
                const target = ruleTarget(r, l);
                const label = r.name || target.label;
                return (
                  <TableRow key={r.id} data-testid={`rule-${r.id}`}>
                    <TableCell className="pl-4">
                      <span className="block font-medium text-label-1">{label}</span>
                      <span className="block type-footnote text-label-3">
                        {t(`wave1.rules.kind.${target.kind}`)}
                        {r.name ? ` · ${target.label}` : ""}
                        {` · ${r.term_id != null ? (l.term(r.term_id) ?? `#${r.term_id}`) : t("wave1.rules.everyTerm")}`}
                      </span>
                    </TableCell>
                    <TableCell className="hidden text-label-2 md:table-cell">
                      {r.steps
                        .map((s, i) => {
                          const a = stepApprovers(s, { user: userName });
                          // admin persona M-35: a "designated approvers" step with nobody designated would never be decided
                          const none = a.designated && approvers.isSuccess && !approvers.data.some((x) => x.can_decide && x.scopes.length > 0);
                          const who = a.designated ? (none ? `${t("wave1.rules.designated")} (${t("wave1.rules.noneDesignated")})` : t("wave1.rules.designated")) : a.names.join(", ");
                          return r.steps.length > 1 ? `${i + 1}. ${who}` : who;
                        })
                        .join(" → ")}
                    </TableCell>
                    <TableCell className="hidden text-label-2 lg:table-cell">{conditions(r, t).join(" · ") || "—"}</TableCell>
                    <TableCell>{r.active ? <Badge tone="feasible">{t("wave1.rules.active")}</Badge> : <Badge variant="outline">{t("wave1.rules.inactive")}</Badge>}</TableCell>
                    <TableCell className="pr-4 text-right whitespace-nowrap">
                      <Button variant="ghost" size="icon-sm" aria-label={t("crbs.rooms.editNamed", { name: label })} onClick={() => setEditing(r)}>
                        <Pencil />
                      </Button>
                      <Button variant="ghost" size="icon-sm" aria-label={t("crbs.rooms.deleteNamed", { name: label })} onClick={() => setDeleting(r)}>
                        <Trash2 />
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </Card>

      <section aria-labelledby="approvers-title">
        <SectionTitle id="approvers-title">{t("wave1.rules.approverList")}</SectionTitle>
        <p className="mb-3 type-callout text-label-2">{t("wave1.rules.approverLead")}</p>
        <Card variant="glass" className="py-0">
          {approvers.isLoading ? (
            <Loading className="px-4" />
          ) : (approvers.data ?? []).length === 0 ? (
            <p className="px-4 py-5 type-callout text-label-2" data-testid="approvers-empty">
              {t("wave1.rules.noApprovers")}
            </p>
          ) : (
            <ul data-testid="approvers-list">
              {(approvers.data ?? []).map((a) => (
                <li key={a.user_id} className="flex items-center gap-3 px-4 py-2.5 hairline-b last:shadow-none">
                  <Stamp className="size-4 shrink-0 text-label-3" aria-hidden />
                  <span className="min-w-0 flex-1">
                    <span className="block type-headline text-label-1">{a.name ?? a.email}</span>
                    <span className="block truncate type-footnote text-label-2">{a.scopes.length ? a.scopes.map((s) => scopeLabel(s, l, t)).join(", ") : t("wave1.rules.noScopes")}</span>
                    {!a.can_decide ? <span className="block type-footnote text-status-warning-fg">{t("wave1.rules.cannotDecide")}</span> : null}
                  </span>
                  {canDesignate ? (
                    <Button variant="ghost" size="icon-sm" aria-label={t("wave1.rules.editApprover", { name: a.name ?? "" })} onClick={() => setEditApprover(a)}>
                      <Pencil />
                    </Button>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </section>

      <Dialog open={editing !== null} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="sm:max-w-xl">{editing !== null ? <RuleForm key={editing === "new" ? "new" : editing.id} rule={editing === "new" ? null : editing} approvers={approvers.data ?? []} lookups={l} onClose={() => setEditing(null)} /> : null}</DialogContent>
      </Dialog>
      <Dialog open={editApprover !== null} onOpenChange={(o) => !o && setEditApprover(null)}>
        <DialogContent>{editApprover ? <ApproverForm key={editApprover.user_id} approver={editApprover} lookups={l} onClose={() => setEditApprover(null)} /> : null}</DialogContent>
      </Dialog>
      <ConfirmDialog
        open={!!deleting}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t("wave1.rules.deleteTitle", { name: deleting ? deleting.name || ruleTarget(deleting, l).label : "" })}
        description={t("wave1.rules.deleteBody")}
        confirmLabel={t("crbs.common.delete")}
        destructive
        busy={del.isPending}
        onConfirm={() => deleting && del.mutate(deleting, { onSuccess: () => (setDeleting(null), toast.success(t("crbs.common.saved"))), onError: (e) => toast.error(errorText(wave1Error(e), locale)) })}
      />
    </div>
  );
}

function conditions(r: Pick<Rule, "hold_minutes" | "lead_time_workdays" | "expires_before_start_minutes" | "allow_self_approve">, t: ReturnType<typeof useI18n>["t"]): string[] {
  return [
    r.lead_time_workdays ? t("wave1.rules.leadN", { n: r.lead_time_workdays }) : null,
    r.hold_minutes ? t("wave1.rules.holdN", { n: r.hold_minutes }) : null,
    r.expires_before_start_minutes ? t("wave1.rules.expiresN", { n: r.expires_before_start_minutes }) : null,
    r.allow_self_approve ? t("wave1.rules.selfApprove") : null,
  ].filter((x): x is string => !!x);
}

interface StepDraft {
  mode: "designated" | "users";
  ids: number[];
  min: number;
}

function RuleForm({ rule, approvers, lookups: l, onClose }: { rule: Rule | null; approvers: Approver[]; lookups: ScopeLookups; onClose: () => void }) {
  const { t, locale } = useI18n();
  const [f, setF] = useState({
    name: rule?.name ?? "",
    entity_type: rule?.entity_type ?? ("room_group" as RuleIn["entity_type"]),
    entity_id: rule?.entity_id != null ? String(rule.entity_id) : "",
    tag: rule?.tag ?? "",
    term_id: rule?.term_id != null ? String(rule.term_id) : "",
    hold_minutes: String(rule?.hold_minutes ?? 0),
    lead_time_workdays: String(rule?.lead_time_workdays ?? 0),
    expires_before_start_minutes: String(rule?.expires_before_start_minutes ?? 0),
    allow_self_approve: rule?.allow_self_approve ?? false,
    active: rule?.active ?? true,
  });
  const [steps, setSteps] = useState<StepDraft[]>(
    rule?.steps.length ? rule.steps.map((s) => ({ mode: s.approvers.type === "users" ? "users" : "designated", ids: s.approvers.ids ?? [], min: s.min_approvals ?? 1 })) : [{ mode: "designated", ids: [], min: 1 }],
  );
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((p) => ({ ...p, [k]: v }));
  const num = (v: string, max: number) => Math.max(0, Math.min(max, Math.round(Number(v) || 0)));
  const body = (): RuleIn => ({
    name: f.name.trim() || null,
    entity_type: f.entity_type,
    entity_id: f.entity_type === "tag" ? null : f.entity_id ? Number(f.entity_id) : null,
    tag: f.entity_type === "tag" ? f.tag.trim().toUpperCase() || null : null,
    term_id: f.term_id ? Number(f.term_id) : null,
    steps: steps.map((s): StepIn => ({ approvers: s.mode === "users" ? { type: "users", ids: s.ids } : { type: "designated" }, min_approvals: Math.max(1, s.min) })),
    hold_minutes: num(f.hold_minutes, 10080),
    lead_time_workdays: num(f.lead_time_workdays, 60),
    expires_before_start_minutes: num(f.expires_before_start_minutes, 10080),
    allow_self_approve: f.allow_self_approve,
    active: f.active,
  });
  const save = useCrbsMutation(() => (rule ? wave1.approvals.updateRule(rule.id, body()) : wave1.approvals.createRule(body())), RULE_KEYS);
  const deciders = approvers.filter((a) => a.can_decide);
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        if (f.entity_type !== "tag" && !f.entity_id) return setError(t("wave1.rules.needTarget"));
        if (f.entity_type === "tag" && !f.tag.trim()) return setError(t("wave1.rules.needTag"));
        if (steps.some((s) => s.mode === "users" && s.ids.length === 0)) return setError(t("wave1.rules.needUsers"));
        save.mutate(undefined, { onSuccess: () => (toast.success(t("crbs.common.saved")), onClose()), onError: (err) => setError(errorText(wave1Error(err), locale)) });
      }}
    >
      <DialogHeader>
        <DialogTitle>{rule ? t("wave1.rules.editTitle") : t("wave1.rules.new")}</DialogTitle>
        <DialogDescription>{t("wave1.rules.formHint")}</DialogDescription>
      </DialogHeader>
      {/* phones: the dialog is a bottom sheet that scrolls itself, so no nested scroller clipping the switches' hit areas */}
      <div className="flex max-h-[min(70dvh,640px)] flex-col gap-3 overflow-y-auto pr-1 max-sm:max-h-none max-sm:overflow-visible">
        <Field label={t("wave1.rules.name")} htmlFor="rule-name" hint={t("wave1.rules.nameHint")}>
          <Input id="rule-name" maxLength={100} value={f.name} onChange={(e) => set("name", e.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("wave1.rules.appliesTo")} htmlFor="rule-type">
            <SelectField id="rule-type" value={f.entity_type} onChange={(e) => set("entity_type", e.target.value as RuleIn["entity_type"])} data-testid="rule-type">
              <option value="room_group">{t("wave1.rules.kind.room_group")}</option>
              <option value="tag">{t("wave1.rules.kind.tag")}</option>
              <option value="room">{t("wave1.rules.kind.room")}</option>
            </SelectField>
          </Field>
          {f.entity_type === "tag" ? (
            <Field label={t("wave1.rules.tag")} htmlFor="rule-tag" hint={t("wave1.rules.tagHint")}>
              <Input id="rule-tag" list="rule-tags" maxLength={16} value={f.tag} onChange={(e) => set("tag", e.target.value)} data-testid="rule-tag" />
              <datalist id="rule-tags">
                {l.tags.map((x) => (
                  <option key={x} value={x} />
                ))}
              </datalist>
            </Field>
          ) : (
            <Field label={f.entity_type === "room" ? t("wave1.rules.kind.room") : t("wave1.rules.kind.room_group")} htmlFor="rule-entity">
              <SelectField id="rule-entity" value={f.entity_id} onChange={(e) => set("entity_id", e.target.value)} data-testid="rule-entity">
                <option value="">{t("wave1.scope.pick")}</option>
                {(f.entity_type === "room" ? l.rooms : l.groups).map((x) => (
                  <option key={x.id} value={x.id}>
                    {x.name}
                  </option>
                ))}
              </SelectField>
            </Field>
          )}
        </div>
        <Field label={t("crbs.export.session")} htmlFor="rule-term">
          <SelectField id="rule-term" value={f.term_id} onChange={(e) => set("term_id", e.target.value)}>
            <option value="">{t("wave1.rules.everyTerm")}</option>
            {l.sessions.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </SelectField>
        </Field>

        <fieldset className="flex flex-col gap-2">
          <legend className="mb-1 type-headline text-label-1">{t("wave1.rules.steps")}</legend>
          {steps.map((s, i) => (
            <div key={i} className="flex flex-col gap-2 rounded-xl bg-fill-3 p-3" data-testid={`rule-step-${i + 1}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="type-callout font-medium text-label-1">{t("wave1.approvals.stepN", { n: i + 1, of: steps.length })}</span>
                {steps.length > 1 ? (
                  <Button type="button" variant="ghost" size="sm" onClick={() => setSteps((x) => x.filter((_, j) => j !== i))}>
                    {t("crbs.common.delete")}
                  </Button>
                ) : null}
              </div>
              <div className="grid gap-2 sm:grid-cols-[1fr_auto]">
                <SelectField aria-label={t("wave1.rules.approvers")} value={s.mode} onChange={(e) => setSteps((x) => x.map((y, j) => (j === i ? { ...y, mode: e.target.value as StepDraft["mode"] } : y)))}>
                  <option value="designated">{t("wave1.rules.designated")}</option>
                  <option value="users">{t("wave1.rules.namedUsers")}</option>
                </SelectField>
                <label className="flex items-center gap-2 type-footnote text-label-2">
                  {t("wave1.rules.minApprovals")}
                  <Input type="number" min={1} max={10} className="h-8 w-16" value={s.min} onChange={(e) => setSteps((x) => x.map((y, j) => (j === i ? { ...y, min: Math.max(1, Math.min(10, Number(e.target.value) || 1)) } : y)))} />
                </label>
              </div>
              {s.mode === "users" ? (
                deciders.length ? (
                  <div className="flex flex-wrap gap-x-4 gap-y-1.5" role="group" aria-label={t("wave1.rules.namedUsers")}>
                    {deciders.map((a) => (
                      <label key={a.user_id} className="flex items-center gap-2 type-callout text-label-1">
                        <input
                          type="checkbox"
                          className="size-4 accent-(--accent)"
                          checked={s.ids.includes(a.user_id)}
                          onChange={(e) => setSteps((x) => x.map((y, j) => (j === i ? { ...y, ids: e.target.checked ? [...y.ids, a.user_id] : y.ids.filter((id) => id !== a.user_id) } : y)))}
                        />
                        {a.name ?? a.email}
                      </label>
                    ))}
                  </div>
                ) : (
                  <p className="type-footnote text-status-warning-fg">{t("wave1.rules.noApprovers")}</p>
                )
              ) : null}
            </div>
          ))}
          {steps.length < 5 ? (
            <Button type="button" variant="outline" size="sm" className="self-start" onClick={() => setSteps((x) => [...x, { mode: "designated", ids: [], min: 1 }])}>
              <Plus aria-hidden />
              {t("wave1.rules.addStep")}
            </Button>
          ) : null}
        </fieldset>

        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={t("wave1.rules.lead")} htmlFor="rule-lead" hint={t("wave1.rules.leadHint")}>
            <Input id="rule-lead" type="number" min={0} max={60} inputMode="numeric" value={f.lead_time_workdays} onChange={(e) => set("lead_time_workdays", e.target.value)} />
          </Field>
          <Field label={t("wave1.rules.hold")} htmlFor="rule-hold" hint={t("wave1.rules.holdHint")}>
            <Input id="rule-hold" type="number" min={0} max={10080} inputMode="numeric" value={f.hold_minutes} onChange={(e) => set("hold_minutes", e.target.value)} data-testid="rule-hold" />
          </Field>
          <Field label={t("wave1.rules.expires")} htmlFor="rule-exp" hint={t("wave1.rules.expiresHint")}>
            <Input id="rule-exp" type="number" min={0} max={10080} inputMode="numeric" value={f.expires_before_start_minutes} onChange={(e) => set("expires_before_start_minutes", e.target.value)} />
          </Field>
        </div>
        <label className="flex items-center justify-between gap-3 type-callout text-label-1">
          <span>
            {t("wave1.rules.selfApprove")}
            <span className="block type-footnote text-label-3">{t("wave1.rules.selfApproveHint")}</span>
          </span>
          <Switch checked={f.allow_self_approve} onCheckedChange={(v) => set("allow_self_approve", v)} aria-label={t("wave1.rules.selfApprove")} />
        </label>
        <label className="flex items-center justify-between gap-3 type-callout text-label-1">
          {t("wave1.rules.active")}
          <Switch checked={f.active} onCheckedChange={(v) => set("active", v)} aria-label={t("wave1.rules.active")} />
        </label>
        {error ? <Alert tone="error">{error}</Alert> : null}
      </div>
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          {t("crbs.common.cancel")}
        </Button>
        <Button type="submit" disabled={save.isPending} data-testid="rule-save">
          {t("crbs.common.save")}
        </Button>
      </DialogFooter>
    </form>
  );
}

function ApproverForm({ approver, lookups, onClose }: { approver: Approver; lookups: ScopeLookups; onClose: () => void }) {
  const { t, locale } = useI18n();
  const [scopes, setScopes] = useState<Scope[]>(approver.scopes);
  const [error, setError] = useState<string | null>(null);
  const save = useCrbsMutation(() => wave1.approvals.setApprover(approver.user_id, normaliseScopes(scopes) as Scope[]), [w1Keys.approvers, ["crbs", "users"]]);
  return (
    <form
      className="flex flex-col gap-3"
      onSubmit={(e) => {
        e.preventDefault();
        setError(null);
        save.mutate(undefined, { onSuccess: () => (toast.success(t("crbs.common.saved")), onClose()), onError: (err) => setError(errorText(wave1Error(err), locale)) });
      }}
    >
      <DialogHeader>
        <DialogTitle>{t("wave1.rules.editApprover", { name: approver.name ?? approver.email ?? "" })}</DialogTitle>
        <DialogDescription>{t("wave1.scope.lead")}</DialogDescription>
      </DialogHeader>
      <ScopePicker value={scopes} onChange={setScopes} lookups={lookups} idPrefix="appr" />
      {scopes.length === 0 ? <p className="type-footnote text-status-warning-fg">{t("wave1.scope.noneRemoves")}</p> : null}
      {error ? <Alert tone="error">{error}</Alert> : null}
      <DialogFooter>
        <Button type="button" variant="ghost" onClick={onClose}>
          {t("crbs.common.cancel")}
        </Button>
        <Button type="submit" disabled={save.isPending}>
          {t("crbs.common.save")}
        </Button>
      </DialogFooter>
    </form>
  );
}
